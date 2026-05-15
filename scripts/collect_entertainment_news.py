#!/usr/bin/env python3
from __future__ import annotations

import argparse
import email.utils
import html
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
CERT_PATHS = [
    Path("/etc/ssl/cert.pem"),
    Path("/opt/homebrew/etc/openssl@3/cert.pem"),
]

DEFAULT_QUERIES = ["연예", "아이돌", "배우", "드라마", "예능", "K팝", "컴백", "시청률"]
RSS_ENDPOINT = "https://news.google.com/rss/search"
IMPORTANT_KEYWORDS = [
    "공식",
    "단독",
    "컴백",
    "확정",
    "발표",
    "출연",
    "계약",
    "시청률",
    "제작발표",
    "결혼",
    "입대",
    "수상",
    "차트",
    "월드투어",
]
SENSITIVE_KEYWORDS = [
    "루머",
    "폭로",
    "사생활",
    "논란",
    "음주",
    "마약",
    "고소",
    "혐의",
    "구속",
    "사망",
    "극단",
    "이혼",
]
ATTENTION_STOPWORDS = {
    "가수",
    "걸그룹",
    "공개",
    "공식",
    "관련",
    "근황",
    "기자",
    "뉴스",
    "단독",
    "드라마",
    "무대",
    "발표",
    "배우",
    "방송",
    "보도",
    "사진",
    "소식",
    "아이돌",
    "연예",
    "예능",
    "오늘",
    "월드투어",
    "출연",
    "컴백",
    "프로그램",
    "확정",
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    description: str
    url: str
    domain: str
    pub_date: str
    pub_date_kst: str
    source_query: str
    source_queries: list[str]
    source_name: str
    score: float
    interest_score: float
    cluster_size: int
    cluster_domains: list[str]
    attention_terms: list[str]
    important_keywords: list[str]
    safety_flags: list[str]


def ssl_context() -> ssl.SSLContext:
    for path in CERT_PATHS:
        if path.exists():
            return ssl.create_default_context(cafile=str(path))
    return ssl.create_default_context()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"</?b>", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_title(value: str, source_name: str) -> str:
    title = clean_text(value)
    if source_name and title.endswith(f" - {source_name}"):
        title = title[: -len(f" - {source_name}")].strip()
    return title


def normalize_title(value: str) -> str:
    value = clean_text(value).lower()
    value = re.sub(r"\[[^\]]+\]|\([^\)]+\)", "", value)
    value = re.sub(r"[^0-9a-z가-힣]+", "", value)
    return value


def parse_pub_date(value: str) -> datetime:
    parsed = email.utils.parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(KST)


def domain_from_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    return parsed.netloc.removeprefix("www.")


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def attention_terms(title: str, description: str) -> list[str]:
    quoted = re.findall(r"[\"'‘’“”「」『』]([^\"'‘’“”「」『』]{2,24})[\"'‘’“”「」『』]", title)
    words = re.findall(r"[0-9A-Za-z가-힣]{2,}", f"{title} {description}")
    terms: list[str] = []

    for raw in [*quoted, *words]:
        term = raw.strip()
        if not term or term in ATTENTION_STOPWORDS:
            continue
        if term.isdigit() or len(term) > 24:
            continue
        if term not in terms:
            terms.append(term)

    return terms[:8]


def topic_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0
    return len(left & right) / min(len(left), len(right))


def score_item(
    pub_dt: datetime,
    important_hits: list[str],
    safety_flags: list[str],
    cluster_size: int,
    cluster_domains: list[str],
    source_queries: list[str],
) -> tuple[float, float]:
    now = datetime.now(KST)
    age_hours = max((now - pub_dt).total_seconds() / 3600, 0)
    recency_score = max(0, 24 - age_hours) / 24 * 6
    coverage_score = min(cluster_size, 6) * 4
    domain_score = min(len(cluster_domains), 5) * 2
    query_score = min(len(source_queries), 5)
    interest_score = coverage_score + domain_score + query_score
    important_score = min(len(important_hits), 4) * 2
    safety_penalty = min(len(safety_flags), 4) * (0.8 if cluster_size >= 2 else 1.5)
    score = interest_score + recency_score + important_score - safety_penalty
    return round(score, 3), round(interest_score, 3)


def rss_url(query: str) -> str:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "hl": "ko",
            "gl": "KR",
            "ceid": "KR:ko",
        }
    )
    return f"{RSS_ENDPOINT}?{params}"


def fetch_rss(query: str) -> list[dict]:
    request = urllib.request.Request(
        rss_url(query),
        headers={"User-Agent": "IssueJournalist/1.0 (+https://github.com/leejungyeob/IssueJournalist)"},
    )
    with urllib.request.urlopen(request, timeout=15, context=ssl_context()) as response:
        root = ET.fromstring(response.read())

    items: list[dict] = []
    for item in root.findall("./channel/item"):
        source = item.find("source")
        source_name = clean_text(source.text if source is not None else "")
        source_url = source.attrib.get("url", "") if source is not None else ""
        title = clean_title(item.findtext("title", ""), source_name)
        link = clean_text(item.findtext("link", ""))
        description = clean_text(item.findtext("description", ""))
        pub_date = clean_text(item.findtext("pubDate", ""))
        if not title or not link or not pub_date:
            continue
        items.append(
            {
                "title": title,
                "description": description,
                "url": link,
                "domain": domain_from_url(source_url or link) or source_name or "source",
                "source_name": source_name or domain_from_url(source_url or link) or "source",
                "pub_date": pub_date,
            }
        )
    return items


