#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
DEFAULT_TAGS = ["연예뉴스", "연예이슈", "아이돌", "배우", "드라마", "예능", "K팝", "컴백", "시청률", "오늘의연예"]
ENTITY_STOPWORDS = {
    "관련",
    "키워드",
    "뉴스",
    "기사",
    "보도",
    "단독",
    "포토",
    "영상",
    "오늘",
    "연예",
    "네이트",
    "종합",
    "공식",
    "데리고",
    "미모의",
    "최초",
    "공개",
    "이래서",
    "했나",
    "혼난",
    "있잖아",
    "엄마",
    "당황",
    "식은땀",
    "반응",
    "소식",
    "정리",
    "시험관",
    "시도",
    "난임센터",
    "현실",
    "고백",
    "연애",
    "관계",
    "여성",
    "여성과",
    "동시",
    "조화로운",
    "있어야",
    "징역형에",
    "면제",
    "출소",
    "여친에",
    "블박",
}
NOISY_TERM_SUFFIXES = (
    "는데",
    "지만",
    "면서",
    "했다",
    "한다",
    "했고",
    "하며",
    "하다",
    "해서",
    "하게",
    "했나",
    "인가",
)


def escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def format_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(KST).strftime("%Y.%m.%d %H:%M")
    except Exception:
        return value


def clamp_title(value: str, max_len: int = 72) -> str:
    value = clean_text(value)
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


def keyword_tags(item: dict, base_tags: list[str]) -> list[str]:
    tags: list[str] = []
    for term in [*(item.get("attention_terms") or []), *(item.get("important_keywords") or []), *base_tags]:
        display_term = meaningful_display_term(str(term)) or str(term)
        tag = re.sub(r"[^0-9A-Za-z가-힣]", "", display_term).strip()
        if len(tag) < 2 or tag in tags:
            continue
        if len(tag) > 15:
            continue
        if tag.startswith("징역형"):
            continue
        if tag in ENTITY_STOPWORDS or tag.endswith(NOISY_TERM_SUFFIXES):
            continue
        tags.append(tag)
        if len(tags) == 10:
            break
    while len(tags) < 10:
        for fallback in DEFAULT_TAGS:
            if fallback not in tags:
                tags.append(fallback)
                break
    return tags[:10]


def excerpt(value: str, max_len: int = 120) -> str:
    text = clean_text(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def has_final_consonant(value: str) -> bool:
    if not value:
        return False
    last = value[-1]
    code = ord(last) - 0xAC00
    return 0 <= code <= 11171 and code % 28 != 0


def normalize_entity_term(term: str) -> str:
    term = clean_text(term)
    term = re.sub(r"[\"'‘’“”\[\](){}<>.,!?…:;]+", "", term).strip()
    if len(term) < 2:
        return term

    suffix = term[-1]
    previous = term[-2]
    if suffix in {"은", "는", "을", "를", "와", "과", "의"}:
        return term[:-1].strip()
    if suffix == "이" and has_final_consonant(previous):
        return term[:-1].strip()
    if suffix == "가" and not has_final_consonant(previous):
        return term[:-1].strip()
    return term


def object_particle(value: str) -> str:
    return "을" if has_final_consonant(value.strip()) else "를"


def meaningful_display_term(raw_term: str) -> str:
    term = normalize_entity_term(raw_term)
    compact = re.sub(r"\s+", "", term)
    if len(compact) < 2 or len(compact) > 18:
        return ""
    if term in ENTITY_STOPWORDS or compact in ENTITY_STOPWORDS:
        return ""
    if compact.endswith(NOISY_TERM_SUFFIXES):
        return ""
    tokens = re.findall(r"[0-9A-Za-z가-힣]{2,}", term)
    if tokens and all(token in ENTITY_STOPWORDS for token in tokens):
        return ""
    return term


def entity_candidates(item: dict) -> list[str]:
    title = clean_text(item.get("title", ""))
    candidates = []
    candidates.extend(re.findall(r"\d+기\s*[A-Za-z가-힣0-9]{2,}", title))
    for term in item.get("attention_terms") or []:
        candidates.append(str(term))
    candidates.extend(re.findall(r"[A-Za-z가-힣0-9]{2,}", title))
    return candidates


def lead_entity(item: dict) -> str:
    title = clean_text(item.get("title", ""))
    if "아이오아이" in title:
        return "아이오아이"
    numbered_cast = re.search(r"\d+기\s*[A-Za-z가-힣0-9]{2,}", title)
    if numbered_cast:
        term = meaningful_display_term(numbered_cast.group(0))
        if term:
            return term
    comma_name = re.search(r"([가-힣]{2,4}),", title)
    if comma_name:
        term = meaningful_display_term(comma_name.group(1))
        if term:
            return term
    for raw_term in entity_candidates(item):
        term = meaningful_display_term(raw_term)
        if not term:
            continue
        if " " in term and not re.match(r"\d+기\s*[A-Za-z가-힣0-9]{2,}$", term):
            continue
        if len(term) > 10:
            continue
        if re.search(r"[가-힣A-Za-z]", term):
            return term
    for term in item.get("attention_terms") or []:
        term = clean_text(str(term))
        if 2 <= len(term) <= 18:
            return term
    words = re.findall(r"[0-9A-Za-z가-힣]{2,}", clean_text(item.get("title", "")))
    return words[0] if words else "이번 연예 이슈"


def keyword_terms(item: dict) -> list[str]:
    terms: list[str] = []
    for raw_term in [*(item.get("attention_terms") or []), *(item.get("important_keywords") or [])]:
        term = meaningful_display_term(str(raw_term))
        if not term or term in terms:
            continue
        terms.append(term)
        if len(terms) == 4:
            break
    entity = lead_entity(item)
    if entity not in terms:
        terms.insert(0, entity)
    return terms[:4]


def compact_title(item: dict) -> str:
    title = clean_text(item.get("title", ""))
    title = re.sub(r"\[[^\]]+\]", "", title)
    title = re.sub(r"\s*-\s*[^-]{2,30}$", "", title)
    return clamp_title(title, 64)


def unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", clean_text(value)).strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def title_candidates(item: dict) -> list[str]:
    terms = keyword_terms(item)
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    secondary = next((term for term in terms if term != entity), "")
    sensitive_title = any(keyword in title for keyword in ["루머", "의혹", "논란", "폭로", "사생활", "혐의"])
    has_couple_story = any(term in title or term in terms for term in ["부부싸움", "목격담", "고우림"])
    partner = "고우림" if "고우림" in title or "고우림" in terms else secondary

    if "한예리" in title and ("백상" in title or "워스트" in title):
        candidates = [
            "한예리 백상 드레스 반응, 본인은 이렇게 말했다",
            "한예리 워스트 드레서 언급에 남긴 말",
            "한예리 드레스 호불호에 직접 남긴 글",
        ]
    elif "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        candidates = [
            "아이오아이 신곡 반응, 갑자기 공개된 챌린지",
            "아이오아이 10주년 신곡 갑자기 챌린지",
            "아이오아이 신곡 반응과 강미나 언급까지",
        ]
    elif sensitive_title:
        candidates = [
            f"{entity} 관련 보도, 방송 장면과 온라인 주장",
            f"{entity} 관련 이야기, 기사 속 장면들",
            f"{entity} 이슈, 지금 나온 내용과 반응",
        ]
    elif has_couple_story and partner:
        candidates = [
            f"{entity} {partner} 부부 이야기, 예능에서 나온 한마디",
            f"{entity} {partner} 목격담, 예능 예고 속 장면",
            f"{entity} {partner} 관련 소식, 방송에서 나온 말",
        ]
    elif "김지민" in title and any(keyword in title for keyword in ["시험관", "난임센터"]):
        candidates = [
            "김지민 시험관 시술 고백, 난임센터 현실까지",
            "김지민 난임센터 이야기, 방송에서 나온 현실",
            "김지민 시험관 근황, 방송에서 꺼낸 말",
        ]
    elif "니요" in title and any(keyword in title for keyword in ["동시 연애", "관계"]):
        candidates = [
            "니요 세 여성과 동시 연애, 본인이 밝힌 관계",
            "니요 3년째 조화로운 관계, 직접 밝힌 생활",
            "니요 다자 연애 고백, 선택권 언급까지",
        ]
    elif "손승원" in title and "음주운전" in title:
        candidates = [
            "손승원 음주운전 재판, 다시 나온 기사 내용",
            "손승원 출소 후 음주운전, 재판에서 나온 말",
            "손승원 무면허 운전까지, 기사에 담긴 정황",
        ]
    elif "컴백" in title or "컴백" in (item.get("important_keywords") or []):
        candidates = [
            f"{entity} 컴백 소식, 먼저 공개된 장면",
            f"{entity} 새 소식, 오늘 나온 내용",
            f"{entity} 컴백 앞두고 나온 이야기",
        ]
    elif "시청률" in title or "시청률" in (item.get("important_keywords") or []):
        candidates = [
            f"{entity} 시청률 이야기, 숫자 뒤 장면",
            f"{entity} 관련 반응, 오늘 기사 속 장면",
            f"{entity} 방송 이슈, 기사에 담긴 말",
        ]
    else:
        candidates = [
            f"{entity} 관련 이야기, 오늘 나온 내용",
            f"{entity} 소식, 기사에서 나온 말은 이랬다",
            f"{secondary or entity} 소식, 기사 속 장면과 반응",
        ]
    return [clamp_title(candidate, 64) for candidate in unique_strings(candidates)[:3]]


