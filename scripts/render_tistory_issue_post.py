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

    if sensitive_title:
        candidates = [
            f"{entity} 루머성 보도 정리, 확인된 내용만 보기",
            f"{entity} 관련 이야기, 단정 없이 차분히 정리",
            f"{entity} 이슈 흐름, 지금 나온 기사만 기준으로",
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
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    related_count = len(related_articles)
    if related_count:
        return (
            f"{entity} 관련 이야기가 {source_name} 보도 이후 여러 매체에서 이어졌습니다. "
            f"제목만 빠르게 훑기보다, 같이 나온 기사 {related_count}건을 묶어 보면 어떤 부분에서 말이 나왔는지 조금 더 선명하게 보입니다."
        )
    return (
        f"{entity} 관련 새 보도가 올라왔습니다. 이번 글에서는 기사 제목의 자극적인 표현을 그대로 따라가기보다, "
        "확인된 내용과 독자가 궁금해할 만한 포인트를 중심으로 정리했습니다. 원문 보도는 하단 북마크에서 따로 확인할 수 있습니다."
    )


def intro_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    if related_articles:
        return (
            f"{entity} 관련 기사가 여러 곳에서 이어졌습니다. 처음엔 그냥 지나칠 수 있는 연예 소식처럼 보이지만, "
            f"{source_name} 보도와 함께 나온 보조 기사들을 보면 사람들이 어떤 지점을 궁금해했는지 어느 정도 드러납니다."
        )
    return (
        f"{entity} 관련 보도가 새로 나왔습니다. 아직 같은 키워드의 후속 기사가 많지는 않아서, "
        "지금은 원문에 나온 내용과 제목에서 반복되는 포인트를 중심으로 보는 편이 좋겠습니다."
    )


def core_summary(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    particle = object_particle(entity)
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    pub_date = format_date(item.get("pub_date_kst", ""))
    related_sources = []
    for article in related_articles:
        name = clean_text(article.get("source_name") or article.get("domain") or "")
        if name and name not in related_sources:
            related_sources.append(name)
    source_text = ", ".join(related_sources[:3])
    if source_text:
        return (
            f"{pub_date} 기준으로 확인한 출발점은 {source_name} 보도입니다. 이후 {source_text} 등에서도 비슷한 키워드가 보였고, "
            f"공통으로 남는 축은 {entity}{particle} 둘러싼 최근 이야기와 그에 대한 후속 해석입니다."
        )
    return f"{pub_date} 기준으로 확인한 내용은 {source_name} 보도가 중심입니다. 핵심은 {entity}{particle} 둘러싼 최근 이야기입니다."


def interest_paragraph(item: dict, related_articles: list[dict]) -> str:
    terms = keyword_terms(item)
    term_text = ", ".join(terms[:4])
    if related_articles:
        source_count = len(
            {clean_text(article.get("source_name") or article.get("domain") or "") for article in related_articles}
        )
        return (
            f"눈에 띄는 키워드는 {term_text}입니다. 같은 키워드로 확인한 보조 기사가 {len(related_articles)}건, "
            f"출처 기준으로는 {source_count}곳입니다. 한 기사만 보면 자극적인 문장만 남기 쉬운데, 여러 제목을 같이 보면 반복되는 포인트가 조금 정리됩니다."
        )
    return f"눈에 띄는 키워드는 {term_text}입니다. 아직 보조 기사는 많지 않지만, 이 조합이 이번 글을 이해하는 가장 빠른 단서입니다."


def public_reaction_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    terms = keyword_terms(item)
    if related_articles:
        return (
            f"댓글이나 커뮤니티 반응을 직접 확인한 것은 아니기 때문에 대중 반응을 단정하긴 어렵습니다. 다만 보조 기사들이 "
            f"{', '.join(terms[:3])} 같은 단어를 반복해서 다룬 걸 보면, 독자들이 {entity} 자체보다 그 주변 맥락을 더 궁금해한 것으로 보입니다."
        )
    return (
        f"아직 반응을 넓게 묶어 말할 단계는 아닙니다. 지금은 {entity}라는 이름과 함께 나온 핵심 키워드가 먼저 소비되고, "
        "이후 추가 보도나 본인·소속사 입장이 나오면 분위기가 달라질 수 있습니다."
    )


def personal_interpretation(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    if item.get("safety_flags"):
        return (
            f"개인적으로는 이런 종류의 {entity} 이야기는 속도보다 확인이 먼저라고 봅니다. 제목이 강하게 보일수록 "
            "본문에서 실제로 확인된 내용과 추측에 가까운 표현을 나눠 읽는 게 필요합니다."
        )
    if related_articles:
        return (
            f"개인적으로는 이번 흐름이 단순한 단발 기사라기보다, 같은 키워드를 여러 매체가 조금씩 다른 각도로 풀어낸 사례처럼 보입니다. "
            "그래서 원문 한 줄을 그대로 따라가기보다는 반복해서 등장하는 단서만 남기는 쪽이 더 읽기 편합니다."
        )
    return (
        f"개인적으로는 아직 크게 단정할 만한 내용보다는 가볍게 체크할 소식에 가깝다고 봅니다. "
        f"{entity} 관련 후속 기사나 공식 채널 업데이트가 있으면 그때 다시 정리해도 늦지 않습니다."
    )


def closing_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 내용은 민감하게 해석될 수 있는 표현이 섞일 수 있어 단정적으로 받아들이기보다 "
            "원문 보도와 추가 입장을 함께 확인하는 편이 좋겠습니다. 새 보도가 나오면 사실관계 중심으로 다시 정리할 만합니다."
        )
    if related_articles:
        return (
            f"정리하면 {entity} 이야기는 한 기사만 보고 끝낼 내용이라기보다, 여러 매체가 같은 키워드를 따라가며 조금씩 살을 붙인 흐름입니다. "
            "새로운 발언이나 방송 장면, 공식 입장이 나오면 다시 한 번 읽을 거리가 생길 수 있습니다."
        )
    return f"정리하면 {entity} 관련 보도는 현재 확인된 기사 기준으로 가볍게 체크할 만한 소식입니다. 추가 기사나 공식 입장이 나오면 흐름이 달라질 수 있습니다."


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


def render_fact_box(item: dict) -> str:
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    pub_date = format_date(item.get("pub_date_kst", ""))
    return f"""
      <div class="fact-box">
        <strong>확인한 기준</strong>
        <p>{escape(source_name)} 보도({escape(pub_date)})를 출발점으로 삼고, 같은 키워드의 보조 기사와 이미지 삽입 후보를 함께 확인했습니다.</p>
      </div>
""".rstrip()


def render_image_recommendation(position: str, recommendation: str, alt: str, caption: str) -> str:
    return f"""
      <div class="image-recommendation">
        <strong>[이미지 삽입 추천]</strong>
        <p><b>위치:</b> {escape(position)}</p>
        <p><b>추천 이미지:</b> {escape(recommendation)}</p>
        <p><b>alt 태그:</b> {escape(alt)}</p>
        <p><b>캡션:</b> {escape(caption)}</p>
      </div>
""".rstrip()


def render_image_recommendations(item: dict, related_articles: list[dict]) -> dict[str, str]:
    entity = lead_entity(item)
    has_related = bool(related_articles)

    blocks = {
        "intro": render_image_recommendation(
            "도입부 직후",
            f"{entity} 공식 프로필, 소속사 제공 이미지, 방송사 공식 페이지 이미지, 또는 본인 SNS 임베드",
            f"{entity} 관련 공식 이미지",
            f"{entity} 이야기를 시작하기 전에 인물이나 프로그램을 자연스럽게 보여주는 이미지가 좋습니다.",
        ),
        "core": render_image_recommendation(
            "이슈 핵심 정리 이후",
            f"{entity} 또는 관련 프로그램의 방송사 제공 스틸컷, 공식 유튜브 썸네일, 프로그램 공식 이미지",
            f"{entity} 관련 핵심 장면 또는 공식 자료",
            "본문에서 다룬 내용을 한 번 쉬어가며 확인할 수 있는 자료 이미지가 잘 맞습니다.",
        ),
    }
    if has_related:
        blocks["reaction"] = render_image_recommendation(
            "대중 반응 정리 부분 근처",
            f"{entity} 본인 SNS 게시물 임베드, 소속사 공지, 방송사 공식 클립 썸네일 중 합법적으로 사용할 수 있는 자료",
            f"{entity} 관련 공식 채널 반응 자료",
            "반응을 단정하지 않기 위해 캡처 이미지보다 원 게시물 임베드나 공식 채널 자료를 우선 확인하세요.",
        )
    else:
        blocks["reaction"] = ""
    return blocks


def render_html(item: dict, tags: list[str], related_articles: list[dict] | None = None, images: list[dict] | None = None) -> str:
    title = blog_title(item)
    original_title = compact_title(item)
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    domain = clean_text(item.get("domain") or source_name)
    url = escape(item.get("url", ""))
    pub_date = escape(format_date(item.get("pub_date_kst", "")))
    tag_text = " ".join(f"#{tag}" for tag in tags)
    related_articles = related_articles or []
    summary = excerpt(blog_summary(item, related_articles), 150)
    related_block = render_related_articles(related_articles)
    fact_box = render_fact_box(item)
    image_recommendations = render_image_recommendations(item, related_articles)
    intro = intro_paragraph(item, related_articles)
    core = core_summary(item, related_articles)
    interest = interest_paragraph(item, related_articles)
    public_reaction = public_reaction_paragraph(item, related_articles)
    interpretation = personal_interpretation(item, related_articles)
    closing = closing_paragraph(item, related_articles)

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
    .fact-box {{
      background: #fafafa;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      margin: 18px 0;
      padding: 14px 16px;
    }}
    .fact-box p {{
      margin: 6px 0 0;
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
      height: auto;
      max-width: 100%;
    }}
    .news-image figcaption {{
      color: #666;
      font-size: 13px;
      margin-top: 8px;
    }}
    .image-recommendation {{
      background: #f8fafc;
      border: 1px dashed #94a3b8;
      border-radius: 8px;
      color: #334155;
      margin: 22px 0;
      padding: 14px 16px;
    }}
    .image-recommendation p {{
      margin: 6px 0;
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

    <section>
      <h2>한눈에 보는 주요 이슈</h2>
      <ul>
        <li><a href="#issue-1">도입부</a></li>
        <li><a href="#issue-2">이슈 핵심 정리</a></li>
        <li><a href="#issue-3">왜 사람들이 보는지</a></li>
        <li><a href="#issue-4">대중 반응 정리</a></li>
        <li><a href="#issue-5">개인적인 해석</a></li>
        <li><a href="#issue-6">마무리</a></li>
      </ul>
    </section>

    <section id="issue-1">
      <h2>도입부</h2>
      <p>{escape(intro)}</p>
      <p>연예 뉴스는 제목만 보면 내용이 꽤 커 보일 때가 많습니다. 그래서 이번 글에서는 자극적인 표현을 따라가기보다, 지금 확인 가능한 기사 흐름만 블로그식으로 짧게 풀어보겠습니다.</p>
{image_recommendations["intro"]}
    </section>

    <section id="issue-2">
      <h2>이슈 핵심 정리</h2>
      <p>{escape(core)}</p>
      <p>기사 문장을 그대로 옮기기보다 흐름만 잡아보면, 이번 이야기는 '{escape(lead_entity(item))}' 키워드를 중심으로 읽는 편이 가장 자연스럽습니다.</p>
{fact_box}
      <p class="meta">보도 시각: {pub_date} | 출처: <a href="{url}" target="_blank" rel="noopener noreferrer">{escape(source_name)}</a></p>
{image_recommendations["core"]}
    </section>

    <section id="issue-3">
      <h2>왜 사람들이 보는지</h2>
      <p>{escape(interest)}</p>
      <p>연예 이슈는 인물명 하나만으로 소비되기도 하지만, 실제로는 방송 장면, 발언 맥락, 팬들의 기존 기대감이 함께 얽히는 경우가 많습니다.</p>
    </section>

    <section id="issue-4">
      <h2>대중 반응 정리</h2>
      <p>{escape(public_reaction)}</p>
      <p>아래 링크는 같은 키워드로 함께 확인한 보조 기사입니다. 원문을 길게 베껴 쓰지 않고, 어떤 매체들이 비슷한 흐름을 다뤘는지 확인하는 용도로만 남깁니다.</p>
{related_block}
{image_recommendations["reaction"]}
    </section>

    <section id="issue-5">
      <h2>개인적인 해석</h2>
      <p>{escape(interpretation)}</p>
      <p>다만 확인되지 않은 추측까지 얹으면 글이 쉽게 과해질 수 있습니다. 그래서 여기서는 기사에서 확인되는 내용과 반복해서 등장하는 키워드만 남겼습니다.</p>
    </section>

    <section id="issue-6">
      <h2>마무리</h2>
      <p>{escape(closing)}</p>
      <p>연예 소식은 빠르게 읽히는 만큼, 조금만 시간이 지나도 맥락이 바뀔 수 있습니다. 이 글은 현재 확인한 보도 기준의 정리이며, 새 내용이 나오면 원문과 공식 채널을 함께 보는 편이 좋겠습니다.</p>
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
