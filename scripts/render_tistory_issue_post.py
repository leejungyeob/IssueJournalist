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
    candidates = []
    for term in item.get("attention_terms") or []:
        candidates.append(str(term))
    candidates.extend(re.findall(r"[A-Za-z가-힣0-9]{2,}", clean_text(item.get("title", ""))))
    return candidates


def lead_entity(item: dict) -> str:
    for raw_term in entity_candidates(item):
        term = meaningful_display_term(raw_term)
        if not term:
            continue
        if " " in term or len(term) > 10:
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


def blog_title(item: dict) -> str:
    terms = keyword_terms(item)
    entity = lead_entity(item)
    title = clean_text(item.get("title", ""))
    sensitive_title = any(keyword in title for keyword in ["루머", "의혹", "논란", "폭로", "사생활", "혐의"])
    if sensitive_title:
        return clamp_title(f"{entity} 관련 루머 확산, 현재 확인된 내용만 정리", 64)
    if "컴백" in title or "컴백" in (item.get("important_keywords") or []):
        return clamp_title(f"{entity} 컴백 소식, 팬들이 주목한 포인트 정리", 64)
    if "시청률" in title or "시청률" in (item.get("important_keywords") or []):
        return clamp_title(f"{entity} 시청률 이슈, 반응이 나온 이유 정리", 64)
    if len(terms) >= 2:
        return clamp_title(f"{entity} 관련 소식, 오늘 화제가 된 이유 정리", 64)
    return clamp_title(f"{entity} 관련 소식, 오늘 나온 반응 정리", 64)


def blog_summary(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    related_count = len(related_articles)
    if related_count:
        return (
            f"{entity} 관련 소식이 {source_name} 보도 이후 여러 매체에서 함께 다뤄지고 있습니다. "
            f"단순히 제목만 보고 넘기기보다, 같이 나온 기사 {related_count}건의 흐름을 묶어보면 어떤 지점이 화제가 됐는지 조금 더 선명하게 보입니다."
        )
    return (
        f"{entity} 관련 소식이 올라왔습니다. 이번 글에서는 기사 제목의 자극적인 표현을 그대로 따라가기보다, "
        "확인된 내용과 독자가 궁금해할 만한 포인트를 중심으로 정리했습니다. 원문 보도는 하단 북마크에서 따로 확인할 수 있습니다."
    )


def issue_context(item: dict, related_articles: list[dict]) -> str:
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
            f"이번 이슈는 {pub_date} 기준 {source_name}에서 먼저 확인한 뒤, {source_text} 등에서도 비슷한 키워드로 이어졌습니다. "
            f"여러 기사에서 공통으로 보이는 축은 {entity}{particle} 둘러싼 반응과 후속 관심입니다."
        )
    return f"이번 이슈는 {pub_date} 기준 {source_name} 보도를 바탕으로 확인했습니다. 핵심은 {entity}{particle} 둘러싼 최근 반응입니다."


def keyword_paragraph(item: dict, related_articles: list[dict]) -> str:
    terms = keyword_terms(item)
    term_text = ", ".join(terms[:4])
    if related_articles:
        source_count = len(
            {clean_text(article.get("source_name") or article.get("domain") or "") for article in related_articles}
        )
        return (
            f"눈에 띄는 키워드는 {term_text}입니다. 같은 키워드로 확인한 보조 기사가 {len(related_articles)}건 있고, "
            f"출처 기준으로는 {source_count}곳에서 비슷한 흐름을 다루고 있습니다. 그래서 본문은 제목을 따라 쓰기보다 공통으로 반복되는 포인트만 추려 정리했습니다."
        )
    return f"눈에 띄는 키워드는 {term_text}입니다. 아직 보조 기사는 많지 않지만, 검색 유입 기준으로는 이 키워드 조합이 핵심입니다."


def closing_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 내용은 민감하게 해석될 수 있는 표현이 포함되어 있어 단정적으로 받아들이기보다 "
            "원문 보도와 추가 입장을 함께 확인하는 편이 좋습니다. 후속 보도가 나오면 사실관계 중심으로 다시 정리할 만한 이슈입니다."
        )
    if related_articles:
        return (
            f"정리하면 {entity} 이슈는 한 기사로 끝나는 단발성 소식이라기보다, 여러 매체가 같은 키워드를 따라가고 있는 흐름입니다. "
            "새로운 발언이나 방송 장면, 공식 입장이 나오면 검색량이 한 번 더 움직일 가능성이 있습니다."
        )
    return f"정리하면 {entity} 이슈는 현재 확인된 보도 기준으로 가볍게 체크할 만한 소식입니다. 추가 기사나 공식 입장이 나오면 흐름이 달라질 수 있습니다."