def blog_title(item: dict) -> str:
    return title_candidates(item)[0]


def blog_summary(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    sentences = article_sentences(item)
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "아이오아이 신곡 이야기는 기대가 컸던 만큼 반응도 빨리 갈렸습니다. "
            "10주년 앨범 소식에 챌린지 영상이 먼저 나오면서 팬들 사이에서도 말이 꽤 나왔습니다. "
            "아직 전체 곡을 다 들은 상황은 아니라서, 몇 초짜리 첫 구간만으로 첫인상이 먼저 퍼진 셈입니다. "
            "팬들이 기다린 10주년 앨범이라는 점까지 더해져 짧은 영상에도 말이 꽤 많았습니다."
        )
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return (
            "김연아·고우림 부부 이야기는 예능 예고 속 한마디에서 시작됐습니다. "
            "제목만 보면 부부싸움처럼 크게 보일 수 있지만, 실제로는 강남이 받아친 농담에 가까운 장면입니다. "
            "강남·이상화 부부의 냉장고 이야기가 나오던 자리에서 자연스럽게 이어진 생활 토크였습니다. "
            "방송이 공개되면 분위기는 훨씬 가볍게 느껴질 가능성이 있습니다."
        )
    if "한예리" in title and ("백상" in title or "워스트" in title):
        return (
            "한예리의 백상예술대상 드레스 이야기가 다시 올라왔습니다. "
            "워스트 드레서 반응도 있었지만, 정작 한예리는 꽤 담담하게 자기 생각을 남겼습니다. "
            "꽃 장식이 큰 화이트 드레스라 온라인에서 호불호가 갈렸고, 그 반응을 본 뒤 직접 글을 올렸습니다. "
            "그는 자신이 입고 싶은 드레스를 입었고, 그 선택이 충분히 아름다웠다는 쪽으로 말을 꺼냈습니다."
        )
    if "손승원" in title and "음주운전" in title:
        return (
            "손승원 음주운전 관련 재판 소식이 다시 기사로 나왔습니다. "
            "과거 음주운전으로 실형을 받은 이력이 있는 만큼, 이번 보도는 단순한 사건 기사보다 더 무겁게 읽힙니다. "
            "기사에는 음주운전 사고와 도주 혐의, 블랙박스 저장장치 관련 부탁, 무면허 운전 정황까지 함께 담겼습니다. "
            "재판에서 어떤 혐의가 언급됐는지와 과거 이력이 왜 함께 다뤄졌는지가 같이 보이는 기사였습니다."
        )
    if item.get("safety_flags"):
        return (
            f"{entity} 이야기는 '나는 SOLO' 방송 이후 온라인 익명 글까지 더해지며 커졌습니다. "
            "익명 글에는 임신 상태와 편집 요청을 둘러싼 주장이 들어갔고, 방송에서는 순자가 눈물을 보인 장면이 다시 언급됐습니다. "
            "여기에 미공개 영상 삭제와 통편집설까지 겹치면서 관련 이야기가 빠르게 커졌습니다. "
            "방송에서 실제로 나온 장면과 온라인 글의 주장이 한꺼번에 오간 상황입니다."
        )
    if "김지민" in title and any(keyword in title for keyword in ["시험관", "난임센터"]):
        return (
            "김지민이 시험관 시술 중 겪고 있는 이야기를 방송에서 꺼냈습니다. "
            "난임센터에 사람이 많아 앉을 자리도 없었다는 말이 기사에 담기면서 현실적인 반응도 나왔습니다. "
            "가벼운 예능 토크라기보다 본인이 지나고 있는 과정을 담담하게 꺼낸 장면에 가깝습니다. "
            "그래서 이번 내용은 짧은 방송 멘트였지만 근황 고백처럼 더 길게 남았습니다."
        )
    if "니요" in title and any(keyword in title for keyword in ["동시 연애", "관계"]):
        return (
            "니요가 세 여성과 함께 지내는 관계를 직접 설명했습니다. "
            "동시 연애라는 표현이 먼저 보이지만, 기사에서 본인이 강조한 건 모두가 알고 선택했다는 부분이었습니다. "
            "아이들과 함께 생활한다는 내용과 일부 계약 무산 이야기도 같이 언급됐습니다. "
            "사생활 이슈인 만큼 기사에는 본인의 설명과 이후 반응이 함께 담겼습니다."
        )
    first_raw = first_meaningful_sentence(sentences) if sentences else ""
    first = soften_sentence(first_raw, 170) if first_raw else ""
    context_raw = contextual_sentence(item, ["방송", "영상", "공개", "발매", "출연", "소속사", "휴식", "안정"])
    if strip_article_noise(context_raw) == strip_article_noise(first_raw):
        context_raw = ""
    context = soften_sentence(context_raw, 160) if context_raw else ""
    if first and context:
        return (
            f"{entity} 관련해서 오늘 새로 나온 이야기는 이 부분입니다. "
            f"{first} "
            f"{context} "
            "기사에 나온 말과 장면이 이어지면서 오늘 소식의 분위기도 조금 더 선명하게 보입니다."
        )
    return (
        f"{entity} 관련 이야기가 새로 올라왔습니다. "
        "기사에는 공개된 장면과 발언, 주변 반응이 함께 담겼습니다. "
        "처음 나온 말과 이어진 상황을 자연스럽게 풀어봤습니다."
    )


def article_sentences(item: dict) -> list[str]:
    sentences = [clean_text(sentence) for sentence in item.get("article_sentences", []) if clean_text(sentence)]
    if sentences:
        return sentences
    text = clean_text(item.get("article_text", ""))
    if not text:
        return []
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?。])\s+", text) if len(sentence.strip()) > 15]


def sentence_with(sentences: list[str], keywords: list[str]) -> str:
    for sentence in sentences:
        if all(keyword in sentence for keyword in keywords):
            return sentence
    for sentence in sentences:
        if any(keyword in sentence for keyword in keywords):
            return sentence
    return ""


