# 회사에서 이어서 실행할 작업

## 현재 상태

네이버 블로그 완전 자동화 방향으로 전환했다.

- 운영 목표: `full_auto`
- 이미지 모드: `aggressive`
- 발행 모드: `auto_publish`
- 기본 발행 수: 실행당 5개 글
- 기본 이미지 수: 글당 3장

설정 파일:

```bash
config/naver-blog-automation.json
```

전체 전략 문서:

```bash
docs/naver-blog-entertainment-automation-strategy.md
```

## 1. 회사에서 먼저 받을 것

```bash
git pull origin main
```

## 2. 네이버 개발자센터에서 확인할 값

네이버 개발자센터 > 내 애플리케이션 > 해당 앱에서 확인한다.

```env
NAVER_BLOG_CLIENT_ID=Client ID
NAVER_BLOG_CLIENT_SECRET=Client Secret
```

이 두 값은 개발자센터 화면에서 직접 확인한다.

## 3. `.env`에 우선 넣을 값

프로젝트 루트의 `.env`에 아래 값을 추가한다.

```env
NAVER_BLOG_CLIENT_ID=개발자센터_Client_ID
NAVER_BLOG_CLIENT_SECRET=개발자센터_Client_Secret
```

기존 뉴스 검색 API 키도 필요하다.

```env
NAVER_CLIENT_ID=뉴스검색_Client_ID
NAVER_CLIENT_SECRET=뉴스검색_Client_Secret
```

같은 앱 키를 뉴스 검색과 블로그 OAuth에 같이 쓸 수 있으면 같은 값으로 넣어도 된다. 단, 네이버 개발자센터에서 API 권한에 뉴스 검색과 블로그 관련 권한이 모두 켜져 있어야 한다.

## 4. Callback URL 확인

네이버 개발자센터의 로그인 오픈 API 서비스 환경은 `PC 웹`으로 추가한다.

로컬 테스트용으로 등록한 값:

```text
서비스 URL: http://localhost:8080
Callback URL: http://localhost:8080/naver/callback
```

네이버가 `localhost`를 거부하면 ngrok 같은 터널 URL을 등록한다.

```text
서비스 URL: https://YOUR-NGROK.ngrok-free.app
Callback URL: https://YOUR-NGROK.ngrok-free.app/naver/callback
```

중요: 토큰 발급 때 `--redirect-uri`로 넣는 값은 개발자센터의 Callback URL과 완전히 같아야 한다.

## 5. 로그인 URL 만들기

```bash
python3 scripts/naver_blog_oauth_helper.py auth-url \
  --redirect-uri "http://localhost:8080/naver/callback"
```

출력 예시:

```text
# state=...
https://nid.naver.com/oauth2.0/authorize?...
```

출력된 URL을 브라우저에서 열고 네이버 로그인/동의를 진행한다.

## 6. code/state 확인

동의가 끝나면 브라우저 주소창이 아래처럼 바뀐다.

```text
http://localhost:8080/naver/callback?code=CODE_VALUE&state=STATE_VALUE
```

페이지가 안 열려도 괜찮다. 주소창의 `code`와 `state`만 복사한다.

## 7. Access/Refresh Token 발급

```bash
python3 scripts/naver_blog_oauth_helper.py exchange \
  --redirect-uri "http://localhost:8080/naver/callback" \
  --code "CODE_VALUE" \
  --state "STATE_VALUE"
```

출력되는 값을 `.env`에 추가한다.

```env
NAVER_BLOG_ACCESS_TOKEN=...
NAVER_BLOG_REFRESH_TOKEN=...
```

## 8. 블로그 카테고리 ID 조회

```bash
python3 scripts/naver_blog_oauth_helper.py categories
```

출력 JSON에서 사용할 카테고리 ID를 골라 `.env`에 추가한다.

```env
NAVER_BLOG_CATEGORY_ID=카테고리ID
```

## 9. Access Token 갱신

Access Token은 만료될 수 있으므로 필요하면 갱신한다.

```bash
python3 scripts/naver_blog_oauth_helper.py refresh
```

새로 출력되는 `NAVER_BLOG_ACCESS_TOKEN`으로 `.env` 값을 교체한다.

## 10. 프리플라이트 실행

```bash
python3 scripts/run_naver_blog_automation.py --preflight
```

현재는 아래 파이프라인 스크립트가 아직 구현 전이라 preflight가 실패하는 것이 정상이다.

```text
scripts/enrich_entertainment_issue.py
scripts/render_naver_blog_post.py
scripts/create_naver_blog_images.py
scripts/validate_naver_blog_post.py
scripts/publish_naver_blog.py
```

다음 구현 순서:

1. `enrich_entertainment_issue.py`: 기사별 OG 이미지/본문 이미지 후보 수집, 중복 제거
2. `render_naver_blog_post.py`: 예시 블로그 스타일의 1이슈 1포스트 생성
3. `create_naver_blog_images.py`: 이미지 후보 선택, 리사이즈, 카드 보강
4. `validate_naver_blog_post.py`: 글자 수, 태그, 이미지 수, 금칙어, 출처 검사
5. `publish_naver_blog.py`: 네이버 블로그 API 또는 브라우저 자동화로 발행

## 11. 현재 자동화 설정

```json
{
  "mode": "full_auto",
  "image_mode": "aggressive",
  "publish_mode": "auto_publish",
  "posts_per_run": 5,
  "images_per_post": 3,
  "fallback_generated_images": true,
  "dedupe_images": true,
  "block_blog_images": true,
  "block_watermarked_images": true,
  "log_sources": true,
  "retry_count": 2,
  "min_body_chars": 1200,
  "max_body_chars": 2200,
  "min_tags": 12,
  "max_tags": 20
}
```

## 12. 주의

- `.env`는 커밋하지 않는다.
- `ACCESS_TOKEN`과 `REFRESH_TOKEN`은 외부에 올리지 않는다.
- 이미지 자동 수집은 `aggressive`로 잡았지만, 워터마크 제거/출처 은폐/타 블로그 이미지 재업로드는 자동 차단한다.
- 발행 로그와 원본 이미지 URL은 반드시 남긴다.