def render_image_block(images: list[dict]) -> str:
    if not images:
        return ""

    primary = images[0]
    source_name = primary.get("source_name", "원문")
    return f"""
      <figure class="news-image">
        <img src="{escape(primary.get("url", ""))}" alt="{escape(source_name)} 관련 뉴스 이미지" loading="lazy">
        <figcaption>이미지 출처: <a href="{escape(primary.get("source_article_url", ""))}" target="_blank" rel="noopener noreferrer">{escape(source_name)}</a></figcaption>
      </figure>
""".rstrip()


def render_image_candidates(images: list[dict]) -> str:
    if len(images) <= 1:
        return ""

    items = "\n".join(
        f"""        <li><a href="{escape(image.get("source_article_url", ""))}" target="_blank" rel="noopener noreferrer">{escape(image.get("source_name", "원문"))}</a> 이미지 후보</li>"""
        for image in images[1:4]
    )
    return f"""
      <ul class="image-candidates">
{items}
      </ul>
""".rstrip()


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
        <p>{escape(source_name)} 보도({escape(pub_date)})를 출발점으로 삼고, 같은 키워드의 보조 기사와 이미지 후보를 함께 확인했습니다.</p>
      </div>
""".rstrip()


def render_html(item: dict, tags: list[str], related_articles: list[dict] | None = None, images: list[dict] | None = None) -> str:
    title = blog_title(item)
    original_title = compact_title(item)
    source_name = clean_text(item.get("source_name") or item.get("domain") or "원문")
    domain = clean_text(item.get("domain") or source_name)
    url = escape(item.get("url", ""))
    pub_date = escape(format_date(item.get("pub_date_kst", "")))
    tag_text = " ".join(f"#{tag}" for tag in tags)
    related_articles = related_articles or []
    images = images or []
    summary = excerpt(blog_summary(item, related_articles), 150)
    primary_image = render_image_block(images)
    image_candidates = render_image_candidates(images)
    related_block = render_related_articles(related_articles)
    fact_box = render_fact_box(item)
    context = issue_context(item, related_articles)
    keyword_body = keyword_paragraph(item, related_articles)
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
        <li><a href="#issue-1">무슨 소식인가</a></li>
        <li><a href="#issue-2">주목할 키워드</a></li>
        <li><a href="#issue-3">정리</a></li>
      </ul>
    </section>

    <section id="issue-1">
      <h2>무슨 일이 있었나</h2>
      <p>{escape(context)}</p>
      <p>기사 문장을 그대로 옮기기보다 흐름만 잡아보면, 이번 소식은 '{escape(lead_entity(item))}' 키워드를 중심으로 관심이 모인 케이스입니다. 아래 기준으로 사실관계만 확인했습니다.</p>
{fact_box}
{primary_image}
      <p class="meta">보도 시각: {pub_date} | 출처: <a href="{url}" target="_blank" rel="noopener noreferrer">{escape(source_name)}</a></p>
    </section>

    <section id="issue-2">
      <h2>왜 관심이 모였나</h2>
      <p>{escape(keyword_body)}</p>
      <p>아래는 같은 키워드로 함께 확인한 보조 기사입니다. 원문을 길게 베껴 쓰지 않고, 어떤 매체들이 같은 흐름을 다뤘는지 확인하는 용도로만 남깁니다.</p>
{related_block}
{image_candidates}
    </section>

    <section id="issue-3">
      <h2>블로그식 정리</h2>
      <p>{escape(closing)}</p>
      <p>이런 유형의 연예 이슈는 제목만 빠르게 퍼질 때 맥락이 흐려지기 쉽습니다. 그래서 본문에서는 확인 가능한 보도와 함께 나온 기사 흐름만 남기고, 추측성 표현은 덜어냈습니다.</p>
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
    title = blog_title(item)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(item, tags, related_articles, image_candidates), encoding="utf-8")
    args.title_output.write_text(title + "\n", encoding="utf-8")
    args.tags_output.write_text(",".join(tags) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