def strip_article_noise(sentence: str) -> str:
    sentence = clean_text(sentence)
    sentence = re.sub(r"^\[[^\]]+\]\s*", "", sentence)
    sentence = re.sub(r"^\*?재판매 및 DB 금지\s*", "", sentence)
    sentence = re.sub(r"^[^=\s]{1,20}\s*[^=\s]{0,20}/사진=[^\s]+\s*", "", sentence)
    sentence = re.sub(r"^\([^)]{1,40}기자\)\s*", "", sentence)
    sentence = re.sub(r"^[가-힣A-Za-z·\s]{2,20}\s*기자\s*=\s*", "", sentence)
    sentence = re.sub(r"^/[A-Za-z가-힣+·\s]+‘[^’]{2,40}’\s*", "", sentence)
    sentence = re.sub(r"^(제작진에 따르면|무엇보다|또한|또|특히|현재)\s*", "", sentence)
    sentence = re.sub(r"^([0-9A-Za-z가-힣]+)\s+\1([은는이가의을를])", r"\1\2", sentence)
    sentence = re.sub(r"^([0-9A-Za-z가-힣]+)\s+\1(?=\s)", r"\1", sentence)
    return sentence.strip()


def soften_sentence(sentence: str, max_len: int = 170) -> str:
    sentence = strip_article_noise(sentence)
    replacements = {
        "충격적인 ": "",
        "일부 네티즌들은": "일부에서는",
        "솔직한 생각을 밝혔다": "직접 생각을 남겼습니다",
        "입장을 밝혔다": "입장을 전했습니다",
        "토로했다": "털어놨습니다",
        "물의를 빚었다": "물의를 빚었습니다",
        "재판을 가졌다": "재판을 받았습니다",
        "알려졌다": "알려졌습니다",
        "포착됐다": "포착됐습니다",
        "전해졌다": "전해졌습니다",
        "올랐다": "올랐습니다",
        "실리고 있다": "실리고 있습니다",
        "근황을 공개했다": "근황을 공개했습니다",
        "공개했다": "공개했습니다",
        "공개됐다": "공개됐습니다",
        "공개된다": "공개됩니다",
        "밝혔다": "이야기했습니다",
        "밝혀 놀라움을 자아낸다": "밝혔습니다",
        "발매한다": "발매합니다",
        "게재했다": "올렸습니다",
        "전했다": "전했습니다",
        "설명했다": "설명했습니다",
        "설명했다.": "설명했습니다.",
        "언급했다": "언급했습니다",
        "덧붙였다": "덧붙였습니다",
        "공감을 안긴다": "공감을 안겼습니다",
        "무산됐다고도 했다": "무산됐다고도 했습니다",
        "주장이 제기됐다": "주장이 나왔습니다",
        "소신을 드러냈다": "자기 생각을 분명히 했습니다",
        "눈길을 끌었다": "눈에 들어온 대목입니다",
        "화제를 모았다": "이야기가 퍼졌습니다",
        "확산되며": "퍼지면서",
        "극단적으로 엇갈린다": "크게 엇갈리고 있습니다",
        "반응을 보이기도 했다": "반응도 나왔습니다",
        "반응을 보였다": "반응이 나왔습니다",
        "파장이 일고 있다": "논란이 커지고 있습니다",
        "시청자들의 공분을 사고 있다": "시청자들 사이에서 불편하다는 반응도 나오고 있습니다",
        "공분을 사고 있다": "불편하다는 반응도 나오고 있습니다",
        "온라인이 발칵 뒤집혔다": "온라인에서 여러 반응이 나왔습니다",
        "발칵 뒤집혔다": "여러 반응이 나왔습니다",
        "관심이 쏠린다": "이어질 여지도 있어 보입니다",
        "이어졌다": "이어졌습니다",
        "비판의 화살이 집중됐다": "비판이 나왔습니다",
        "집중됐다": "모였습니다",
        "송출되며": "방송에 나오면서",
        "꼬집었다": "지적했습니다",
        "털어놔 웃음을 자아낸다": "털어놨다는 내용입니다",
        "폭소를 유발한다": "웃음을 더한 대목입니다",
    }
    for before, after in replacements.items():
        sentence = sentence.replace(before, after)
    sentence = re.sub(r"했다([.。]?)$", r"했습니다\1", sentence)
    sentence = re.sub(r"됐다([.。]?)$", r"됐습니다\1", sentence)
    sentence = re.sub(r"한다([.。]?)$", r"합니다\1", sentence)
    sentence = re.sub(r"된다([.。]?)$", r"됩니다\1", sentence)
    sentence = re.sub(r"자아낸다([.。]?)$", r"자아냈습니다\1", sentence)
    return excerpt(sentence, max_len)


def quoted_phrases(sentences: list[str]) -> list[str]:
    text = " ".join(strip_article_noise(sentence) for sentence in sentences)
    phrases = []
    for phrase in re.findall(r"[“\"]([^”\"]{6,120})[”\"]", text):
        phrase = clean_text(phrase)
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases


def first_meaningful_sentence(sentences: list[str]) -> str:
    for sentence in sentences:
        cleaned = strip_article_noise(sentence)
        if len(cleaned) < 20:
            continue
        if cleaned.startswith(("누리꾼들의 반응", "일각에서는")):
            continue
        return cleaned
    return sentences[0] if sentences else ""


def claim_line(sentence: str) -> str:
    quotes = quoted_phrases([sentence])
    if quotes:
        return f"글에는 \"{excerpt(quotes[0], 90)}\"라는 주장이 담겼습니다."
    return soften_sentence(sentence, 150)


def edit_claim_line(sentence: str) -> str:
    quotes = quoted_phrases([sentence])
    if quotes:
        return f"작성자 주장에는 \"{excerpt(quotes[0], 95)}\"라는 내용까지 들어가 있습니다."
    return soften_sentence(sentence, 160)


def hanyeri_style_summary(sentences: list[str]) -> list[str]:
    quotes = quoted_phrases(sentences)
    main_quote = next((quote for quote in quotes if "드레스" in quote), quotes[0] if quotes else "")
    staff_quote = next((quote for quote in quotes if "무난" in quote or "아름다" in quote), "")
    return [
        (
            "배우 한예리가 백상예술대상 드레스 스타일링을 두고 나온 '워스트 드레서' 반응에 직접 입장을 남겼습니다. "
            "당시 한예리는 꽃 장식이 돋보이는 화이트 드레스를 입었고, 온라인에서는 디자인을 두고 호불호가 갈렸습니다."
        ),
        (
            f"하지만 한예리의 입장은 달랐습니다. 그는 SNS에 \"{excerpt(main_quote, 105)}\"라고 적었습니다. "
            "워스트 평가에 아쉬움을 드러냈다기보다는, 자신이 고른 드레스가 좋았다는 쪽에 가까웠습니다."
        ),
        (
            f"일부에서는 가슴 부분 장식을 두고 '달걀프라이 같다'는 말도 나왔습니다. "
            f"한예리는 \"{excerpt(staff_quote, 95)}\"라는 말도 덧붙이며 스태프에게 고마움을 전했습니다."
        ),
    ]


def ioi_song_summary(sentences: list[str]) -> list[str]:
    release = sentence_with(sentences, ["발매"]) or ""
    return [
        "아이오아이의 신곡을 두고 반응이 갈리고 있습니다. 데뷔 10주년을 기념한 미니앨범 소식이라 기대가 컸던 만큼, 먼저 공개된 짧은 챌린지 영상에도 말이 많았습니다.",
        soften_sentence(release, 180) if release else "아이오아이는 데뷔 10주년을 기념한 새 앨범을 준비하고 있습니다.",
        "기사에는 '난해하다'거나 곡 선정이 아쉽다는 반응과, '묘한 중독성이 있다'며 좋게 보는 반응이 함께 소개됐습니다.",
    ]


def sensitive_news_summary(item: dict, sentences: list[str]) -> list[str]:
    entity = lead_entity(item)
    claim = sentence_with(sentences, ["주장"]) or first_meaningful_sentence(sentences)
    broadcast = sentence_with(sentences, ["순자", "눈물"]) or sentence_with(sentences, ["방송"])
    edit = sentence_with(sentences, ["편집", "요청"]) or sentence_with(sentences, ["삭제"])
    paragraphs = [
        (
            f"{entity} 관련 보도에는 온라인 익명 커뮤니티에서 나온 주장과 방송 장면이 함께 들어갔습니다. "
            f"{claim_line(claim)}"
        )
    ]
    if broadcast:
        paragraphs.append(
            f"방송에서는 출연자들 사이의 장면도 다시 언급됐습니다. {soften_sentence(broadcast, 170)}"
        )
    if edit and edit != broadcast:
        paragraphs.append(
            f"편집 요청 주장도 기사에 들어갔습니다. {edit_claim_line(edit)} "
            "그 뒤 미공개 영상 삭제와 방송 분량 이야기가 함께 거론됐습니다."
        )
    else:
        paragraphs.append(
            "임신설과 편집 요구설이 같이 언급되면서 관련 보도가 빠르게 퍼졌습니다. "
            "방송에서 나온 장면과 온라인 글이 같은 기사 안에 담겼습니다."
        )
    return paragraphs[:3]


