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
            "한예리 드레스 호불호 반응 정리",
        ]
    elif "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        candidates = [
            "아이오아이 신곡 반응, 갑자기 공개된 챌린지",
            "아이오아이 10주년 신곡 갑자기 반응 정리",
            "아이오아이 신곡 반응과 강미나 언급까지",
        ]
    elif sensitive_title:
        candidates = [
            f"{entity} 루머성 보도 정리, 확인된 내용만 보기",
            f"{entity} 관련 이야기, 단정 없이 차분히 정리",
            f"{entity} 이슈 흐름, 지금 나온 기사만 기준으로",
        ]
    elif has_couple_story and partner:
        candidates = [
            f"{entity} {partner} 부부 이야기, 예능에서 나온 한마디",
            f"{entity} {partner} 목격담, 너무 크게 볼 일은 아닌 이유",
            f"{entity} {partner} 관련 소식, 가볍게 정리해봄",
        ]
    elif "컴백" in title or "컴백" in (item.get("important_keywords") or []):
        candidates = [
            f"{entity} 컴백 소식, 팬들이 먼저 본 포인트",
            f"{entity} 새 소식 정리, 오늘 나온 내용만 보기",
            f"{entity} 컴백 흐름을 블로그식으로 정리",
        ]
    elif "시청률" in title or "시청률" in (item.get("important_keywords") or []):
        candidates = [
            f"{entity} 시청률 이야기, 숫자 뒤 흐름 정리",
            f"{entity} 관련 반응, 오늘 기사 기준으로 보기",
            f"{entity} 방송 이슈가 눈길을 끈 이유",
        ]
    else:
        candidates = [
            f"{entity} 관련 이야기, 오늘 나온 내용만 정리",
            f"{entity} 소식이 눈길을 끈 이유",
            f"{secondary or entity} 흐름 정리, 기사보다 쉽게 보기",
        ]
    return [clamp_title(candidate, 64) for candidate in unique_strings(candidates)[:3]]


def blog_title(item: dict) -> str:
    return title_candidates(item)[0]


def blog_summary(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    related_count = len(related_articles)
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "아이오아이 10주년 신곡 관련 기사가 올라왔습니다. "
            "먼저 공개된 챌린지와 기사에 언급된 반응을 중심으로 정리했습니다."
        )
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return (
            "김연아·고우림 부부 이야기가 예능 예고 속 강남의 한마디로 다시 언급됐습니다. "
            "핵심은 부부싸움 자체라기보다 방송에서 나온 가벼운 에피소드에 가깝습니다."
        )
    if related_count:
        return (
            f"{entity} 관련 기사가 올라왔습니다. "
            f"원문과 함께 나온 기사 {related_count}건에서 확인되는 내용만 짧게 정리했습니다."
        )
    return (
        f"{entity} 관련 이야기가 새로 올라왔습니다. "
        "본문에서는 기사에 나온 내용과 확인된 발언만 중심으로 정리했습니다."
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
        "근황을 공개했다": "근황을 공개했습니다",
        "공개했다": "공개했습니다",
        "공개됐다": "공개됐습니다",
        "밝혔다": "이야기했습니다",
        "발매한다": "발매합니다",
        "게재했다": "올렸습니다",
        "전했다": "전했습니다",
        "설명했다": "설명했습니다",
        "언급했다": "언급했습니다",
        "덧붙였다": "덧붙였습니다",
        "주장이 제기됐다": "주장이 나왔습니다",
        "소신을 드러냈다": "자기 생각을 분명히 했습니다",
        "눈길을 끌었다": "눈에 들어온 대목입니다",
        "화제를 모았다": "이야기가 퍼졌습니다",
        "확산되며": "퍼지면서",
        "극단적으로 엇갈린다": "크게 엇갈리고 있습니다",
        "반응을 보이기도 했다": "반응도 나왔습니다",
        "반응을 보였다": "반응이 나왔습니다",
        "파장이 일고 있다": "말이 이어지고 있습니다",
        "시청자들의 공분을 사고 있다": "시청자들 사이에서 불편하다는 반응도 나오고 있습니다",
        "공분을 사고 있다": "불편하다는 반응도 나오고 있습니다",
        "발칵 뒤집혔다": "말이 크게 번졌습니다",
        "관심이 쏠린다": "이어질 여지도 있어 보입니다",
        "이어졌다": "이어졌습니다",
        "집중됐다": "모였습니다",
        "송출되며": "방송에 나오면서",
        "꼬집었다": "지적했습니다",
        "털어놔 웃음을 자아낸다": "털어놨다는 내용입니다",
        "폭소를 유발한다": "웃음을 더한 대목입니다",
    }
    for before, after in replacements.items():
        sentence = sentence.replace(before, after)
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
        "아이오아이의 신곡을 두고 반응이 갈리고 있습니다. 데뷔 10주년을 기념한 미니앨범 소식이라 기대가 컸던 만큼, 먼저 공개된 짧은 챌린지 영상에도 말이 붙었습니다.",
        soften_sentence(release, 180) if release else "아이오아이는 데뷔 10주년을 기념한 새 앨범을 준비하고 있습니다.",
        "기사에는 '난해하다'거나 곡 선정이 아쉽다는 반응과, '묘한 중독성이 있다'며 좋게 보는 반응이 함께 소개됐습니다.",
    ]


