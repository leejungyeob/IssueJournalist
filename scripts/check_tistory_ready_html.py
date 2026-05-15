#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


FORBIDDEN_PATTERN_GUIDES = [
    ("왜 중요", "독자에게 설명하는 메타 문구 대신 기사 흐름 자체를 바로 쓰세요."),
    ("관심도", "수집/랭킹 기준 노출은 빼고 본문 이슈만 남기세요."),
    ("관련 노출", "수집/랭킹 기준 노출은 빼고 본문 이슈만 남기세요."),
    ("상위 이슈", "수집/랭킹 기준 노출은 빼고 본문 이슈만 남기세요."),
    ("수집 기준", "검수용 문구는 발행문에서 제거하세요."),
    ("선별", "검수용 문구는 발행문에서 제거하세요."),
    ("관심도 점수", "검수용 문구는 발행문에서 제거하세요."),
    ("관심도 신호", "검수용 문구는 발행문에서 제거하세요."),
    ("선정 신호", "검수용 문구는 발행문에서 제거하세요."),
    ("선별 신호", "검수용 문구는 발행문에서 제거하세요."),
    ("검색 의도", "SEO 작업 메모는 발행문에서 제거하세요."),
    ("블로그용 정리 포인트", "작성 메모는 발행문에서 제거하세요."),
    ("검수 메모", "작성 메모는 발행문에서 제거하세요."),
    ("수동 검수", "작성 메모는 발행문에서 제거하세요."),
    ("게시 전", "작성 메모는 발행문에서 제거하세요."),
    ("작성 기준", "작성 메모는 발행문에서 제거하세요."),
    ("자동 수집", "작성 메모는 발행문에서 제거하세요."),
    ("초안입니다", "작성 상태 설명은 발행문에서 제거하세요."),
    ("화제가 되고 있습니다", "상투적인 기사체 대신 구체 장면이나 발언으로 시작하세요."),
    ("귀추가 주목됩니다", "상투적인 기사체 대신 다음 흐름을 담백하게 쓰세요."),
    ("관심이 집중되고 있습니다", "상투적인 기사체 대신 누가 무엇을 말했는지 쓰세요."),
    ("반응이 붙기 쉽", "왜 반응이 생겼는지 분석하지 말고 기사 속 말과 짧은 감상만 쓰세요."),
    ("반응이 붙은 이유", "왜 반응이 생겼는지 분석하지 말고 기사 속 말과 짧은 감상만 쓰세요."),
    ("공감 포인트", "해설 문구 대신 실제 발언이나 장면이 어떻게 들렸는지 쓰세요."),
    ("눈에 들어옵니다", "AI식 평가 문구 대신 말 자체가 주는 느낌을 자연스럽게 쓰세요."),
    ("핵심은 복잡하지 않습니다", "보고서식 요약 문구는 빼고 바로 본문 내용을 이어가세요."),
    ("결론적으로", "결론 라벨은 빼고 바로 마지막 생각이나 정리 문장으로 이어가세요."),
    ("요약하면", "요약 라벨은 빼고 핵심 문장을 바로 쓰세요."),
    ("정리하자면", "정리 라벨은 빼고 핵심 문장을 바로 쓰세요."),
    ("정리하면", "정리 라벨은 빼고 블로그 운영자의 감상이나 후속 흐름으로 닫으세요."),
    ("따라서", "딱딱한 인과 접속사보다 문장을 분리하거나 '그래서' 정도로 풀어 쓰세요."),
    ("그러므로", "딱딱한 인과 접속사보다 문장을 분리하거나 '그래서' 정도로 풀어 쓰세요."),
    ("이를 통해", "'이로써', '이 때문에', '이 장면에서'처럼 실제 의미에 맞춰 쓰세요."),
    ("시사하는 바가 크다", "추상 평가를 빼고 무엇이 달라졌는지 구체적으로 쓰세요."),
    ("주목할 만하다", "평가 문구를 빼고 독자가 볼 만한 실제 내용을 쓰세요."),
    ("본질적으로", "추상 부사는 빼고 바로 핵심 내용을 쓰세요."),
    ("핵심적으로", "추상 부사는 빼고 바로 핵심 내용을 쓰세요."),
    ("혁신적인", "과장 수식 대신 실제 변화나 차이를 쓰세요."),
    ("이에 있어서", "'여기서는', '이 부분은', '이 흐름에서'로 풀어 쓰세요."),
    ("에 있어서", "'에서', '볼 때', '부분에서는'으로 줄이세요."),
    ("라는 점에서", "'라서', '라는 이유로', '때문에'로 풀어 쓰세요."),
    ("와 관련하여", "'를 두고', '에서', '에는'처럼 자연스럽게 바꾸세요."),
    ("를 통해", "'로', '해서', '때문에' 중 실제 의미에 맞게 바꾸세요."),
    ("을 통해", "'로', '해서', '때문에' 중 실제 의미에 맞게 바꾸세요."),
    ("에 의해", "행위자를 주어로 바꾸거나 능동문으로 쓰세요."),
    ("되어진", "'된', '됐다', '보였다'처럼 단일 피동으로 줄이세요."),
    ("가지고 있다", "'있다', '강하다', '했다'처럼 동사나 형용사로 환원하세요."),
    ("첫째", "번호식 보고서 흐름 대신 산문으로 이어 쓰세요."),
    ("둘째", "번호식 보고서 흐름 대신 산문으로 이어 쓰세요."),
    ("셋째", "번호식 보고서 흐름 대신 산문으로 이어 쓰세요."),
    ("또한,", "'또'나 '여기에'로 바꾸거나 삭제하세요."),
    ("즉,", "풀이가 꼭 필요할 때만 남기고 대부분 삭제하세요."),
    ("나아가", "보고서식 접속사는 빼거나 '여기에' 정도로 낮추세요."),
    ("할 필요가 있다", "권고문 대신 실제 기사 내용이나 현재 흐름을 쓰세요."),
    ("할 수 있을 것으로 보인다", "'로 보인다' 또는 확정 가능한 사실이면 평서로 줄이세요."),
    ("단정하지", "독자에게 조심하라고 권고하지 말고 확인된 내용만 담백하게 쓰세요."),
    ("봐야", "독자에게 지시하지 말고 기사에 나온 흐름을 평서로 쓰세요."),
    ("봐야 합니다", "독자에게 지시하지 말고 기사에 나온 흐름을 평서로 쓰세요."),
    ("보는 게 맞", "독자에게 판단을 권고하지 말고 글쓴이의 정리로 바꾸세요."),
    ("보는 편", "독자에게 판단을 권고하지 말고 글쓴이의 정리로 바꾸세요."),
    ("안전합니다", "안전/위험 판단 대신 확인된 사실과 남은 흐름을 쓰세요."),
    ("좋겠습니다", "권고형 마무리 대신 후속 내용 안내나 개인 감상으로 닫으세요."),
    ("좋아 보입니다", "권고형 마무리 대신 후속 내용 안내나 개인 감상으로 닫으세요."),
    ("조심해서 봐야", "독자에게 주의시키지 말고 기사 내용의 확인 범위만 쓰세요."),
    ("받아들이기 어렵", "판단 권고 대신 기사에서 확인된 내용과 반응만 쓰세요."),
    ("받아들이기엔", "판단 권고 대신 기사에서 확인된 내용과 반응만 쓰세요."),
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
        self.news_images = 0
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
        elif tag == "img":
            self.news_images += 1

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
    for pattern, guide in FORBIDDEN_PATTERN_GUIDES:
        if re.search(re.escape(pattern), html, flags=re.IGNORECASE):
            errors.append(f"forbidden phrase found: {pattern} -> {guide}")

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
    if parsed.toc_links and parsed.toc_links != parsed.issue_sections:
        errors.append(f"toc link count {parsed.toc_links} does not match issue section count {parsed.issue_sections}")
    if parsed.source_bookmarks < 1:
        errors.append("missing source bookmark")
    if not 1 <= parsed.news_images <= 4:
        errors.append(f"expected 1-4 article images, found {parsed.news_images}")

    tags = tag_count(args.tags_file)
    if tags is not None and tags != 10:
        errors.append(f"expected 10 tags, found {tags}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "OK: publish-ready checks passed "
        f"(h1=1, issues={parsed.issue_sections}, toc={parsed.toc_links}, "
        f"bookmarks={parsed.source_bookmarks}, images={parsed.news_images})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