def general_news_summary(item: dict, sentences: list[str]) -> list[str]:
    title = clean_text(item.get("title", ""))
    if "한예리" in title and ("백상" in title or "워스트" in title):
        return hanyeri_style_summary(sentences)
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return ioi_song_summary(sentences)

    first = first_meaningful_sentence(sentences)
    quotes = quoted_phrases(sentences)
    reaction = (
        sentence_with(sentences, ["온라인"])
        or sentence_with(sentences, ["SNS"])
        or sentence_with(sentences, ["반응"])
        or sentence_with(sentences, ["논란"])
    )
    context = (
        sentence_with(sentences, ["참석"])
        or sentence_with(sentences, ["방송"])
        or sentence_with(sentences, ["발매"])
        or sentence_with(sentences, ["신곡"])
        or sentence_with(sentences, ["공개"])
        or sentence_with(sentences, ["챌린지"])
        or sentence_with(sentences, ["출연"])
    )

    selected: list[str] = []

    def add_sentence(sentence: str) -> None:
        cleaned = soften_sentence(sentence, 180)
        if cleaned and cleaned not in selected:
            selected.append(cleaned)

    add_sentence(first)
    if context and context != first:
        add_sentence(context)

    if quotes:
        quote = excerpt(quotes[0], 95)
        selected.append(f"당사자 발언도 함께 나왔습니다. \"{quote}\"라는 말이 기사에서 주요하게 다뤄졌습니다.")

    reaction_text = soften_sentence(reaction, 180) if reaction else ""
    if reaction_text and reaction_text not in selected:
        selected.append(f"기사 안에는 이런 반응도 함께 언급됐습니다. {reaction_text}")

    for sentence in sentences:
        if len(selected) >= 3:
            break
        add_sentence(sentence)
    return selected[:3] or [core_summary_fallback(item)]


def news_summary_paragraphs(item: dict) -> list[str]:
    title = clean_text(item.get("title", ""))
    sentences = article_sentences(item)
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return [
            (
                "이번 내용은 JTBC 예능 '냉장고를 부탁해' 예고에서 나온 이야기입니다. "
                "결혼 8년 차 강남·이상화 부부의 냉장고가 공개되는 예고에서, 국가대표 출신 아내를 둔 남편들의 이야기가 함께 나왔습니다."
            ),
            (
                "강남은 이상화의 철저한 건강 관리 아래 사는 일상을 이야기했고, 왕십리에서 용산 집까지 뛰어갔던 일화도 꺼냈습니다. "
                "고우림은 김연아의 순발력과 반응 속도를 언급하면서 자연스럽게 부부들의 현실 토크가 이어졌습니다."
            ),
            (
                "제목으로 가장 크게 잡힌 부분은 고우림이 '김연아와 한 번도 싸운 적이 없다'고 말하자, "
                "강남이 '혼난 적 있잖아'라고 받아친 장면입니다. 강남 특유의 농담이 섞이면서 예고편에서도 이 대화가 먼저 보였습니다."
            ),
        ]
    if sentences and item.get("safety_flags"):
        return sensitive_news_summary(item, sentences)
    if sentences:
        return general_news_summary(item, sentences)
    return [core_summary_fallback(item)]


def section_fact(sentence: str, fallback: str) -> str:
    fact = soften_sentence(sentence, 220) if sentence else fallback
    return fact


def pick_section_sentence(sentences: list[str], keywords: list[str], used: set[str]) -> str:
    for sentence in sentences:
        cleaned = strip_article_noise(sentence)
        if cleaned in used:
            continue
        if any(keyword in cleaned for keyword in keywords):
            used.add(cleaned)
            return sentence
    for sentence in sentences:
        cleaned = strip_article_noise(sentence)
        if cleaned and cleaned not in used:
            used.add(cleaned)
            return sentence
    return ""


def hanyeri_blog_sections(item: dict) -> list[tuple[str, list[str]]]:
    return [
        (
            "워스트 드레서로 언급된 드레스",
            [
                "한예리는 제62회 백상예술대상 레드카펫에 꽃 장식이 크게 들어간 화이트 드레스를 입고 참석했습니다. 기사에서 크게 잡힌 부분은 이 드레스가 일부 온라인에서 '워스트 드레서'로 언급됐다는 점이었습니다.",
                "드레스는 상체 쪽 꽃 장식이 크게 들어간 디자인이라 사진만 봐도 시선이 먼저 갔습니다. 그래서 레드카펫 의상 자체보다 그 장식을 두고 나온 말들이 기사에 함께 나왔습니다.",
            ],
        ),
        (
            "한예리가 직접 남긴 말",
            [
                "한예리는 이후 직접 글을 올렸습니다. 그는 누가 뭐래도 자신의 드레스가 가장 예뻤고, 입고 싶은 드레스를 입었을 뿐이라는 취지로 이야기했습니다.",
                "글에는 스태프들이 최선을 다해줬다는 말도 들어 있었습니다. 시상식 드레스가 매번 무난할 필요는 없다는 생각도 함께 전했습니다.",
            ],
        ),
        (
            "달걀프라이 반응까지 나온 장식",
            [
                "온라인에서는 가슴 부분의 꽃 장식을 두고 '달걀프라이 같다'는 식의 반응도 나왔습니다. 이 표현이 함께 돌면서 드레스 이야기도 더 크게 번졌습니다.",
                "드레스 자체는 꽃 장식이 시선을 확 잡는 디자인이었습니다. 한예리도 그 반응을 피하기보다, 자신이 입고 싶었던 드레스였고 충분히 아름다웠다는 쪽으로 이야기를 꺼냈습니다.",
            ],
        ),
        (
            "무난하지 않아도 된다는 선택",
            [
                "한예리가 남긴 글은 길게 맞받아치는 방식은 아니었습니다. 자신이 고른 스타일이고, 그 순간에는 충분히 아름다웠다는 말을 비교적 담담하게 남겼습니다.",
                "레드카펫 의상은 늘 호불호가 갈리지만, 본인이 선택한 스타일을 스스로 좋았다고 말한 모습만큼은 더 응원하게 되는 것 같습니다.",
            ],
        ),
    ]