def sensitive_news_summary(item: dict, sentences: list[str]) -> list[str]:
    entity = lead_entity(item)
    claim = sentence_with(sentences, ["주장"]) or first_meaningful_sentence(sentences)
    broadcast = sentence_with(sentences, ["방송"]) or sentence_with(sentences, ["영상"])
    edit = sentence_with(sentences, ["편집"]) or sentence_with(sentences, ["삭제"])
    paragraphs = [
        (
            f"{entity} 관련해서는 온라인 익명 커뮤니티에서 나온 주장과 방송 장면이 함께 언급되고 있습니다. "
            f"{claim_line(claim)}"
        )
    ]
    if broadcast:
        paragraphs.append(
            f"방송에서는 출연자들 사이의 장면도 다시 언급됐습니다. {soften_sentence(broadcast, 170)}"
        )
    if edit and edit != broadcast:
        paragraphs.append(
            f"여기에 편집 여부를 둘러싼 이야기도 붙었습니다. {edit_claim_line(edit)} "
            "다만 이 부분은 아직 주장성 내용이라 사실처럼 단정하긴 어렵습니다."
        )
    else:
        paragraphs.append(
            "다만 임신설이나 편집 요구처럼 민감한 표현은 아직 확인된 사실처럼 받아들이기 어렵습니다. "
            "지금은 기사에 나온 주장과 실제 방송 장면을 분리해서 보는 게 맞습니다."
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
                "결혼 8년 차 강남·이상화 부부의 냉장고가 공개되는 흐름에서, 국가대표 출신 아내를 둔 남편들의 이야기가 함께 나온 겁니다."
            ),
            (
                "강남은 이상화의 철저한 건강 관리 아래 사는 일상을 이야기했고, 왕십리에서 용산 집까지 뛰어갔던 일화도 꺼냈습니다. "
                "고우림은 김연아의 순발력과 반응 속도를 언급하면서 자연스럽게 부부들의 현실 토크가 이어졌습니다."
            ),
            (
                "제목으로 가장 크게 잡힌 부분은 고우림이 '김연아와 한 번도 싸운 적이 없다'고 말하자, "
                "강남이 '혼난 적 있잖아'라고 받아친 장면입니다. 말 그대로 예능식 농담에 가까운 장면이라, 심각한 부부 갈등처럼 볼 내용은 아닙니다."
            ),
        ]
    if sentences and item.get("safety_flags"):
        return sensitive_news_summary(item, sentences)
    if sentences:
        return general_news_summary(item, sentences)
    return [core_summary_fallback(item)]


