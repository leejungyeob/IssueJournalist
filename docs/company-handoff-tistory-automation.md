# 회사에서 이어서 실행할 작업

## 현재 방향

네이버 블로그 자동 발행은 공식 글쓰기 API가 현재 호출되지 않아 보류한다.

운영 방향은 다시 티스토리다.

- 운영 목표: `semi_auto`
- 발행 방식: 티스토리 게시용 HTML/대표이미지 생성 후 수동 복붙
- 다음 자동화 목표: 티스토리 글쓰기 화면 브라우저 자동화
- 우선 안전한 단계: 자동 임시저장

설정 파일:

```bash
config/tistory-automation.json
```

## 1. 회사에서 먼저 받을 것

```bash
git pull origin main
```

## 2. `.env` 확인

티스토리 초안 생성에는 네이버 뉴스 검색 API 키만 필요하다.

```env
NAVER_CLIENT_ID=뉴스검색_Client_ID
NAVER_CLIENT_SECRET=뉴스검색_Client_Secret
```

현재 로컬에서는 네이버 OAuth 설정 과정에서 이 값도 채워둔 상태다.

## 3. 사전 확인

```bash
python3 scripts/run_tistory_pipeline.py --preflight
```

정상 출력:

```text
OK: Tistory pipeline preflight passed
```

## 4. 오늘 초안 생성

```bash
python3 scripts/run_tistory_pipeline.py
```

생성 위치:

```text
drafts/YYYY-MM-DD/
  post-title.txt
  post-tags.txt
  cover.png
  cover.svg
  tistory-ready.html
  seed.html
  latest-entertainment-news.json
```

티스토리에 실제로 넣을 파일:

- `post-title.txt`: 제목
- `post-tags.txt`: 태그
- `cover.png`: 대표이미지
- `tistory-ready.html`: 본문 HTML

## 5. 현재 설정

```json
{
  "target": "tistory",
  "mode": "semi_auto",
  "publish_mode": "manual_copy",
  "posts_per_run": 1,
  "news_display_per_query": 40,
  "news_limit": 12
}
```

태그는 티스토리 검증 스크립트 기준에 맞춰 정확히 10개로 유지한다.

## 6. 다음 구현 순서

1. 현재 생성물로 티스토리 수동 게시 흐름을 한 번 검증한다.
2. `tistory-ready.html` 품질을 높인다.
3. 티스토리 글쓰기 화면 브라우저 자동화 스크립트를 만든다.
4. 처음에는 `임시저장`까지만 자동화한다.
5. 안정화되면 `발행` 버튼 자동화로 확장한다.

## 7. 주의

- `.env`는 커밋하지 않는다.
- `drafts/`, `logs/`는 자동 생성물이므로 커밋하지 않는다.
- 네이버 블로그 OAuth 토큰은 현재 `.env`에 남아 있지만, 티스토리 운영에는 필수값이 아니다.
- 브라우저 자동화 발행은 로그인 세션, 에디터 UI 변경, 캡차/보안확인에 따라 멈출 수 있다.