def ioi_blog_sections(item: dict) -> list[tuple[str, list[str]]]:
    return [
        (
            "갑자기 공개된 챌린지",
            [
                "아이오아이 신곡 이야기는 타이틀곡 '갑자기' 챌린지가 먼저 공개되면서 시작됐습니다. 제목 그대로 갑자기 나온 짧은 구간이라 팬들 입장에서는 반응이 빨리 갈릴 수밖에 없었습니다.",
                "영상으로 먼저 들린 건 곡 전체가 아니라 일부 구간이었습니다. 그래도 10주년 앨범을 기다리던 팬들에게는 그 짧은 구간도 꽤 크게 들릴 수밖에 없었습니다.",
            ],
        ),
        (
            "10주년 앨범 루프",
            [
                "기사에 따르면 아이오아이는 데뷔 10주년을 기념해 세 번째 미니앨범 '루프'를 발매합니다. 오랜만에 팀 이름으로 나오는 소식이라 팬들의 기대도 자연스럽게 커졌습니다.",
                "미니앨범 제목과 발매 소식이 먼저 알려진 뒤 챌린지 영상이 공개됐습니다. 팀을 오래 기다린 팬들 입장에서는 신곡 한 곡보다 10주년이라는 시간이 같이 보이는 소식이었습니다.",
            ],
        ),
        (
            "엇갈린 신곡 반응",
            [
                "기사에는 곡 분위기를 두고 아쉽다는 반응과 묘하게 중독성이 있다는 반응이 함께 소개됐습니다. 일부는 트로트 느낌이 난다고 봤고, 일부는 오히려 그 점이 기억에 남는다고 본 셈입니다.",
                "먼저 공개된 구간만 두고 말이 나온 만큼 전체 곡이 공개되면 분위기는 또 달라질 수 있습니다. 지금은 짧은 챌린지 영상에서 받은 첫인상이 기사에 먼저 담긴 상황입니다.",
            ],
        ),
        (
            "강미나 이름까지 함께 언급",
            [
                "강미나 이름도 함께 언급됐습니다. 신곡 반응이 갈리다 보니, 참여 여부나 팀 활동을 둘러싼 팬들의 아쉬움도 같이 나온 것으로 보입니다.",
                "아이오아이 이름으로 나오는 10주년 소식인 만큼 기대와 아쉬움이 같이 보였습니다. 그래도 오래 기다린 팬들에게 반가운 활동으로 이어지길 바랍니다.",
            ],
        ),
    ]


def sensitive_blog_sections(item: dict) -> list[tuple[str, list[str]]]:
    entity = lead_entity(item)
    sentences = article_sentences(item)
    used: set[str] = set()
    claim = pick_section_sentence(sentences, ["주장", "커뮤니티", "게시글", "임신"], used)
    broadcast = sentence_with(sentences, ["순자", "눈물"]) or pick_section_sentence(sentences, ["방송", "장면", "출연자"], used)
    video = sentence_with(sentences, ["미공개", "삭제"]) or pick_section_sentence(sentences, ["초상집", "질투"], used)
    return [
        (
            "익명 글에서 나온 임신설",
            [
                section_fact(claim, f"{entity} 관련 이야기는 온라인에서 나온 주장성 내용과 함께 커졌습니다."),
                "작성자는 임신 상태와 절대안정 진단을 언급했고, 제작진에게 편집을 요청했다는 취지의 말까지 적었습니다. 이 익명 글이 이번 이야기의 출발점이 됐습니다.",
            ],
        ),
        (
            "순자 눈물 장면",
            [
                section_fact(broadcast, "방송에서는 순자가 눈물을 보인 장면도 함께 언급됐습니다."),
                "시청자들이 먼저 반응한 부분도 이 장면이었습니다. 순자가 문 뒤에서 우는 모습이 나온 뒤, 출연자들 사이 분위기를 두고 여러 말이 나왔습니다.",
            ],
        ),
        (
            "미공개 영상 삭제",
            [
                section_fact(video, "유튜브 미공개 영상 삭제도 기사에서 함께 언급됐습니다."),
                "해당 영상에는 순자를 향한 발언이 담겼고, 비판 여론이 나온 뒤 이틀 만에 삭제됐다는 내용이 나왔습니다. 방송 본편뿐 아니라 미공개 영상까지 같이 회자된 셈입니다.",
            ],
        ),
        (
            "편집 요청 주장",
            [
                "익명 글에는 제작진에게 편집을 요청했다는 내용도 들어 있었습니다. 처음에는 거절됐지만 이후 다시 요청해 받아들여졌다는 식의 주장입니다.",
                "이후 방송 분량을 두고도 댓글에서 여러 말이 나왔습니다. 여러 추측이 너무 거칠게 번지기보다 방송 안팎의 이야기가 차분하게 정리되길 바랍니다.",
            ],
        ),
    ]


def drunk_driving_blog_sections(item: dict) -> list[tuple[str, list[str]]]:
    sentences = article_sentences(item)
    used: set[str] = set()
    first = pick_section_sentence(sentences, ["음주운전", "물의", "범행"], used)
    trial = pick_section_sentence(sentences, ["재판", "도주", "혐의"], used)
    blackbox = pick_section_sentence(sentences, ["블랙박스", "저장장치", "여자친구"], used)
    past = pick_section_sentence(sentences, ["2018", "실형", "군", "면제"], used)
    return [
        (
            "다시 나온 음주운전 보도",
            [
                section_fact(first, "손승원 음주운전 관련 보도가 다시 나왔습니다."),
                "기사에는 과거 음주운전 이력도 함께 언급됐습니다. 이미 같은 문제로 크게 다뤄진 적이 있어서 이번 보도는 재판 소식과 과거 이력이 같이 읽혔습니다.",
            ],
        ),
        (
            "재판에서 언급된 혐의",
            [
                section_fact(trial, "기사에는 음주운전 사고와 도주 혐의가 함께 언급됐습니다."),
                "법적 판단은 재판 절차에서 확인될 부분입니다. 다만 기사에 나온 내용만 봐도 음주운전, 사고, 도주 혐의가 함께 묶여 있어 사안이 가볍지 않아 보입니다.",
            ],
        ),
        (
            "블랙박스 저장장치 이야기",
            [
                section_fact(blackbox, "기사에는 사건 직후 블랙박스 저장장치와 관련한 정황도 담겼습니다."),
                "보도에는 사고 이후의 정황도 함께 들어갔습니다. 음주운전 자체뿐 아니라 이후 어떤 부탁이 오갔는지까지 기사에 담긴 셈입니다.",
            ],
        ),
        (
            "과거 음주운전 이력",
            [
                section_fact(past, "과거 음주운전 이력도 기사에서 다시 언급됐습니다."),
                "과거 실형과 군 면제 이야기까지 다시 소환되면서 기사 무게가 더 커졌습니다. 이번 일을 계기로 같은 문제가 반복되지 않고 책임 있는 모습으로 정리되길 바랍니다.",
            ],
        ),
    ]


