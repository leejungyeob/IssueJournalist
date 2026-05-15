# 티스토리 시간별 자동 발행 목표

## 목표

매일 07:00부터 다음날 02:00까지 매시간 연예뉴스 글 5개를 자동 발행한다.

```text
20회/일 * 5개/회 = 100개/일
```

## 현재 구현

현재 구현은 아래 단계까지 가능하다.

```text
뉴스 수집 -> 시간당 이슈 5개 선택 -> 개별글 5개 생성 -> 대표이미지 5개 생성 -> 검증 -> Chrome 브라우저 자동 발행
```

현재 실행 명령:

```bash
python3 scripts/run_tistory_hourly_batch.py
```

현재 산출물은 `drafts/YYYY-MM-DD/HH/post-01..05/`에 나뉘어 저장되고, 기본 설정에서는 로그인된 Chrome을 통해 티스토리에 바로 발행한다.

선택 우선순위:

```text
네이트 연예 조회순 랭킹
-> 이미 발행/큐 등록한 URL 또는 제목 스킵
-> 랭킹 후보 부족 시 공개 RSS 최신 연예뉴스로 보충
```

## 자동 발행 구조

최종 자동 발행은 아래 구조로 바꾼다.

```text
스케줄러
-> 시간별 실행 판단
-> 뉴스 수집
-> 중복 제거
-> 상위 이슈 5개 선택
-> 이슈별 티스토리 글 5개 렌더링
-> 대표이미지 5개 생성
-> 검증
-> 티스토리 브라우저 자동화로 발행
-> 발행 로그 저장
```

## 스케줄

KST 기준으로 아래 시간에 실행한다.

```text
07:00
08:00
09:00
10:00
11:00
12:00
13:00
14:00
15:00
16:00
17:00
18:00
19:00
20:00
21:00
22:00
23:00
00:00
01:00
02:00
```

## 운영 명령

발행 없이 산출물만 검증한다.

```bash
python3 scripts/run_tistory_hourly_batch.py --force --no-record --no-publish
```

현재 시간대가 `active_hours`에 포함되면 5개 글을 생성하고 발행한다.

```bash
python3 scripts/run_tistory_hourly_batch.py
```

Codex 자동화 `daily-tistory-entertainment-draft`가 매시간 정각 실행되도록 설정되어 있다. 실제 발행 시간대는 `config/tistory-automation.json`의 `active_hours`가 제어하므로 3~6시는 스크립트가 자동으로 건너뛴다. Codex 자동화 대신 로컬 맥에서 직접 돌리고 싶으면 macOS `launchd`에 등록한다.

```bash
scripts/install_tistory_hourly_launchd.sh
```

성공한 발행 이력은 `logs/tistory-published.jsonl`에 저장한다. 선택 이력은 `logs/tistory-issued.jsonl`에도 남겨 같은 URL/제목을 다시 고르지 않게 한다.

## 운영 리스크

하루 100개 발행은 플랫폼 스팸 판정 위험이 크다.

기술적으로는 구현되어 있지만, 운영 리스크는 여전히 있다. 문제가 생기면 아래 순서로 낮춘다.

```text
시간당 5개 초안 생성
-> 시간당 5개 임시저장
-> 제한된 시간대 자동 발행
-> 전체 시간대 자동 발행
```

## API 참고

티스토리 Open API 문서에는 글 작성 API가 남아 있지만, 티스토리 공지에 따르면 Open API는 종료됐다. 따라서 자동 발행은 브라우저 자동화 기준으로 구현한다.
