# 회사에서 이어서 실행할 작업

## 현재 방향

운영 방향은 티스토리다.

- 운영 목표: `semi_auto`
- 발행 방식: 티스토리 게시용 HTML/대표이미지 생성 후 수동 복붙
- 다음 자동화 목표: 티스토리 글쓰기 화면 브라우저 자동화
- 우선 안전한 단계: 자동 임시저장

## 최종 목표

사용자가 원하는 최종 운영 형태는 아래와 같다.

- 매일 07:00부터 다음날 02:00까지 실행
- 매 정각마다 연예뉴스 포스트 5개 생성
- 매 정각마다 5개 자동 발행
- 하루 실행 횟수: 20회
- 하루 발행량: 100개

시간대:

```text
07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 00, 01, 02
```

현재 코드는 `시간당 5개 개별글 생성`까지 된다. 티스토리 브라우저 자동 입력/임시저장/발행은 아직 구현 전이다.

최종 목표를 위해 필요한 추가 구현:

1. 중복 발행 방지용 발행 로그
2. 티스토리 에디터 브라우저 자동화
3. 최초에는 자동 `임시저장`, 안정화 후 자동 `발행`
4. 스케줄러 등록

주의: 티스토리 Open API는 종료 공지가 있으므로 공식 API 발행이 아니라 브라우저 자동화 기준으로 구현한다.

설정 파일:

```bash
config/tistory-automation.json
```

## 1. 회사에서 먼저 받을 것

```bash
git pull origin main
```

## 2. `.env` 확인

현재 티스토리 초안 생성에는 별도 API 키가 필요하지 않다.

`.env`는 Git에서 제외되어 있으며, 이후 티스토리 브라우저 자동화에 필요한 로컬 값이 생기면 개인 환경에서만 관리한다.

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

## 4-1. 시간당 5개 개별글 생성

```bash
python3 scripts/run_tistory_hourly_batch.py
```

현재 시간이 설정된 운영 시간대가 아니어도 테스트하려면:

```bash
python3 scripts/run_tistory_hourly_batch.py --force
```

생성 위치:

```text
drafts/YYYY-MM-DD/HH/
  latest-entertainment-news.json
  manifest.json
  post-01/
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

개별글마다 폴더를 분리한다.

## 5. 현재 설정

```json
{
  "target": "tistory",
  "mode": "semi_auto",
  "publish_mode": "manual_copy",
  "posts_per_run": 5,
  "news_display_per_query": 40,
  "news_limit": 30
}
```

태그는 티스토리 검증 스크립트 기준에 맞춰 정확히 10개로 유지한다.

## 6. 다음 구현 순서

1. 시간당 5개 생성물로 티스토리 수동 게시 흐름을 한 번 검증한다.
2. `tistory-ready.html` 품질을 높인다.
3. 티스토리 글쓰기 화면 브라우저 자동화 스크립트를 만든다.
4. 처음에는 `임시저장`까지만 자동화한다.
5. 안정화되면 `발행` 버튼 자동화로 확장한다.

## 7. 주의

- `.env`는 커밋하지 않는다.
- `drafts/`, `logs/`는 자동 생성물이므로 커밋하지 않는다.
- 브라우저 자동화 발행은 로그인 세션, 에디터 UI 변경, 캡차/보안확인에 따라 멈출 수 있다.
