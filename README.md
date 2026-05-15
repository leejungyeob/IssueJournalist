# IssueJournalist

연예 뉴스 수집부터 티스토리 게시용 HTML 초안 생성까지 돕는 반자동 블로그 운영 워크스페이스입니다.

현재 운영 방향은 티스토리입니다. 뉴스 수집은 공개 RSS 기반이며, 티스토리는 HTML/대표이미지 생성 후 수동 복붙을 기본값으로 둡니다.

## 설정

현재 초안 생성에는 별도 API 키가 필요하지 않습니다. `.env`는 Git에서 제외되어 있으며, 이후 티스토리 브라우저 자동화에 필요한 로컬 값이 생기면 개인 환경에서만 관리합니다.

## 티스토리 파이프라인 실행

사전 확인:

```bash
python3 scripts/run_tistory_pipeline.py --preflight
```

오늘 초안 생성:

```bash
python3 scripts/run_tistory_pipeline.py
```

시간당 5개 개별글 배치 생성:

```bash
python3 scripts/run_tistory_hourly_batch.py
```

시간당 배치는 먼저 네이트 연예 조회순 랭킹을 사용합니다. 이미 `logs/tistory-published.jsonl` 또는 `logs/tistory-issued.jsonl`에 같은 URL/제목이 있으면 건너뛰고, 랭킹 후보가 부족해지면 공개 RSS 최신 연예뉴스 후보로 채웁니다.

생성물은 `drafts/YYYY-MM-DD/` 아래에 저장됩니다.

```text
post-title.txt
post-tags.txt
cover.png
cover.svg
tistory-ready.html
seed.html
latest-entertainment-news.json
```

시간당 배치 생성물은 `drafts/YYYY-MM-DD/HH/` 아래에서 개별글마다 폴더를 나눕니다.

```text
drafts/YYYY-MM-DD/HH/
  latest-entertainment-news.json
  manifest.json
  post-01/
    enriched.json
    post-title.txt
    post-tags.txt
    cover.png
    cover.svg
    tistory-ready.html
  post-02/
  post-03/
  post-04/
  post-05/
```

회사/집에서 이어서 볼 작업 메모는 아래 문서를 기준으로 합니다.

```bash
docs/company-handoff-tistory-automation.md
```

## 뉴스 수집

```bash
python3 scripts/collect_entertainment_news.py --display 40 --limit 12 --output logs/latest-entertainment-news.json
```

기본 검색어는 `연예`, `아이돌`, `배우`, `드라마`, `예능`, `K팝`, `컴백`, `시청률`입니다. 변경하려면 `--queries` 옵션에 쉼표로 구분해 넣습니다.

```bash
python3 scripts/collect_entertainment_news.py --queries "연예,아이돌,배우" --limit 8
```

수집 결과는 단순 최신순이 아니라 관심도 기준으로 다시 정렬합니다.

- 여러 매체/검색어에서 반복 등장하는 이슈를 더 높게 봅니다.
- `공식`, `단독`, `컴백`, `확정`, `출연`, `시청률` 같은 블로그 소재 키워드를 가산합니다.
- 민감 이슈는 제외하지 않고 플래그만 붙입니다. 반복 보도되는 민감 이슈는 포함할 수 있지만, 최종 글에서는 보도/혐의/공식 입장 중심으로 보수적으로 표현합니다.

## 티스토리 초안 뼈대 생성

```bash
python3 scripts/render_tistory_seed_draft.py logs/latest-entertainment-news.json --output drafts/YYYY-MM-DD/seed.html
```

`seed.html`은 자동화가 참고하는 게시글 뼈대입니다. 독자에게 보이지 않는 내부 판단 문구(`관심도 점수`, `왜 중요할까`, `검수 메모`, `수집 기준`, `자동 수집` 등)는 HTML에 넣지 않습니다.

`drafts/`는 자동 생성 산출물이므로 Git에서 제외됩니다.

## 복붙용 HTML 검증

최종 HTML을 만든 뒤에는 게시 전에 아래 검사를 통과시킵니다.

```bash
python3 scripts/check_tistory_ready_html.py drafts/YYYY-MM-DD/tistory-ready.html \
  --title-file drafts/YYYY-MM-DD/post-title.txt \
  --tags-file drafts/YYYY-MM-DD/post-tags.txt
```

검사 항목은 다음과 같습니다.

- 내부 분석/검수 문구가 본문에 남아 있지 않은지 확인합니다.
- 제목 길이, `meta description`, `h1` 개수, 목차 링크, 이슈 섹션, 출처 박스 구조를 확인합니다.
- 티스토리 태그가 정확히 10개인지 확인합니다.

## 대표이미지 생성

기본 대표이미지는 기사 사진을 무단 재사용하지 않고, 날짜/제목/주요 이슈 카드로 만든 1080x1080 PNG를 사용합니다. 티스토리 관리자/목록 썸네일에서 정사각형 또는 16:10으로 잘려도 중앙 제목이 살아남도록 만든 썸네일 안전 구도입니다.

```bash
python3 scripts/create_cover_image.py logs/latest-entertainment-news.json \
  --title-file drafts/YYYY-MM-DD/post-title.txt \
  --svg-output drafts/YYYY-MM-DD/cover.svg \
  --png-output drafts/YYYY-MM-DD/cover.png
```

## 초안 파일 규칙

날짜별 폴더를 사용합니다.

```text
drafts/
  YYYY-MM-DD/
    post-title.txt      # 티스토리 제목 입력칸에 넣을 제목
    post-tags.txt       # 티스토리 태그 입력칸에 넣을 태그
    cover.png           # 티스토리 대표이미지
    cover.svg           # 대표이미지 원본
    tistory-ready.html  # 티스토리에 바로 복사/붙여넣기할 최종 초안
    seed.html           # 자동화가 참고하는 수집 기반 뼈대
```

사용자가 실제로 사용할 파일은 `post-title.txt`, `post-tags.txt`, `cover.png`, `tistory-ready.html`입니다. `tistory-ready.html`은 독자에게 바로 보이는 게시글 문장만 포함해야 하며, 자동화 운영 메모나 작성자 지시문을 넣지 않습니다.