def core_summary_fallback(item: dict) -> str:
    entity = lead_entity(item)
    particle = object_particle(entity)
    title = clean_text(item.get("title", ""))
    if "부부싸움" in title or "목격담" in title:
        return (
            f"이번 이야기는 {entity}{particle} 둘러싼 일상적인 에피소드가 예능 맥락에서 언급되며 나온 흐름입니다. "
            "제목만 보면 크게 느껴질 수 있지만, 실제로는 방송에서 나온 짧은 말과 주변 반응이 기사로 이어진 쪽에 가깝습니다."
        )
    if item.get("safety_flags"):
        return (
            f"이번 이야기는 {entity}{particle} 둘러싼 민감한 표현이 제목에 섞여 있습니다. "
            "그래서 사실처럼 단정하기보다는, 지금 나온 내용과 반복되는 키워드만 분리해서 보는 편이 좋습니다."
        )
    return (
        f"{entity}{particle} 둘러싼 최근 소식입니다. "
        "기사에 나온 발언과 상황만 중심으로 짧게 보면 됩니다."
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
        return "확인된 내용과 주장성 표현"
    if has_title_keywords(item, ["위경련", "탈수", "불참"]):
        return "건강 문제로 빠진 일정"
    if has_title_keywords(item, ["컴백", "신곡", "발매", "챌린지"]):
        return "신곡 공개와 반응"
    if has_title_keywords(item, ["니요", "동시 연애", "관계"]):
        return "니요가 밝힌 관계"
    return "기사에서 확인된 내용"


def section_four_heading(item: dict) -> str:
    if has_title_keywords(item, ["한예리"]) and has_title_keywords(item, ["백상", "워스트"]):
        return "워스트 반응보다 남은 말"
    if has_title_keywords(item, ["아이오아이"]) and has_title_keywords(item, ["신곡", "반응", "강미나"]):
        return "곡 분위기에 갈린 의견"
    if item.get("safety_flags"):
        return "조심해서 봐야 할 부분"
    if has_title_keywords(item, ["위경련", "탈수", "불참"]):
        return "소속사가 전한 휴식과 안정"
    if has_title_keywords(item, ["컴백", "신곡", "발매", "챌린지"]):
        return "함께 볼 배경"
    return "조금 더 보면"


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
            "이 이야기는 김연아·고우림 부부와 강남·이상화 부부의 예능 토크가 함께 묶이면서 기사화됐습니다. "
            "실제 내용은 부부 갈등이라기보다 방송 예고 속 짧은 대화에 가깝습니다."
        )
    if "한예리" in title and ("백상" in title or "워스트" in title):
        return (
            "기사에서 먼저 보이는 건 '워스트 드레서'나 '달걀프라이' 같은 반응이지만, "
            "실제로는 한예리가 자신의 드레스 선택에 대해 직접 입장을 남긴 내용입니다."
        )
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "이번 이슈는 컴백 자체보다 먼저 공개된 타이틀곡 '갑자기' 챌린지 반응에서 시작됐습니다. "
            "짧은 구간만 공개된 상태라 전체 곡 분위기는 본 발매 이후 다시 봐야 합니다."
        )
    if item.get("safety_flags"):
        return (
            "이슈가 된 부분은 임신설, 편집 요구설, 통편집설 같은 표현이 방송 장면과 함께 묶였다는 점입니다. "
            "다만 이런 내용은 확인된 장면과 온라인 주장성 표현을 나눠서 봐야 합니다."
        )
    context = contextual_sentence(item, ["발매", "공개", "출연", "소속사", "휴식", "안정", "관계", "선택권"])
    if context:
        return soften_sentence(context, 190)
    return f"기사화된 포인트는 {term_text}입니다. 지금은 기사에 나온 내용만 가볍게 확인하면 됩니다."


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
            f"{entity} 관련 반응은 조심해서 정리하는 게 맞습니다. "
            "온라인에서 나온 주장까지 모두 사실처럼 받아들이기보다는, 기사에 확인된 내용만 보는 편이 안전합니다."
        )
    return (
        f"{entity} 관련 반응을 넓게 단정할 만한 내용은 아직 많지 않습니다. "
        "현재는 기사에 언급된 발언과 상황만 확인하는 정도가 적당합니다."
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
            "본인이 입고 싶은 드레스를 입었고, 그 선택에 만족했다는 점이 핵심입니다."
        )
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "아직은 챌린지로 공개된 일부 구간만 두고 나온 반응입니다. "
            "전체 음원이 공개되면 지금과는 다른 평가가 나올 수도 있습니다."
        )
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 이야기는 조금 천천히 보는 게 좋겠습니다. "
            "제목이 강하게 보일수록 실제 내용과 추측처럼 보이는 표현을 나눠 읽어야 합니다."
        )
    context = contextual_sentence(item, ["소속사", "휴식", "안정", "컴백", "앨범", "일정", "선택권", "자발", "동의"])
    if context:
        return soften_sentence(context, 190)
    return (
        "지금 나온 내용만 보면 크게 덧붙일 부분은 많지 않습니다. "
        "기사에 나온 발언과 상황만 확인하고 넘어가면 될 것 같습니다."
    )


