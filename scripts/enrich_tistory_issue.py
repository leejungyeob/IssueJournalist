#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collect_entertainment_news import clean_text, fetch_rss  # noqa: E402


CERT_PATHS = [
    Path("/etc/ssl/cert.pem"),
    Path("/opt/homebrew/etc/openssl@3/cert.pem"),
]
IMAGE_PATTERN = re.compile(r"https://lh3\.googleusercontent\.com/[A-Za-z0-9_./?=&;%:+-]+")
OG_IMAGE_PATTERN = re.compile(
    r'<meta\s+(?:property|name)=["\'](?:og:image|twitter:image)["\']\s+content=["\'](?P<url>[^"\']+)["\']',
    re.IGNORECASE,
)
NATE_IMAGE_PATTERN = re.compile(r"(?:https?:)?//thumbnews\.nateimg\.co\.kr/[A-Za-z0-9_./?=&;%:+-]+")
ICON_HINTS = {"DR60l-K8vnyi99NZovm9HlXyZwQ85GMDxiwJWzoasZYCUrPuUM_P_4Rb7ei03j-0nRs0c4F"}


def ssl_context() -> ssl.SSLContext:
    for path in CERT_PATHS:
        if path.exists():
            return ssl.create_default_context(cafile=str(path))
    return ssl.create_default_context()


def normalized(value: str) -> str:
    value = clean_text(value).lower()
    return re.sub(r"[^0-9a-z가-힣]+", "", value)


def build_query(item: dict) -> str:
    terms = [term for term in item.get("attention_terms", []) if len(str(term)) >= 2]
    if terms:
        return " ".join(str(term) for term in terms[:3])
    title_words = re.findall(r"[0-9A-Za-z가-힣]{2,}", clean_text(item.get("title", "")))
    return " ".join(title_words[:4]) or clean_text(item.get("source_query", "연예"))


def unique_related(item: dict, candidates: list[dict], limit: int) -> list[dict]:
    base_title = normalized(item.get("title", ""))
    base_url = item.get("url", "")
    seen = {base_url}
    related = []

    for candidate in candidates:
        title = clean_text(candidate.get("title", ""))
        url = candidate.get("url", "")
        if not title or not url or url in seen:
            continue
        if normalized(title) == base_title:
            continue
        seen.add(url)
        related.append(
            {
                "title": title,
                "description": clean_text(candidate.get("description", "")),
                "url": url,
                "domain": clean_text(candidate.get("domain", "")),
                "source_name": clean_text(candidate.get("source_name", "")),
                "pub_date": clean_text(candidate.get("pub_date", "")),
            }
        )
        if len(related) == limit:
            break
    return related


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "IssueJournalist/1.0 (+https://github.com/leejungyeob/IssueJournalist)"},
    )
    with urllib.request.urlopen(request, timeout=12, context=ssl_context()) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def normalize_image_url(url: str) -> str:
    url = html.unescape(url)
    url = url.split("\\u003d")
    if len(url) > 1:
        url = "=".join(url)
    else:
        url = url[0]
    return urllib.parse.unquote(url).strip()


def absolute_image_url(url: str, base: str = "https://news.nate.com") -> str:
    url = normalize_image_url(url)
    if url.startswith("//"):
        return "https:" + url
    return urllib.parse.urljoin(base, url)


def image_rank(url: str) -> int:
    score = 0
    if "w300" in url or "s0-w300" in url:
        score += 4
    if "w16" in url or "w24" in url or "w32" in url or "w48" in url:
        score -= 10
    if any(hint in url for hint in ICON_HINTS):
        score -= 20
    return score


def extract_images(article: dict) -> list[dict]:
    try:
        page = fetch_text(article["url"])
    except Exception:
        return []

    urls = []
    for pattern in [OG_IMAGE_PATTERN, NATE_IMAGE_PATTERN, IMAGE_PATTERN]:
        if pattern is OG_IMAGE_PATTERN:
            found = [match.group("url") for match in pattern.finditer(page)]
        else:
            found = pattern.findall(page)
        for raw_url in found:
            image_url = absolute_image_url(raw_url, article["url"])
            if any(hint in image_url for hint in ICON_HINTS):
                continue
            if image_url in urls:
                continue
            urls.append(image_url)

    urls = sorted(urls, key=image_rank, reverse=True)
    return [
        {
            "url": image_url,
            "source_article_title": article.get("title", ""),
            "source_article_url": article.get("url", ""),
            "source_name": article.get("source_name") or article.get("domain") or "source",
        }
        for image_url in urls[:2]
        if image_rank(image_url) > -5
    ]


def enrich_item(item: dict, related_limit: int, image_limit: int) -> dict:
    query = build_query(item)
    related_candidates = fetch_rss(query)
    related_articles = unique_related(item, related_candidates, related_limit)
    article_pool = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source_name": item.get("source_name") or item.get("domain") or "source",
            "domain": item.get("domain", ""),
        },
        *related_articles,
    ]

    image_candidates = []
    seen_images = set()
    for image in item.get("image_candidates") or []:
        image_url = absolute_image_url(image.get("url", ""), item.get("url", ""))
        if not image_url or image_url in seen_images:
            continue
        seen_images.add(image_url)
        image_candidates.append({**image, "url": image_url})
        if len(image_candidates) == image_limit:
            break
    for article in article_pool[: max(related_limit, 4)]:
        for image in extract_images(article):
            if image["url"] in seen_images:
                continue
            seen_images.add(image["url"])
            image_candidates.append(image)
            if len(image_candidates) == image_limit:
                break
        if len(image_candidates) == image_limit:
            break

    return {
        "query": query,
        "item": item,
        "related_articles": related_articles,
        "image_candidates": image_candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich one Tistory issue with related news and image candidates.")
    parser.add_argument("input", type=Path, help="Collected news JSON path.")
    parser.add_argument("--index", type=int, required=True, help="0-based item index.")
    parser.add_argument("--output", type=Path, required=True, help="Enriched JSON output path.")
    parser.add_argument("--related-limit", type=int, default=5)
    parser.add_argument("--image-limit", type=int, default=4)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if args.index < 0 or args.index >= len(items):
        raise SystemExit(f"item index out of range: {args.index}")

    enriched = enrich_item(items[args.index], args.related_limit, args.image_limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