def collect_news(queries: list[str], display: int, limit: int) -> dict:
    candidates_by_url: dict[str, dict] = {}
    errors: list[dict[str, str]] = []

    for query in queries:
        try:
            raw_items = fetch_rss(query)[:display]
        except urllib.error.HTTPError as exc:
            errors.append({"query": query, "error": f"HTTP {exc.code}: {exc.reason}"})
            continue
        except Exception as exc:
            errors.append({"query": query, "error": str(exc)})
            continue

        for raw in raw_items:
            title = clean_text(raw.get("title", ""))
            description = clean_text(raw.get("description", ""))
            url = raw.get("url") or ""
            pub_date = raw.get("pub_date", "")
            if not title or not url or not pub_date:
                continue

            try:
                pub_dt = parse_pub_date(pub_date)
            except Exception:
                continue

            combined = f"{title} {description}"
            candidate = {
                "title": title,
                "description": description,
                "url": url,
                "domain": raw.get("domain") or domain_from_url(url),
                "source_name": raw.get("source_name") or raw.get("domain") or domain_from_url(url),
                "pub_date": pub_date,
                "pub_date_kst": pub_dt.isoformat(),
                "pub_dt": pub_dt,
                "source_query": query,
                "source_queries": [query],
                "important_keywords": keyword_hits(combined, IMPORTANT_KEYWORDS),
                "safety_flags": keyword_hits(combined, SENSITIVE_KEYWORDS),
                "attention_terms": attention_terms(title, description),
                "normalized_title": normalize_title(title),
            }

            existing = candidates_by_url.get(url)
            if existing:
                if query not in existing["source_queries"]:
                    existing["source_queries"].append(query)
                continue
            candidates_by_url[url] = candidate

    clusters: list[dict] = []
    for candidate in candidates_by_url.values():
        terms = set(candidate["attention_terms"])
        matched_cluster = None
        for cluster in clusters:
            if candidate["normalized_title"] == cluster["normalized_titles"][0]:
                matched_cluster = cluster
                break
            if len(terms & cluster["terms"]) >= 2 or topic_similarity(terms, cluster["terms"]) >= 0.35:
                matched_cluster = cluster
                break

        if matched_cluster is None:
            matched_cluster = {
                "items": [],
                "terms": set(),
                "domains": set(),
                "queries": set(),
                "normalized_titles": [],
            }
            clusters.append(matched_cluster)

        matched_cluster["items"].append(candidate)
        matched_cluster["terms"].update(terms)
        matched_cluster["domains"].add(candidate["domain"])
        matched_cluster["queries"].update(candidate["source_queries"])
        matched_cluster["normalized_titles"].append(candidate["normalized_title"])

    representative_items: list[NewsItem] = []
    for cluster in clusters:
        cluster_domains = sorted(cluster["domains"])
        cluster_queries = sorted(cluster["queries"])
        cluster_size = len(cluster["items"])
        scored_candidates = []
        for candidate in cluster["items"]:
            merged_queries = sorted(set(candidate["source_queries"]) | set(cluster_queries))
            score, interest_score = score_item(
                candidate["pub_dt"],
                candidate["important_keywords"],
                candidate["safety_flags"],
                cluster_size,
                cluster_domains,
                merged_queries,
            )
            scored_candidates.append((score, interest_score, merged_queries, candidate))

        score, interest_score, merged_queries, candidate = max(scored_candidates, key=lambda item: item[0])
        representative_items.append(
            NewsItem(
                title=candidate["title"],
                description=candidate["description"],
                url=candidate["url"],
                domain=candidate["domain"],
                pub_date=candidate["pub_date"],
                pub_date_kst=candidate["pub_date_kst"],
                source_query=candidate["source_query"],
                source_queries=merged_queries,
                source_name=candidate["source_name"],
                score=score,
                interest_score=interest_score,
                cluster_size=cluster_size,
                cluster_domains=cluster_domains,
                attention_terms=candidate["attention_terms"],
                important_keywords=candidate["important_keywords"],
                safety_flags=candidate["safety_flags"],
            )
        )

    items = sorted(representative_items, key=lambda item: item.score, reverse=True)[:limit]
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    return {
        "generated_at": generated_at,
        "timezone": "Asia/Seoul",
        "source": "rss",
        "queries": queries,
        "display_per_query": display,
        "candidate_count": len(candidates_by_url),
        "topic_cluster_count": len(clusters),
        "selected_count": len(items),
        "errors": errors,
        "items": [asdict(item) for item in items],
    }


def parse_queries(raw: str | None) -> list[str]:
    if not raw:
        return DEFAULT_QUERIES
    return [part.strip() for part in raw.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect recent entertainment news from public RSS feeds.")
    parser.add_argument("--queries", help="Comma-separated query terms. Defaults to entertainment-related terms.")
    parser.add_argument("--display", type=int, default=20, help="RSS items per query.")
    parser.add_argument("--limit", type=int, default=12, help="Maximum selected items to output.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    if args.display < 1:
        print("--display must be at least 1.", file=sys.stderr)
        return 2

    payload = collect_news(parse_queries(args.queries), args.display, args.limit)
    if payload["errors"] and not payload["items"]:
        for error in payload["errors"]:
            print(f"ERROR: {error['query']}: {error['error']}", file=sys.stderr)
        return 1

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