def category_blog_blueprints(item: dict) -> list[tuple[str, list[str], str]]:
    title = clean_text(item.get("title", ""))
    if has_title_keywords(item, ["위경련", "탈수", "불참"]):
        return [
            ("연달아 비운 대학 축제 무대", ["불참", "축제", "일정"], "12일 상지대학교 축제에 이어 14일 단국대학교와 성균관대학교 축제까지 빠지면서 팬들 걱정도 같이 커졌습니다."),
            ("위경련과 탈수 증세", ["위경련", "탈수", "증세"], "보도에 따르면 위경련과 탈수 증세가 함께 언급됐습니다. 축제 시즌은 이동과 리허설, 본무대가 이어지는 일정이라 몸 상태 이야기가 먼저 보였습니다."),
            ("소속사가 전한 휴식과 안정", ["소속사", "휴식", "안정"], "소속사 측은 빠른 컨디션 회복을 위해 휴식과 안정을 취하고 있다고 밝혔습니다. 팬들에게 양해를 부탁했다는 내용도 함께 전해졌습니다."),
            ("컴백을 앞둔 프로미스나인", ["컴백", "앨범", "활동", "예정"], "프로미스나인은 7월 정규 앨범 컴백을 앞두고 있습니다. 지금은 무리한 일정이 이어지기보다 건강하게 회복해 반가운 무대로 돌아오길 바랍니다."),
        ]
    if has_title_keywords(item, ["시험관", "난임센터"]):
        return [
            ("시험관 시술 중 전한 근황", ["시험관", "시술", "근황"], "방송에서 나온 말이지만 김지민이 지금 겪고 있는 상황을 직접 꺼낸 장면이라 꽤 담담하게 들렸습니다."),
            ("난임센터에서 본 현실", ["난임센터", "병원", "사람"], "난임센터에 사람이 많아 앉을 곳도 없었다는 말은 짧았지만 꽤 현실적으로 들렸습니다. 비슷한 시간을 지나본 사람이라면 그냥 웃고 넘기기 어려운 대목이지 않을까 싶습니다."),
            ("반복되는 시도의 무게", ["여러 번", "지쳐", "실패", "마음"], "시험관 과정은 결과만 놓고 말하기 어려운 시간입니다. 기사에서도 그 과정에서 느낀 피로와 마음이 같이 묻어났습니다."),
            ("방송에서 이어질 이야기", ["방송", "사연", "공개"], "프로그램 안에서는 다른 사연과 함께 이어질 예정입니다. 쉽지 않은 과정을 담담하게 꺼낸 만큼 좋은 소식으로 이어지길 조용히 응원하게 됩니다."),
        ]
    if has_title_keywords(item, ["니요", "동시 연애", "관계"]):
        return [
            ("세 사람과 함께 지내는 관계", ["세 명", "동시에", "한집", "교제"], "기사에서 먼저 잡힌 건 세 사람과 함께 지내는 현재 관계였습니다. 니요는 이 관계가 어떤 식으로 유지되고 있는지 직접 설명했습니다."),
            ("선택권을 줬다는 설명", ["선택권", "자발", "동의"], "이 대목은 단순한 스캔들식 이야기와 구분되는 부분입니다. 본인은 모두가 상황을 알고 선택했다는 설명을 강조한 것으로 보입니다."),
            ("아이들과 생활한다는 부분", ["아이", "생활", "함께"], "기사에서는 아이들과 함께 생활한다는 내용도 따로 언급됐습니다. 관계 설명에 가족 생활까지 들어가며 소식의 결이 더 복잡해졌습니다."),
            ("계약 무산까지 언급", ["계약", "비즈니스", "무산"], "공개 이후 실제 활동에도 영향이 있었다는 점도 기사에 함께 들어갔습니다. 낯설게 느끼는 반응도 있겠지만 서로 존중하는 방식으로 잘 지내는지가 가장 중요해 보입니다."),
        ]
    return [
        ("처음 공개된 장면", ["공개", "밝", "전했", "올렸", "출연"], f"{lead_entity(item)} 관련 소식은 기사 첫 장면에서 시작됩니다. 누가 어디서 어떤 말을 꺼냈는지가 먼저 잡혔습니다."),
        ("기사에 담긴 발언", ["핵심", "설명", "언급", "발언", "입장"], "기사에는 당사자가 직접 남긴 말이나 방송에서 나온 장면이 함께 들어 있습니다. 그 말이 나온 상황을 먼저 가져왔습니다."),
        ("사람들이 말한 부분", ["반응", "온라인", "SNS", "논란", "시청자"], "온라인에서는 기사 속 장면이나 발언을 두고 이런저런 말이 이어졌습니다. 그중 반복해서 나온 말이 기사에도 함께 담겼습니다."),
        ("이어질 일정과 배경", ["예정", "향후", "앞두", "다음", "계속"], "기사에는 이후 일정이나 최근 활동도 함께 언급됐습니다. 짧은 소식이어도 좋은 방향으로 이어질 만한 부분이 있다면 다음 이야기에서 자연스럽게 더 보일 것 같습니다."),
    ]


def generic_blog_sections(item: dict) -> list[tuple[str, list[str]]]:
    sentences = article_sentences(item)
    used: set[str] = set()
    sections: list[tuple[str, list[str]]] = []
    for heading, keywords, reflection in category_blog_blueprints(item):
        sentence = pick_section_sentence(sentences, keywords, used)
        fact = section_fact(sentence, core_summary_fallback(item))
        sections.append((heading, [fact, reflection]))
    return sections


def reference_blog_sections(item: dict, related_articles: list[dict]) -> list[tuple[str, list[str]]]:
    title = clean_text(item.get("title", ""))
    if "한예리" in title and ("백상" in title or "워스트" in title):
        return hanyeri_blog_sections(item)
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return ioi_blog_sections(item)
    if "손승원" in title and "음주운전" in title:
        return drunk_driving_blog_sections(item)
    if item.get("safety_flags"):
        return sensitive_blog_sections(item)
    return generic_blog_sections(item)


def render_issue_sections(sections: list[tuple[str, list[str]]], image_blocks: dict[str, str]) -> str:
    chunks: list[str] = []
    for index, (heading, paragraphs) in enumerate(sections, start=1):
        paragraph_html = "\n".join(f"      <p>{escape(paragraph)}</p>" for paragraph in paragraphs)
        image_html = ""
        if index == 2 and image_blocks["core"]:
            image_html = "\n" + image_blocks["core"]
        chunks.append(
            f"""    <section id="issue-{index}">
      <h2>{escape(heading)}</h2>
{paragraph_html}{image_html}
    </section>"""
        )
    return "\n\n".join(chunks)


def core_summary_fallback(item: dict) -> str:
    entity = lead_entity(item)
    particle = object_particle(entity)
    title = clean_text(item.get("title", ""))
    if "부부싸움" in title or "목격담" in title:
        return (
            f"이번 이야기는 {entity}{particle} 둘러싼 일상적인 에피소드가 예능 맥락에서 언급되며 나온 내용입니다. "
            "제목만 보면 크게 느껴질 수 있지만, 실제로는 방송에서 나온 짧은 말과 주변 반응이 기사로 이어진 쪽에 가깝습니다."
        )
    if item.get("safety_flags"):
        return (
            f"이번 이야기는 {entity}{particle} 둘러싼 방송 장면에 온라인 이야기가 더해지면서 커졌습니다. "
            "기사에는 자주 언급된 단어와 시청자 반응이 함께 담겼습니다."
        )
    return (
        f"{entity}{particle} 둘러싼 최근 소식입니다. "
        "기사에 나온 발언과 상황을 중심으로 풀었습니다."
    )


def article_reaction_sentence(item: dict) -> str:
    sentences = article_sentences(item)
    skip_keywords = ["주장", "작성자", "게시글", "커뮤니티를 중심", "제기"]
    priority_groups = [
        ["일각에서는"],
        ["누리꾼"],
        ["네티즌"],
        ["호불호"],
        ["달걀프라이"],
        ["비판"],
        ["혹평"],
        ["반응"],
        ["온라인상"],
        ["SNS"],
    ]
    for group in priority_groups:
        for index, sentence in enumerate(sentences):
            if not any(keyword in sentence for keyword in group):
                continue
            if any(skip in sentence for skip in skip_keywords):
                continue
            if sentence.startswith("누리꾼들의 반응") and index + 1 < len(sentences):
                return sentences[index + 1]
            return sentence
    return ""


def has_title_keywords(item: dict, keywords: list[str]) -> bool:
    title = clean_text(item.get("title", ""))
    return any(keyword in title for keyword in keywords)


def section_two_heading(item: dict) -> str:
    if has_title_keywords(item, ["한예리"]) and has_title_keywords(item, ["백상", "워스트"]):
        return "한예리가 직접 남긴 말"
    if has_title_keywords(item, ["아이오아이"]) and has_title_keywords(item, ["신곡", "반응", "강미나"]):
        return "아이오아이 10주년 신곡"
    if item.get("safety_flags"):
        return "기사에 나온 내용과 주장성 표현"
    if has_title_keywords(item, ["위경련", "탈수", "불참"]):
        return "건강 문제로 빠진 일정"
    if has_title_keywords(item, ["컴백", "신곡", "발매", "챌린지"]):
        return "신곡 공개와 반응"
    if has_title_keywords(item, ["니요", "동시 연애", "관계"]):
        return "니요가 밝힌 관계"
    return "기사에서 나온 내용"


def section_four_heading(item: dict) -> str:
    if has_title_keywords(item, ["한예리"]) and has_title_keywords(item, ["백상", "워스트"]):
        return "워스트 반응보다 남은 말"
    if has_title_keywords(item, ["아이오아이"]) and has_title_keywords(item, ["신곡", "반응", "강미나"]):
        return "곡 분위기에 갈린 의견"
    if item.get("safety_flags"):
        return "이어진 방송 이야기"
    if has_title_keywords(item, ["위경련", "탈수", "불참"]):
        return "소속사가 전한 휴식과 안정"
    if has_title_keywords(item, ["컴백", "신곡", "발매", "챌린지"]):
        return "함께 볼 배경"
    return "이어진 장면"


