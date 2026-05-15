# 회사에서 이어서 실행할 작업

## 현재 방향

운영 방향은 티스토리다.

- 운영 목표: `auto`
- 발행 방식: 시간당 5개 글 생성 후 로그인된 Chrome으로 티스토리 자동 발행
- 자동화 방식: Codex cron automation + Chrome AppleScript 브라우저 자동화

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

현재 코드는 `시간당 5개 개별글 생성`과 로그인된 Chrome 기반 티스토리 자동 발행까지 연결되어 있다. 발행 없이 산출물만 확인할 때는 `--no-publish`를 사용한다.

현재 시간당 글 선택 방식:

1. 네이트 연예 조회순 랭킹에서 높은 순위 기사부터 사용한다.
2. `logs/tistory-published.jsonl` 또는 `logs/tistory-issued.jsonl`에 같은 URL/제목이 있으면 건너뛴다.
3. 네이트 랭킹 후보를 다 썼거나 부족하면 공개 RSS 최신 연예뉴스 후보로 채운다.
4. 개별글마다 같은 키워드의 보조 기사와 이미지 후보를 `enriched.json`에 저장한다.

주의: 티스토리 Open API는 종료 공지가 있으므로 공식 API 발행이 아니라 브라우저 자동화 기준으로 구현한다. 현재 방식은 `scripts/publish_tistory_browser.py`가 로그인된 Chrome에서 티스토리 글쓰기 화면을 열고 제목/본문/태그/대표이미지를 넣은 뒤 최종 발행 버튼을 누른다.

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

브라우저 자동화는 Chrome 로그인 세션을 사용한다. 현재 블로그 주소는 `goods99.tistory.com`이며, 필요하면 `.env`에 아래처럼 override한다.

```bash
TISTORY_BLOG_HOST=goods99.tistory.com
```

Chrome에서 AppleScript JavaScript 실행이 꺼져 있으면 아래 메뉴를 한 번 켠다.

```text
보기 > 개발자 > Apple Events의 자바스크립트 허용
```

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
  post-title-candidates.txt
  post-tags.txt
  cover.png
  cover.svg
  tistory-ready.html
  seed.html
  latest-entertainment-news.json
```

티스토리에 실제로 넣을 파일:

- `post-title.txt`: 제목
- `post-title-candidates.txt`: 제목 후보 3개
- `post-tags.txt`: 태그
- `cover.png`: 대표이미지
- `tistory-ready.html`: 본문 HTML. 기사 복붙형 문장 대신 블로그식 정리 흐름으로 작성되며, 본문 중간에 수집/보강 단계에서 찾은 실제 이미지와 이미지 출처 캡션이 들어간다.

본문 문체 기준:

- 너무 방어적으로 쓰지 않는다. `민감하니 단정하지 말자`, `출처와 확인 여부를 봐야 한다` 같은 권고문은 피한다.
- 보고서식 요약어를 줄인다. 기본 문체는 `다/습니다`로 맞춘다. `흐름입니다`, `핵심은 복잡하지 않습니다`처럼 딱딱하게 닫기보다 `아무래도 ... 것으로 보입니다`, `... 쪽에 가까워 보입니다`, `... 같습니다`처럼 블로그 운영자가 자연스럽게 읽은 느낌으로 쓴다.
- 한 글 안에서 `다/습니다`와 `요`체를 갑자기 섞지 않는다. 대화체를 쓰려면 글 전체 톤을 맞추고, 기본 자동 초안에서는 `요`체를 쓰지 않는다.
- 루머성 소재도 과하게 겁내지 않는다. 기사 밖 사실을 단정하지만 않으면 되고, 본문은 방송 장면과 온라인 반응이 어떻게 이어졌는지 담백하게 풀어쓴다.
- `왜 반응이 붙었는지`, `왜 관심이 몰렸는지`를 억지로 분석하지 않는다. `반응이 붙기 쉽습니다`, `공감 포인트가 생겼습니다`, `눈에 들어옵니다` 같은 해설 문구보다 기사 속 말과 짧은 감상을 먼저 쓴다.
- 독자를 가르치거나 훈계하지 않는다. `자극적으로 소비되기 쉽습니다`, `실제로 남겨야 할 건`, `조롱성 표현이 아니라` 같은 문장으로 줄을 채우지 말고, 기사에 나온 발언·의상·방송 장면·당사자 반응을 더 풀어서 녹인다.
- 소제목은 분석 라벨보다 장면형으로 쓴다. `반응이 커진 이유`, `핵심 포인트` 대신 `직접 남긴 말`, `예고편에 잡힌 한마디`, `드레스 장식에 붙은 반응`처럼 기사에서 실제로 보인 단어를 쓴다.
- `본문에서는`, `이번 글에서는`, `정리해보겠습니다`처럼 글을 설명하는 문장은 발행문에 넣지 않는다. 시작부터 기사 속 장면이나 발언으로 들어간다.
- `제목에 잡혔다`, `말이 이어졌다`, `표현이 붙었다` 같은 연결 문장을 반복하지 않는다. 반복이 보이면 단어만 바꾸지 말고 섹션 역할을 `주장`, `방송 장면`, `발언`, `후속 영상`, `당사자 입장`처럼 다시 나눈다.
- 글의 마지막 문장은 가급적 훈훈하게 닫는다. 별도 `마무리` 섹션을 억지로 추가하지는 말고, 마지막 단락이 있다면 `차분하게 정리되길 바랍니다`, `좋은 방향으로 이어지길 바랍니다` 정도로 부드럽게 마무리한다.

## 4-1. 시간당 5개 개별글 생성

```bash
python3 scripts/run_tistory_hourly_batch.py
```

현재 기본 설정은 `browser_publish`라서 운영 시간대에는 위 명령이 생성 후 티스토리 발행까지 진행한다. 발행 없이 파일 생성과 검증만 보려면:

```bash
python3 scripts/run_tistory_hourly_batch.py --force --no-record --no-publish
```

생성 위치:

```text
drafts/YYYY-MM-DD/HH/
  latest-entertainment-news.json
  manifest.json
  post-01/
    enriched.json
    post-title.txt
    post-title-candidates.txt
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

