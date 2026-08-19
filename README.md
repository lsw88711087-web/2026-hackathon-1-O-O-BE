# 2026-hackathon-1-O-O-BE

2026 중앙해커톤 1조 백엔드입니다.

명품 매장 인터랙티브 리테일 서비스 **O&O**. 로그인 없이 매장을 구경한 방문자의 행동을
모아 개인 취향 리포트를 만들고, 같은 데이터를 브랜드 대시보드로 제공한다.

- **API 필드 가이드(프론트 필독)**: [`docs/필드_가이드.md`](docs/필드_가이드.md) — 각 필드가 왜 있고 무엇을 해야 하는지
- **구현 기록**: [`docs/구현_기록.md`](docs/구현_기록.md) — 각 기능을 왜 그렇게 만들었는지, 버린 대안은 무엇인지
- API 문서(스키마): `/api/schema/swagger-ui/`
- 기획: [`기획.md`](기획.md) · 결정 사항: [`tasks/결정사항.md`](tasks/결정사항.md) · 마일스톤: [`tasks/마일스톤.md`](tasks/마일스톤.md)

## 기술 스택

Django 5.1 · Django REST Framework · SQLite(WAL) · simplejwt · drf-spectacular · OpenAI API

## 실행 방법

```bash
git clone <repo> && cd oando
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DJANGO_SECRET_KEY, OPENAI_API_KEY 채우기
python manage.py migrate
python manage.py runserver
```

SSE(챗봇 스트리밍)를 배포와 같은 조건에서 확인할 때는 gunicorn으로 띄운다.

```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --worker-class gthread --workers 2 --threads 4 --timeout 300
```

⚠️ **uvicorn(ASGI)으로 띄우면 스트리밍이 죽는다.** `respond()`가 동기 제너레이터라
Django가 `sync_to_async(list)`로 전부 소비한 뒤 내보낸다(응답은 200인데 조각이 안 흐른다).
`async def` + `async for`로 바꾸기 전까지는 WSGI가 맞다.

브라우저에서 `http://127.0.0.1:8000/api/schema/swagger-ui/` 확인.

## 초기 데이터

```bash
python manage.py createsuperuser   # 브랜드 관리자 계정 (username에 이메일을 넣는다)
```

상품·전시존은 `/django-admin/`에서 입력·검수한다. 상품 1개당 8개 분류 축
(`category` `color` `material` `pattern` `silhouette` `mood` `price_band` `use_case`)을
반드시 채워야 취향 분석이 동작한다. 값 목록은 `apps/catalog/models.py`의 TextChoices가 진실.

## 구조

```
config/     설정 · 루트 URL · ASGI
apps/
  visits/     Visitor, Visit (익명 UUID · visit_token · 이어하기)
  catalog/    Store, Scene, Product (분석 축 8개를 컬럼으로 가짐)
  events/     Event (append-only 행동 로그)
  chat/       ChatLog (클릭이 쌓이는 타임라인 + AI 문맥)
  analysis/   TasteProfile, Report (비동기 분석 결과 박제)
  dashboard/  브랜드 관리자 API (모델 없음 — 기본 User 사용)
api/        공용 HTTP 관심사 (visit_token 인증 · 공통 에러 포맷 · v1 라우팅)
common/     인프라 (식별자 생성 등)
```

## 인증

| 대상 | 방식 |
| --- | --- |
| 사용자 API | 로그인 없음. `X-Anonymous-UUID` · `X-Visit-Token` 헤더 |
| `/api/v1/admin/*` | `Authorization: Bearer <access_token>` (`POST /admin/auth`로 발급) |

## 에러 형식

모든 에러가 같은 모양이다.

```json
{ "error": { "code": "INVALID_VISIT_TOKEN", "message": "유효하지 않거나 만료된 visit token 입니다.", "detail": null } }
```

`VALIDATION_ERROR`(400) · `INVALID_VISIT_TOKEN`/`UNAUTHORIZED`(401) · `NOT_FOUND`(404) ·
`CONFLICT`(409) · `RATE_LIMITED`(429) · `INTERNAL_ERROR`(500)

## 개발 규칙

- `.env`는 커밋하지 않는다. 키를 추가하면 `.env.example`에 이름만 추가한다.
- 커밋 전: `ruff check --fix . && ruff format .`
- 마이그레이션 파일은 수정·삭제하지 않는다. 잘못됐으면 새 마이그레이션을 추가한다.
- SQLite를 쓰므로 **쓰기 트랜잭션을 짧게** 유지한다. 분석 계산을 끝낸 뒤 저장 한 번만 감싼다.