def contextual_sentence(item: dict, preferred_keywords: list[str] | None = None) -> str:
    sentences = article_sentences(item)
    if not sentences:
        return ""
    preferred_keywords = preferred_keywords or []
    if preferred_keywords:
        for sentence in sentences:
            if any(keyword in sentence for keyword in preferred_keywords):
                return sentence
    reaction = article_reaction_sentence(item)
    for sentence in sentences[1:]:
        if sentence != reaction:
            return sentence
    return sentences[0]


def interest_paragraph(item: dict, related_articles: list[dict]) -> str:
    terms = keyword_terms(item)
    term_text = "·".join(terms[:4])
    title = clean_text(item.get("title", ""))
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return (
            "이 이야기는 김연아·고우림 부부와 강남·이상화 부부의 예능 토크가 함께 기사화됐습니다. "
            "실제 내용은 부부 갈등이라기보다 방송 예고 속 짧은 대화에 가깝습니다."
        )
    if "한예리" in title and ("백상" in title or "워스트" in title):
        return (
            "기사에서 먼저 보이는 건 '워스트 드레서'나 '달걀프라이' 같은 반응이지만, "
            "실제로는 한예리가 자신이 고른 드레스를 두고 직접 입장을 남긴 내용입니다."
        )
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "이번 이슈는 컴백 자체보다 먼저 공개된 타이틀곡 '갑자기' 챌린지 반응에서 시작됐습니다. "
            "짧은 구간만 공개된 상태라 전체 곡 분위기는 본 발매 이후 다시 이어질 가능성이 있습니다."
        )
    if item.get("safety_flags"):
        return (
            "이슈가 된 부분은 임신설, 편집 요구설, 통편집설 같은 표현이 방송 장면과 함께 묶였다는 점입니다. "
            "기사 안에서는 방송에 나온 장면과 온라인 주장성 표현이 함께 다뤄졌습니다."
        )
    context = contextual_sentence(item, ["발매", "공개", "출연", "소속사", "휴식", "안정", "관계", "선택권"])
    if context:
        return soften_sentence(context, 190)
    return f"기사에서 반복해서 언급된 단어는 {term_text}입니다. 기사에 나온 내용은 이 단어들을 중심으로 이어졌습니다."


def public_reaction_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    reaction = article_reaction_sentence(item)
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return (
            "기사 내용만 보면 실제 부부싸움을 확인한 이야기는 아닙니다. "
            "강남이 예능식으로 받아친 말이 제목에 크게 잡힌 쪽에 가깝습니다."
        )
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "기사에 언급된 반응은 꽤 갈립니다. '난해하다'는 쪽도 있고, "
            "'한 번 들어도 흥얼거리게 된다'며 좋게 보는 쪽도 함께 나왔습니다."
        )
    if reaction:
        return f"기사 안에 언급된 반응만 보면, {soften_sentence(reaction, 190)}"
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 반응은 방송 장면을 본 시청자 의견에 온라인 이야기가 더해지면서 커졌습니다. "
            "처음에는 장면에 대한 불편함이었고, 이후에는 편집 이야기까지 나오면서 말이 더 많아진 분위기입니다."
        )
    return (
        f"{entity} 관련 반응은 아직 기사 안에 길게 담기지는 않았습니다. "
        "현재 기사에는 언급된 발언과 상황이 짧게 들어갔습니다."
    )


def extra_context_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return (
            "예능에서는 짧은 농담이 제목으로 크게 잡히는 경우가 많습니다. "
            "이번 내용도 실제 갈등보다는 방송에서 나온 생활형 에피소드에 가깝습니다."
        )
    if "한예리" in title and ("백상" in title or "워스트" in title):
        return (
            "이 소식은 드레스 평가보다 한예리가 직접 남긴 말이 더 크게 남습니다. "
            "본인이 입고 싶은 드레스를 입었고, 그 선택에 만족했다는 말을 직접 남겼습니다."
        )
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "아직은 챌린지로 공개된 일부 구간만 두고 나온 반응입니다. "
            "전체 음원이 공개되면 지금과는 다른 평가가 나올 수도 있습니다."
        )
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 이야기는 여러 표현이 한꺼번에 묶여 기사로 나왔습니다. "
            "방송 장면과 온라인에서 나온 말이 같은 기사 안에 함께 들어갔습니다."
        )
    context = contextual_sentence(item, ["소속사", "휴식", "안정", "컴백", "앨범", "일정", "선택권", "자발", "동의"])
    if context:
        return soften_sentence(context, 190)
    return (
        "지금 나온 내용만 보면 크게 덧붙일 부분은 많지 않습니다. "
        "기사에 나온 발언과 상황이 짧게 이어진 소식이었습니다."
    )


def closing_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return (
            "이번 이야기는 김연아·고우림 부부의 갈등이라기보다, 예능 예고 속 짧은 대화가 기사로 커진 경우였습니다. "
            "방송이 공개되면 실제 분위기는 더 가볍게 느껴질 가능성이 크고, 두 부부의 편안한 예능 케미도 함께 볼 수 있을 것 같습니다."
        )
    if "손승원" in title and "음주운전" in title:
        return (
            "손승원 음주운전 보도는 읽는 사람 입장에서도 씁쓸함이 남는 이야기였습니다. "
            "무겁게 남는 사안인 만큼, 앞으로는 같은 일이 반복되지 않고 책임 있는 모습으로 다시 정리되길 바랍니다."
        )
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 이야기는 방송 장면과 온라인 반응이 한꺼번에 엮이면서 생각보다 크게 번졌습니다. "
            "여러 말이 오가는 중이지만, 방송 안팎의 이야기가 너무 거칠게 번지기보다 차분하게 정리되길 바랍니다."
        )
    if "한예리" in title and ("백상" in title or "워스트" in title):
        return (
            "이번 이야기는 워스트 드레스라는 평가보다 한예리가 직접 남긴 말이 더 크게 와닿았습니다. "
            "호불호는 갈릴 수 있지만, 본인이 선택한 스타일을 스스로 좋았다고 말하는 당당한 모습에서 더욱 응원하게 되는 것 같습니다."
        )
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "아이오아이 신곡 이야기는 기대가 컸던 만큼 첫 반응도 빨리 갈린 것 같습니다. "
            "아직 짧은 구간만 보고 나온 말도 많으니, 전체 곡이 공개된 뒤에는 또 다른 매력이 보일 수도 있겠다는 생각이 듭니다."
        )
    if "김지민" in title and any(keyword in title for keyword in ["시험관", "난임센터"]):
        return (
            "김지민의 이번 이야기는 방송 속 짧은 고백이었지만 꽤 현실적인 무게가 느껴졌습니다. "
            "쉽게 꺼내기 어려운 과정을 담담하게 말한 만큼, 좋은 소식으로 이어지길 조용히 응원하게 됩니다."
        )
    if "니요" in title and any(keyword in title for keyword in ["동시 연애", "관계"]):
        return (
            "니요의 이번 이야기는 관계 형태를 직접 공개하면서 나온 사생활 이슈였습니다. "
            "낯설게 느끼는 반응도 있겠지만, 당사자들이 서로 존중하는 방식으로 잘 지내는지가 결국 가장 중요해 보입니다."
        )
    if related_articles:
        return (
            f"{entity} 이야기는 제목보다 기사에 나온 말과 배경이 먼저 남았습니다. "
            "짧은 소식이어도 좋은 방향으로 이어질 만한 부분이 있다면 다음 이야기에서 자연스럽게 더 보일 것 같습니다."
        )
    return (
        f"{entity} 이야기는 제목보다 기사 안에 나온 말이 먼저 남습니다. "
        "짧은 소식이어도 오늘 나온 장면이 좋은 쪽으로 이어지면 더 반가운 이야기로 남을 것 같습니다."
    )


