#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


FORBIDDEN_PATTERNS = [
    "왜 중요",
    "관심도",
    "관련 노출",
    "상위 이슈",
    "수집 기준",
    "선별",
    "관심도 점수",
    "관심도 신호",
    "선정 신호",
    "선별 신호",
    "검색 의도",
    "블로그용 정리 포인트",
    "검수 메모",
    "수동 검수",
    "게시 전",
    "작성 기준",
    "자동 수집",
    "초안입니다",
]


class TistoryHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.h1_count = 0
        self.h2_count = 0
        self.meta_description = ""
        self.og_description = ""
        self.issue_sections = 0
        self.toc_links = 0
        self.source_bookmarks = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and attr_map.get("name") == "description":
            self.meta_description = attr_map.get("content", "")
        elif tag == "meta" and attr_map.get("property") == "og:description":
            self.og_description = attr_map.get("content", "")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "h2":
            self.h2_count += 1
        elif tag == "section" and attr_map.get("id", "").startswith("issue-"):
            self.issue_sections += 1
        elif tag == "a" and attr_map.get("href", "").startswith("#issue-"):
            self.toc_links += 1
        elif "source-bookmark" in attr_map.get("class", "").split():
            self.source_bookmarks += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def tag_count(path: Path | None) -> int | None:
    if path is None:
        return None
    tags = [tag.strip() for tag in read_text(path).strip().split(",") if tag.strip()]
    return len(tags)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a Tistory-ready HTML draft for publish-readiness.")
    parser.add_argument("html", type=Path, help="Tistory-ready HTML path.")
    parser.add_argument("--title-file", type=Path, help="Optional Tistory post title file.")
    parser.add_argument("--tags-file", type=Path, help="Optional Tistory tags file.")
    args = parser.parse_args()

    html = read_text(args.html)
    parsed = TistoryHTMLParser()
    parsed.feed(html)

    errors: list[str] = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(re.escape(pattern), html, flags=re.IGNORECASE):
            errors.append(f"forbidden phrase found: {pattern}")

    title_text = read_text(args.title_file).strip() if args.title_file else parsed.title.strip()
    if not title_text:
        errors.append("missing title")
    elif len(title_text) > 85:
        errors.append(f"title too long: {len(title_text)} chars")

    if parsed.h1_count != 1:
        errors.append(f"expected exactly one h1, found {parsed.h1_count}")
    if not parsed.meta_description:
        errors.append("missing meta description")
    elif len(parsed.meta_description) > 160:
        errors.append(f"meta description too long: {len(parsed.meta_description)} chars")
    if parsed.og_description and parsed.og_description != parsed.meta_description:
        errors.append("og description differs from meta description")
    if parsed.issue_sections == 0:
        errors.append("missing issue sections")
    if parsed.toc_links != parsed.issue_sections:
        errors.append(f"toc link count {parsed.toc_links} does not match issue section count {parsed.issue_sections}")
    if parsed.source_bookmarks != parsed.issue_sections:
        errors.append(
            f"source bookmark count {parsed.source_bookmarks} does not match issue section count {parsed.issue_sections}"
        )

    tags = tag_count(args.tags_file)
    if tags is not None and tags != 10:
        errors.append(f"expected 10 tags, found {tags}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "OK: publish-ready checks passed "
        f"(h1=1, issues={parsed.issue_sections}, toc={parsed.toc_links}, bookmarks={parsed.source_bookmarks})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
