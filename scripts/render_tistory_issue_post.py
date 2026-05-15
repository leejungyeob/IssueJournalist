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
    has_couple_story = any(term in title or term in terms for term in ["부부싸움", "목격담", "고우림"])
    partner = "고우림" if "고우림" in title or "고우림" in terms else secondary

    if sensitive_title:
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
    related_count = len(related_articles)
    if related_count:
        return (
            f"{entity} 이야기가 예능과 연예 기사 흐름 안에서 다시 언급됐습니다. "
            f"제목만 보면 꽤 크게 느껴질 수 있지만, 함께 나온 기사 {related_count}건을 같이 보면 핵심은 조금 더 단순합니다."
        )
    return (
        f"{entity} 관련 이야기가 새로 올라왔습니다. 제목만 보면 조금 강하게 느껴질 수 있어서, "
        "본문에서는 핵심 내용과 자연스럽게 읽을 만한 포인트만 추려봤습니다."
    )


def core_summary(item: dict, related_articles: list[dict]) -> str:
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
        f"핵심은 {entity}{particle} 둘러싼 최근 이야기입니다. 제목에 여러 단어가 붙어 있지만, "
        "길게 풀어보면 인물과 상황, 그리고 그걸 바라보는 독자들의 궁금증으로 정리됩니다."
    )


def interest_paragraph(item: dict, related_articles: list[dict]) -> str:
    terms = keyword_terms(item)
    term_text = ", ".join(terms[:4])
    if related_articles:
        return (
            f"사람들이 눌러볼 만한 포인트는 {term_text} 쪽입니다. 특히 이름만 보고 들어왔다가도, "
            "막상 읽다 보면 실제로 어떤 상황에서 나온 말인지 궁금해지는 식입니다."
        )
    return f"사람들이 눌러볼 만한 포인트는 {term_text} 쪽입니다. 아직 큰 흐름은 아니지만, 이 조합만으로도 궁금증은 생깁니다."


def public_reaction_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    terms = keyword_terms(item)
    if related_articles:
        return (
            f"반응을 단정해서 말하긴 어렵지만, {', '.join(terms[:3])} 같은 단어가 반복되는 걸 보면 "
            f"사람들은 {entity} 자체보다 그 말이 나온 배경을 더 궁금해하는 분위기입니다."
        )
    return (
        f"아직 반응을 넓게 묶어 말할 정도는 아닙니다. 지금은 {entity}라는 이름과 핵심 키워드가 먼저 소비되는 단계로 보입니다."
    )


def personal_interpretation(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    if item.get("safety_flags"):
        return (
            f"개인적으로는 이런 종류의 {entity} 이야기는 조금 천천히 보는 게 좋다고 생각합니다. "
            "제목이 강하게 보일수록 실제 내용과 추측처럼 보이는 표현을 나눠 읽어야 합니다."
        )
    if related_articles:
        return (
            "개인적으로는 이런 이야기가 너무 크게 소비될 필요는 없다고 봅니다. "
            "다만 익숙한 이름과 생활감 있는 에피소드가 만나면, 가볍게 읽히는 연예 이슈가 되는 건 자연스러운 흐름입니다."
        )
    return (
        "개인적으로는 아직 크게 의미를 붙이기보다는 가볍게 체크할 소식에 가깝다고 봅니다. "
        "후속 내용이 나오면 그때 맥락을 다시 보면 됩니다."
    )


def closing_paragraph(item: dict, related_articles: list[dict]) -> str:
    entity = lead_entity(item)
    if item.get("safety_flags"):
        return (
            f"{entity} 관련 이야기는 제목만 보고 단정하기보다 조금 차분히 보는 편이 좋겠습니다. "
            "새로운 내용이 나오면 그때 사실관계를 중심으로 다시 확인하면 됩니다."
        )
    if related_articles:
        return (
            f"정리하면 {entity} 이야기는 무겁게 볼 이슈라기보다, 방송이나 일상 에피소드가 기사로 이어진 가벼운 읽을거리 쪽에 가깝습니다. "
            "다만 제목만 보고 오해하지 않도록 핵심만 보고 넘어가는 게 좋겠습니다."
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
      <h2>이슈 핵심 정리</h2>
      <p>{escape(core)}</p>
      <p>길게 설명할 필요 없이, 이번 글은 '{escape(lead_entity(item))}'라는 키워드로 보면 가장 쉽게 잡힙니다. 누가 무슨 말을 했고, 왜 그 말이 기사로 이어졌는지만 보면 됩니다.</p>
{image_blocks["core"]}
    </section>

    <section id="issue-2">
      <h2>왜 사람들이 보는지</h2>
      <p>{escape(interest)}</p>
      <p>연예 이슈는 인물명 하나만으로 소비되기도 하지만, 실제로는 방송 장면, 발언 맥락, 팬들의 기존 기대감이 함께 얽히는 경우가 많습니다.</p>
    </section>

    <section id="issue-3">
      <h2>대중 반응 정리</h2>
      <p>{escape(public_reaction)}</p>
      <p>비슷한 내용으로 함께 확인한 기사도 아래에 남겨둡니다. 제목만 훑어봐도 어떤 포인트가 반복됐는지 감이 옵니다.</p>
{related_block}
{image_blocks["reaction"]}
    </section>

    <section id="issue-4">
      <h2>개인적인 해석</h2>
      <p>{escape(interpretation)}</p>
      <p>이런 이야기는 너무 진지하게 몰고 가면 오히려 어색해집니다. 지금 나온 내용만 보면, 그냥 가볍게 보고 지나갈 수 있는 연예 이슈에 더 가깝습니다.</p>
    </section>

    <section id="issue-5">
      <h2>마무리</h2>
      <p>{escape(closing)}</p>
      <p>혹시 뒤이어 새로운 말이 나오면 그때 다시 보면 됩니다. 지금은 제목만 보고 너무 크게 받아들이기보다, 이런 이야기가 나왔구나 정도로 정리하면 충분해 보입니다.</p>
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