## 4-2. 티스토리 브라우저 자동 발행

현재 자동 입력 방식은 제목 입력칸에 제목을 넣고, 본문은 `더보기 > HTML블럭`에 `tistory-ready.html`의 본문 조각을 넣고, 태그 입력칸에 태그 10개를 넣는 흐름이다. 본문 HTML에서는 티스토리 제목과 중복되는 첫 `h1`, 하단 태그 문구는 제외한다.

글쓰기 화면에 한 개 글을 채워 넣기만 할 때:

```bash
python3 scripts/publish_tistory_browser.py \
  --blog-host goods99.tistory.com \
  --post-dir drafts/YYYY-MM-DD/HH/post-01
```

임시저장까지 누를 때:

```bash
python3 scripts/publish_tistory_browser.py \
  --blog-host goods99.tistory.com \
  --post-dir drafts/YYYY-MM-DD/HH/post-01 \
  --draft-save
```

시간당 배치 5개를 순서대로 발행할 때:

```bash
python3 scripts/publish_tistory_browser.py \
  --blog-host goods99.tistory.com \
  --manifest drafts/YYYY-MM-DD/HH/manifest.json \
  --publish
```

발행 성공 이력은 `logs/tistory-published.jsonl`에 남는다.

## 5. 현재 설정

```json
{
  "target": "tistory",
  "mode": "auto",
  "publish_mode": "browser_publish",
  "posts_per_run": 5,
  "news_display_per_query": 40,
  "news_limit": 80
}
```

태그는 티스토리 검증 스크립트 기준에 맞춰 정확히 10개로 유지한다.

## 6. 시간대별 자동 실행 등록

기본은 Codex 자동화 `daily-tistory-entertainment-draft`다. 설정 파일은 아래 위치에 있으며, 매시간 정각 실행되도록 바뀌어 있다. 실제 발행 여부는 `config/tistory-automation.json`의 `active_hours`가 제어하므로 3~6시는 자동으로 건너뛴다.

```bash
/Users/goods99j/.codex/automations/daily-tistory-entertainment-draft/automation.toml
```

Codex 자동화 대신 로컬 맥에서 직접 돌리고 싶으면 `launchd`를 등록한다.

```bash
scripts/install_tistory_hourly_launchd.sh
```

등록 후에는 macOS 로컬 시간 기준 `00:00`, `01:00`, `02:00`, `07:00`부터 `23:00`까지 매시간 실행된다.

로그:

```bash
logs/tistory-hourly-run.log
logs/launchd-tistory-hourly.out.log
logs/launchd-tistory-hourly.err.log
```

## 7. 주의

- `.env`는 커밋하지 않는다.
- `drafts/`, `logs/`는 자동 생성물이므로 커밋하지 않는다.
- 브라우저 자동화 발행은 로그인 세션, 에디터 UI 변경, 캡차/보안확인에 따라 멈출 수 있다.