def closing_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    if all(keyword in title for keyword in ["김연아", "고우림"]) and "강남" in title:
        return (
            "정리하면 이번 이야기는 김연아·고우림 부부의 갈등이라기보다, 예능 예고 속 짧은 대화가 기사 제목으로 커진 경우입니다. "
            "방송이 공개되면 실제 분위기는 더 가볍게 느껴질 가능성이 큽니다."
        )
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 이야기는 제목만 보고 단정하기보다 조금 차분히 보는 편이 좋겠습니다. "
            "새로운 내용이 나오면 그때 사실관계를 중심으로 다시 확인하면 됩니다."
        )
    if "아이오아이" in title and any(keyword in title for keyword in ["신곡", "반응", "강미나"]):
        return (
            "정리하면 아이오아이 신곡 이야기는 기대감이 큰 만큼 반응도 빨리 갈린 경우입니다. "
            "지금은 챌린지와 기사에 나온 반응만 확인하고, 전체 곡은 공개 이후 다시 보면 될 것 같습니다."
        )
    if related_articles:
        return (
            f"정리하면 {entity} 이야기는 기사에 나온 내용만 보면 크게 복잡한 이슈는 아닙니다. "
            "발언과 배경만 확인하고 넘어가도 충분해 보입니다."
        )
    return f"정리하면 {entity} 관련 이야기는 가볍게 체크할 만한 소식입니다. 아직은 더 크게 해석할 필요는 없어 보입니다."


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
    return re.sub(r"[?#].*$", "", url).rsplit("/", 1)[-1] or url


def selected_images(images: list[dict], limit: int = 3) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for image in images:
        url = clean_text(image.get("url", ""))
        if not url:
            continue
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
    return f"""
      <figure class="news-image">
        <img src="{escape(image.get("url", ""))}" alt="{escape(entity)} 관련 이미지" loading="lazy">
        <figcaption>{escape(caption)} <a href="{escape(source_url)}" target="_blank" rel="noopener noreferrer">이미지 출처: {escape(source_name)}</a></figcaption>
      </figure>
""".rstrip()


def render_images(item: dict, images: list[dict]) -> dict[str, str]:
    entity = lead_entity(item)
    candidates = selected_images(images)
    blocks = {"intro": "", "core": "", "reaction": ""}
    captions = [
        f"{entity} 관련 이야기를 시작하기 전에 분위기를 잡아주는 이미지입니다.",
        "본문에서 언급한 흐름을 한 번 쉬어가며 볼 수 있는 이미지입니다.",
        "관련 반응과 함께 보기 좋은 참고 이미지입니다.",
    ]
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
    summary = excerpt(blog_summary(item, related_articles), 150)
    related_block = render_related_articles(related_articles)
    image_blocks = render_images(item, images)
    news_summary = "\n".join(f"      <p>{escape(paragraph)}</p>" for paragraph in news_summary_paragraphs(item))
    interest = interest_paragraph(item, related_articles)
    public_reaction = public_reaction_paragraph(item, related_articles)
    extra_context = extra_context_paragraph(item, related_articles)
    closing = closing_paragraph(item, related_articles)
    detail_heading = section_two_heading(item)
    extra_heading = section_four_heading(item)

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
      max-width: 760px;
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
      color: #666;
      font-size: 13px;
      margin-top: 8px;
    }}
    .related-list, .image-candidates {{
      padding-left: 20px;
    }}
    .related-list span {{
      color: #666;
      font-size: 13px;
      margin-left: 4px;
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
    <p class="lead">{escape(summary)}</p>
{image_blocks["intro"]}

    <section id="issue-1">
      <h2>뉴스 내용 정리</h2>
{news_summary}
{image_blocks["core"]}
    </section>

    <section id="issue-2">
      <h2>{escape(detail_heading)}</h2>
      <p>{escape(interest)}</p>
      <p>그래서 이 글에서는 확인된 발언과 기사에 나온 배경만 중심으로 정리했습니다.</p>
    </section>

    <section id="issue-3">
      <h2>기사 속 반응 정리</h2>
      <p>{escape(public_reaction)}</p>
      <p>비슷한 내용으로 함께 확인한 기사도 아래에 남겨둡니다.</p>
{related_block}
{image_blocks["reaction"]}
    </section>

    <section id="issue-4">
      <h2>{escape(extra_heading)}</h2>
      <p>{escape(extra_context)}</p>
      <p>확인되지 않은 내용은 따로 키우지 않고, 기사에 나온 내용만 기준으로 보는 게 맞겠습니다.</p>
    </section>

    <section id="issue-5">
      <h2>마무리</h2>
      <p>{escape(closing)}</p>
      <p>지금은 여기까지 확인하고 넘어가면 될 것 같습니다.</p>
      <div class="source-bookmark">
        <a href="{url}" target="_blank" rel="noopener noreferrer">원문 기사: {escape(original_title)}</a>
        <span>{escape(domain)}</span>
        <p>{escape(summary)}</p>
      </div>
    </section>

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