def render_related_articles(articles: list[dict]) -> str:
    if not articles:
        return "<p>현재 같은 키워드의 보조 기사는 추가로 확인되지 않았습니다.</p>"

    items = "\n".join(
        f"""        <li><a href="{escape(article.get("url", ""))}" title="{escape(article.get("title", ""))}" target="_blank" rel="noopener noreferrer">{escape(article.get("source_name") or article.get("domain") or "원문")} 관련 기사 확인</a></li>"""
        for article in articles[:5]
    )
    return f"""
      <ul class="related-list">
{items}
      </ul>
""".rstrip()


def image_key(image: dict) -> str:
    url = clean_text(image.get("url", ""))
    url = re.sub(r"[?#].*$", "", url)
    if "/orgImg/" in url:
        return url.split("/orgImg/", 1)[1].lstrip("/")
    return url.rsplit("/", 1)[-1] or url


def image_quality_score(image: dict) -> int:
    url = clean_text(image.get("url", ""))
    source_url = clean_text(image.get("source_article_url") or "")
    score = 0
    if "googleusercontent.com" in url:
        score -= 100
    if "view610" in url:
        score += 40
    if "orgImg" in url:
        score += 20
    if "news90" in url or "mnews90" in url:
        score -= 30
    if source_url and "news.nate.com" in source_url:
        score += 10
    return score


def selected_images(images: list[dict], limit: int = 2) -> list[dict]:
    best_by_key: dict[str, dict] = {}
    for image in images:
        url = clean_text(image.get("url", ""))
        if not url or "googleusercontent.com" in url:
            continue
        key = image_key(image)
        current = best_by_key.get(key)
        if current is None or image_quality_score(image) > image_quality_score(current):
            best_by_key[key] = image

    selected: list[dict] = []
    seen: set[str] = set()
    high_quality = [image for image in best_by_key.values() if "view610" in clean_text(image.get("url", ""))]
    fallback = [
        image
        for image in best_by_key.values()
        if "news90" not in clean_text(image.get("url", "")) and "mnews90" not in clean_text(image.get("url", ""))
    ]
    pool = high_quality or fallback
    for image in sorted(pool, key=image_quality_score, reverse=True):
        url = clean_text(image.get("url", ""))
        key = image_key(image)
        if key in seen:
            continue
        seen.add(key)
        selected.append(image)
        if len(selected) == limit:
            break
    return selected


def render_image(image: dict, entity: str, caption: str) -> str:
    source_name = clean_text(image.get("source_name") or "원문")
    source_url = clean_text(image.get("source_article_url") or "")
    caption_text = f"{caption} " if caption else ""
    caption_style = "color:#aaa !important;font-size:10px !important;line-height:1.4;margin-top:4px;text-align:right;"
    source_style = "color:#aaa !important;display:block;font-size:10px !important;font-weight:400 !important;line-height:1.4;margin-top:4px;text-align:right;text-decoration:none !important;opacity:.65;"
    return f"""
      <figure class="news-image">
        <img src="{escape(image.get("url", ""))}" alt="{escape(entity)} 관련 이미지" loading="lazy">
        <figcaption style="{caption_style}">{escape(caption_text)}<a href="{escape(source_url)}" target="_blank" rel="noopener noreferrer" style="{source_style}">출처: {escape(source_name)}</a></figcaption>
      </figure>
""".rstrip()


def render_images(item: dict, images: list[dict]) -> dict[str, str]:
    entity = lead_entity(item)
    candidates = selected_images(images)
    blocks = {"intro": "", "core": ""}
    captions = ["", ""]
    for slot, image, caption in zip(blocks, candidates, captions):
        blocks[slot] = render_image(image, entity, caption)
    return blocks


def render_html(item: dict, tags: list[str], related_articles: list[dict] | None = None, images: list[dict] | None = None) -> str:
    title = blog_title(item)
    original_title = compact_title(item)
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    domain = clean_text(item.get("domain") or source_name)
    url = escape(item.get("url", ""))
    tag_text = " ".join(f"#{tag}" for tag in tags)
    related_articles = related_articles or []
    images = images or []
    lead_text = blog_summary(item, related_articles)
    summary = excerpt(lead_text, 150)
    image_blocks = render_images(item, images)
    issue_sections = render_issue_sections(reference_blog_sections(item, related_articles), image_blocks)

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(summary)}">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(summary)}">
  <style>
    body {{
      color: #222;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.75;
      margin: 0;
      padding: 32px 20px;
    }}
    article {{
      margin: 0 auto;
      max-width: 680px;
    }}
    h1, h2 {{
      line-height: 1.35;
    }}
    h1 {{
      font-size: 28px;
      margin: 0 0 18px;
    }}
    h2 {{
      font-size: 21px;
      margin-top: 34px;
    }}
    a {{
      color: #1d4ed8;
    }}
    .lead {{
      background: #f7f7f7;
      border-left: 4px solid #222;
      padding: 14px 16px;
    }}
    .meta {{
      color: #555;
      font-size: 14px;
    }}
    .source-bookmark {{
      border: 1px solid #ddd;
      border-radius: 8px;
      margin: 18px 0 4px;
      padding: 14px 16px;
    }}
    .source-bookmark a {{
      display: inline-block;
      font-weight: 700;
      margin-bottom: 4px;
      text-decoration: none;
    }}
    .source-bookmark span {{
      color: #666;
      display: block;
      font-size: 13px;
    }}
    .news-image {{
      margin: 22px 0;
    }}
    .news-image img {{
      border-radius: 8px;
      display: block;
      height: 420px;
      max-width: 100%;
      object-fit: cover;
      object-position: center;
      width: 100%;
    }}
    .news-image figcaption {{
      color: #aaa;
      font-size: 10px;
      line-height: 1.4;
      margin-top: 4px;
      text-align: right;
    }}
    .news-image figcaption a {{
      color: #aaa !important;
      display: block;
      font-size: 10px;
      font-weight: 400;
      line-height: 1.4;
      margin-top: 4px;
      text-align: right;
      text-decoration: none;
    }}
    .tags {{
      color: #555;
      font-size: 14px;
      margin-top: 28px;
    }}
  </style>
</head>
<body>
  <article>
    <h1>{escape(title)}</h1>
    <p class="lead">{escape(lead_text)}</p>
{image_blocks["intro"]}

{issue_sections}

    <div class="source-bookmark">
      <a href="{url}" target="_blank" rel="noopener noreferrer">원문 기사: {escape(original_title)}</a>
      <span>{escape(domain)}</span>
    </div>

    <p class="tags">{escape(tag_text)}</p>
  </article>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render one Tistory issue post from one collected news item.")
    parser.add_argument("input", type=Path, help="Collected news JSON path.")
    parser.add_argument("--index", type=int, required=True, help="0-based item index to render.")
    parser.add_argument("--output", type=Path, required=True, help="HTML output path.")
    parser.add_argument("--title-output", type=Path, required=True, help="Post title output path.")
    parser.add_argument("--title-candidates-output", type=Path, help="Optional title candidates output path.")
    parser.add_argument("--tags-output", type=Path, required=True, help="Comma-separated tags output path.")
    parser.add_argument("--base-tags", default="", help="Comma-separated fallback tags.")
    parser.add_argument("--enriched", type=Path, help="Optional enriched issue JSON path.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if args.index < 0 or args.index >= len(items):
        raise SystemExit(f"item index out of range: {args.index}")

    item = items[args.index]
    related_articles: list[dict] = []
    image_candidates: list[dict] = []
    if args.enriched:
        enriched = json.loads(args.enriched.read_text(encoding="utf-8"))
        item = enriched.get("item") or item
        related_articles = enriched.get("related_articles") or []
        image_candidates = enriched.get("image_candidates") or []
    base_tags = [tag.strip() for tag in args.base_tags.split(",") if tag.strip()] or DEFAULT_TAGS
    tags = keyword_tags(item, base_tags)
    candidates = title_candidates(item)
    title = candidates[0]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(item, tags, related_articles, image_candidates), encoding="utf-8")
    args.title_output.write_text(title + "\n", encoding="utf-8")
    if args.title_candidates_output:
        args.title_candidates_output.write_text("\n".join(candidates) + "\n", encoding="utf-8")
    args.tags_output.write_text(",".join(tags) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
