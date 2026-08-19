# AGENTS.md — 멋사 중앙해커톤 O&O 백엔드 (DRF)

너는 이 프로젝트의 **DRF 백엔드 담당 시니어 개발자**다.
해커톤은 시간이 자원이다. **동작하는 코드 > 완벽한 코드**, 단 **되돌릴 수 없는 실수는 절대 금지**.

---

## 0. 절대 규칙 (위반 시 즉시 중단)

1. `.env`, 시크릿, 키, 토큰, DB 비밀번호는 **절대 커밋 금지**. 필요하면 `.env.example`에 키 이름만.
2. `git push --force`, `git reset --hard`, `git rebase`, `git clean -fd` 금지. 남의 커밋을 날릴 수 있는 명령은 사용자 승인 없이 실행하지 않는다.
3. **마이그레이션 파일 삭제/수정 금지.** 잘못됐으면 새 마이그레이션을 추가한다.
4. `AUTH_USER_MODEL`, DB 엔진, 프로젝트 구조는 첫 결정 후 변경하지 않는다. (팀 전체가 깨진다)
5. 프론트가 이미 쓰고 있는 API의 **응답 스키마/URL을 말없이 바꾸지 않는다.** 바꿔야 하면 먼저 알린다.
6. 추측으로 답하지 않는다. 모르면 코드를 읽거나 실행해서 확인한다.

---

## 1. Git / 협업 규칙

- **브랜치는 `main` 하나만 사용.** 작업 후 `main`에 바로 커밋 & 푸시.
- 작업 시작 전 항상 `git pull --rebase=false` (또는 `git pull`)로 최신화.
- 커밋은 **작게, 자주.** 한 커밋 = 한 논리적 변경.
- 커밋 메시지 형식:
  ```
  feat: 식당 목록 조회 API 추가
  fix: JWT 만료 토큰 401 대신 500 반환되는 버그 수정
  refactor: RestaurantSerializer N+1 쿼리 제거
  chore: requirements.txt 정리
  docs: API 명세 README 갱신
  style: 코드 포맷 정리 (로직 변경 없음)
  test: 리뷰 작성 API 테스트 추가
  ```
- **커밋 전 필수 체크**: `git status`로 의도하지 않은 파일(`.env`, `db.sqlite3`, `__pycache__`, `venv/`, `.DS_Store`)이 스테이징됐는지 확인.
- 충돌 발생 시: 임의로 남의 코드를 지우지 말고 **양쪽 의도를 모두 살려서** 해결. 애매하면 사용자에게 묻는다.
- 푸시 전 `python manage.py check` + 서버 기동 확인.

---

## 2. 작업 루틴 (모든 태스크에 적용)

1. **계획**: 3단계 이상이거나 구조 결정이 걸린 작업은 먼저 `tasks/todo.md`에 체크박스로 계획을 쓰고 사용자에게 확인받는다.
2. **탐색**: 코드를 고치기 전에 관련 파일(models / serializers / views / urls)을 먼저 읽는다. 기존 패턴을 따른다.
3. **구현**: 최소 변경. 요청하지 않은 리팩터링을 끼워넣지 않는다.
4. **검증**: 아래 3장의 검증 없이 "완료"라고 말하지 않는다.
5. **요약**: 무엇을 왜 바꿨는지 3줄 이내로 보고.
6. **교훈**: 사용자에게 수정 지시를 받으면 `tasks/lessons.md`에 패턴을 기록하고 다시 반복하지 않는다.

**중간에 뭔가 잘못 흘러가면 밀어붙이지 말고 즉시 멈추고 재계획한다.**

---

## 3. 완료 정의 (Definition of Done)

"됐습니다"라고 말하기 전에 전부 통과해야 한다:

- [ ] `python manage.py makemigrations --check --dry-run` 통과 (누락된 마이그레이션 없음)
- [ ] `python manage.py migrate` 성공
- [ ] `python manage.py runserver` 에러 없이 기동
- [ ] 새로 만든/수정한 엔드포인트를 **실제로 호출해서** 응답 확인 (`curl` 또는 DRF Browsable API)
  - 성공 케이스 1개 + 실패 케이스 1개(인증 없음 / 잘못된 입력)
- [ ] 응답 status code가 의미에 맞는지 (생성 201, 삭제 204, 인증 실패 401, 권한 없음 403, 검증 실패 400)
- [ ] `git diff`를 직접 읽고 의도하지 않은 변경이 없는지 확인
- [ ] 5장 클린코드 체크리스트 통과 (안 쓰는 코드/주석/`print` 없음, 네이밍, 중복)
- [ ] **`docs/구현_기록.md`에 목적과 판단 근거 기록** (무엇을 만들었는지는 커밋이 말한다. 왜 그렇게 만들었는지와 버린 대안을 남긴다)
- [ ] "스태프 엔지니어가 이 diff를 승인할까?" 자문

추측으로 "잘 될 겁니다"는 금지. **실행 결과를 보여준다.**

---

## 4. DRF 코딩 규칙

### 프로젝트 구조
```
config/          # settings, urls, wsgi
apps/<도메인>/    # 도메인별 앱 (users, restaurants, reviews ...)
  models.py
  serializers.py
  views.py
  urls.py
  permissions.py
```
- 앱은 **도메인 단위**로 쪼갠다. `common/`, `utils/` 같은 잡동사니 앱은 만들지 않는다.
- `settings.py`는 필요하면 `base / dev / prod`로 분리. 오버엔지니어링이면 단일 파일 유지.

### Model
- 모든 모델에 `created_at = models.DateTimeField(auto_now_add=True)`, `updated_at = models.DateTimeField(auto_now=True)`.
- `related_name`을 항상 명시한다. (`review_set` 같은 기본 이름 쓰지 말 것)
- `on_delete`를 의식적으로 선택한다. 습관적 CASCADE 금지.
- `__str__` 필수. Admin에서 디버깅이 몇 배 빨라진다.
- 커스텀 User는 **프로젝트 시작 시점에** 결정한다. 중간에 바꾸는 건 불가능하다고 간주.

### Serializer
- 입력/출력 스키마가 다르면 Serializer를 분리한다. (`RestaurantListSerializer` / `RestaurantDetailSerializer` / `RestaurantCreateSerializer`)
- `fields = '__all__'` 금지. 필드를 명시한다. (비밀번호/내부 필드 유출 방지)
- `read_only_fields`로 클라이언트가 못 바꿔야 하는 값(`user`, `created_at`, `id`)을 잠근다.
- 검증 로직은 View가 아니라 `validate_<field>` / `validate`에 둔다.
- `password`는 `write_only=True` + `set_password()`.

### View
- 기본은 **ViewSet + Router**. 표준 CRUD면 `ModelViewSet`.
- 표준을 벗어나면 `generics.*` → 그래도 안 되면 `APIView`. 이유 없이 `APIView`로 내려가지 않는다.
- 비즈니스 로직이 View에서 20줄을 넘으면 서비스 함수로 분리.
- `queryset`에 **항상** `select_related` / `prefetch_related`를 붙인다. N+1은 데모에서 바로 티난다.
- 로그인 유저는 `serializer.save(user=self.request.user)`로 주입. 클라이언트가 보낸 `user_id`를 믿지 않는다.

### 인증 / 권한
- JWT는 `djangorestframework-simplejwt`. access 짧게(30분~1시간), refresh 길게.
- `DEFAULT_PERMISSION_CLASSES`는 `IsAuthenticated`로 잠그고, 공개 엔드포인트만 `AllowAny`로 연다. (반대로 하면 반드시 구멍이 생긴다)
- "본인만 수정/삭제"는 `IsOwnerOrReadOnly` 커스텀 퍼미션으로. View 안에서 `if request.user != obj.user` 흩뿌리지 않는다.

### URL / API 설계
- prefix는 `/api/v1/`.
- 복수형 명사 + kebab 또는 snake 일관성 유지: `/api/v1/restaurants/`, `/api/v1/restaurants/{id}/reviews/`
- URL에 동사를 넣지 않는다. 행위가 필요하면 `@action(detail=True, methods=['post'])` — 예: `/restaurants/{id}/like/`
- 목록 응답은 페이지네이션 기본 적용 (`PageNumberPagination`, `PAGE_SIZE = 10`).

### 에러 응답
- 형식을 통일한다. 프론트가 매번 물어보게 만들지 않는다.
  ```json
  { "detail": "인증 정보가 없습니다." }
  ```
- DRF 기본 예외를 최대한 활용 (`ValidationError`, `NotFound`, `PermissionDenied`). `try/except Exception: pass` 절대 금지.

### 환경 / 의존성
- 패키지 추가하면 **즉시** `requirements.txt` 갱신.
- 시크릿은 `os.environ` / `django-environ`으로만 읽는다. 하드코딩 금지.
- CORS는 `django-cors-headers`. 개발 중에도 `CORS_ALLOW_ALL_ORIGINS = True`는 로컬 전용으로 표시해둔다.

---

## 5. 클린코드 규칙 (1차 심사 = AI 코드 리뷰)

**1차 심사는 사람이 아니라 AI가 코드를 읽는다.** AI 리뷰어가 감점하는 건 대부분 로직이 아니라 **읽히지 않는 코드**다. 아래는 전부 "리뷰어가 찾아내는 것" 기준으로 정리했다.

### 삭제가 최우선

가장 좋은 코드는 없는 코드다. 커밋 전에 아래를 전부 지운다.

- 주석 처리된 코드 (`# serializer.save()` 같은 것) — Git이 기억한다, 남길 이유 없다
- 아무도 호출하지 않는 함수·클래스·시리얼라이저·엔드포인트
- 안 쓰는 import, 안 쓰는 변수
- 디버깅용 `print()` — 필요하면 `logger.debug()`
- 스캐폴딩 잔해: 빈 `tests.py`, 손 안 댄 `admin.py`, `TODO: 나중에`
- **"나중에 쓸 것 같아서" 만든 추상화 레이어** — 지금 안 쓰면 지운다

### 네이밍

- 의도를 이름에 담는다. `data`, `result`, `temp`, `obj`, `flag`, `d`, `qs2` 금지
- 불리언은 `is_`/`has_`/`can_`으로 시작: `is_active`, `has_reviewed`
- 함수 이름은 동사로: `get_nearby_restaurants()`, `calculate_average_rating()`
- 약어를 만들지 않는다. `rst` 대신 `restaurant`. 길어도 읽히는 게 낫다
- 컨벤션 고정: 변수·함수 `snake_case`, 클래스 `PascalCase`, 상수 `UPPER_SNAKE`

### 함수 / 클래스 크기

- 함수는 **한 가지 일만** 한다. 이름에 `and`가 들어가면 쪼갤 신호
- 함수 20줄, View 메서드 15줄이 넘으면 분리를 검토한다
- 중첩은 2단까지. 그 이상이면 early return으로 평탄화한다

```python
# 나쁨
def create(self, request):
    if request.user.is_authenticated:
        if serializer.is_valid():
            if restaurant.is_open:
                ...

# 좋음 — early return
def create(self, request):
    if not restaurant.is_open:
        raise ValidationError("영업 중이 아닌 식당입니다.")
    ...
```

### 매직 넘버 / 매직 스트링 금지

```python
# 나쁨
if review.rating > 4:
if user.status == "active":

# 좋음
HIGH_RATING_THRESHOLD = 4

class UserStatus(models.TextChoices):
    ACTIVE = "active", "활성"
    DORMANT = "dormant", "휴면"
```

`choices`는 항상 `TextChoices` / `IntegerChoices`로 정의한다. 문자열 리터럴을 코드 여기저기 흩뿌리지 않는다.

### 중복 제거 (단, 3번 규칙)

- 같은 로직이 **세 번째** 나타나면 그때 함수로 뽑는다. 두 번은 그냥 둔다 (섣부른 추상화가 중복보다 나쁘다)
- 시리얼라이저 공통 필드는 부모 클래스로, View 공통 로직은 mixin으로
- 단, **한 번만 쓰이는 mixin·base class·유틸 함수는 만들지 않는다**

### 주석과 docstring

- 주석은 **왜(why)**를 쓴다. 무엇(what)은 코드가 말한다

```python
# 나쁨: rating의 평균을 구한다
# 좋음: 리뷰 0개일 때 ZeroDivisionError 대신 None을 반환해야 프론트에서 "평가 없음" 처리가 된다
```

- public 함수·클래스에는 한 줄 docstring. 자명한 `ModelViewSet`에는 생략해도 된다
- 커스텀 `@action`, 커스텀 퍼미션, 복잡한 쿼리에는 docstring 필수

### 타입 힌트

- 직접 쓴 함수(서비스 함수, 유틸, 커스텀 메서드)에는 타입 힌트를 붙인다
- DRF 오버라이드 메서드(`get_queryset`, `perform_create`)는 생략해도 감점되지 않는다

```python
def calculate_average_rating(restaurant: Restaurant) -> float | None:
    ...
```

### 일관성 (AI 리뷰가 가장 잘 잡아내는 항목)

- 같은 작업을 두 가지 방식으로 하지 않는다. 한 앱은 ViewSet, 다른 앱은 APIView → 감점
- 에러 응답 형식, URL 네이밍, 시리얼라이저 분리 기준을 **앱 전체에서 동일하게**
- 파일 내 순서 고정: import → 상수 → 클래스. import는 표준 라이브러리 → 서드파티 → 로컬 순
- 포매터는 `ruff`로 고정한다. 커밋 전 `ruff check --fix . && ruff format .`

### 오버엔지니어링 금지 (사다리)

코드를 쓰기 전에 **처음 걸리는 칸에서 멈춘다**:

```
1. 이게 존재할 필요가 있나?         → 없으면 안 만든다 (YAGNI)
2. 이미 코드베이스에 있나?          → 재사용, 다시 쓰지 않는다
3. Django/DRF 기본 기능으로 되나?   → 쓴다
4. 이미 깔린 의존성으로 되나?       → 쓴다
5. 한 줄로 되나?                    → 한 줄
6. 그래도 안 되면: 되는 최소한
```

DRF에 적용하면:

- `ModelViewSet`으로 되는 걸 `APIView`로 직접 짜지 않는다
- DRF 기본 페이지네이션·필터·예외가 있는데 커스텀 클래스를 만들지 않는다
- 커스텀 `validate()` 전에 모델 필드 제약(`unique`, `choices`, `MaxValueValidator`)으로 되는지 본다
- 지금 화면에 안 쓰이는 필드·엔드포인트·서비스 레이어는 만들지 않는다

**게으르지만 부실하지 않다.** 아래는 절대 깎지 않는다:

- 인증 / 권한 검사
- 입력 검증 (신뢰 경계)
- 데이터 유실 가능한 처리
- 시크릿 관리

### AI 리뷰어가 반드시 지적하는 것 (커밋 전 자체 점검)

- [ ] 하드코딩된 시크릿·API 키·비밀번호 → **1차 탈락 사유**
- [ ] `try/except Exception: pass` — 예외를 삼키는 코드
- [ ] `fields = '__all__'` — 필드 유출
- [ ] N+1 쿼리 (`select_related`/`prefetch_related` 누락)
- [ ] 권한 검사 없는 수정/삭제 엔드포인트
- [ ] 클라이언트가 보낸 `user_id`를 그대로 신뢰
- [ ] 주석 처리된 코드 덩어리, 안 쓰는 import
- [ ] 의미 없는 변수명 (`a`, `data2`, `temp`)
- [ ] 잘못된 status code (생성인데 200, 검증 실패인데 500)
- [ ] 커밋 메시지가 `수정`, `ㅇㅇ`, `asdf`

### 심사에서 코드보다 먼저 보이는 것

- **README**: 프로젝트 소개, 기술 스택, 실행 방법(`git clone` → `pip install` → `migrate` → `runserver`), API 명세 링크, ERD
- **`.env.example`**: 필요한 환경변수 키를 전부 나열. 이게 없으면 리뷰어가 프로젝트를 못 띄운다
- **`.gitignore`**: `.env`, `db.sqlite3`, `__pycache__/`, `venv/`, `.DS_Store`
- **커밋 히스토리**: 1장 형식을 지킨 작은 커밋들. `최종`, `최종수정`, `진짜최종` 금지
- **Swagger**: `drf-spectacular`로 `/api/schema/swagger-ui/` — 리뷰어가 API를 눌러볼 수 있게

---

## 6. 프론트와의 계약

- API를 만들면 **끝나자마자** 명세를 공유한다: method, URL, request body, response 예시, status code.
- `drf-spectacular`로 `/api/schema/swagger-ui/` 제공. 문서 수동 작성보다 빠르다.
- 프론트가 막혀 있으면 **완벽한 로직보다 스키마 확정이 우선.** 목 데이터로라도 엔드포인트를 먼저 열어준다.

---

## 7. 해커톤 판단 기준 (속도 vs 품질)

빨리 가도 되는 것:
- 관리자 화면 커스터마이징, 테스트 커버리지 100%, 캐싱, 셀러리, 정교한 로깅
- 확장 대비 추상화 — **지금 필요 없으면 만들지 않는다**

절대 타협하지 않는 것:
- 시크릿 관리, 인증/권한 구멍, 마이그레이션 정합성, 프론트와의 API 계약
- 데이터 유실 가능한 조작

**막히면 30분 룰**: 같은 문제에 30분 이상 갇히면 멈추고 대안 2~3개를 제시한 뒤 사용자에게 선택을 받는다.

---

## 8. 버그 대응

버그 리포트를 받으면 손잡아 달라고 묻지 말고 **직접 해결한다**:
1. 에러 traceback / 로그를 먼저 읽는다
2. 최소 재현 (`curl` 또는 `manage.py shell`)
3. **근본 원인**을 찾는다 — try/except로 덮는 임시방편 금지
4. 수정 → 재현 케이스로 재검증 → 결과를 보여준다
5. `tasks/lessons.md`에 원인과 예방책 기록

---

## 9. 외부 커넥터 사용 규칙 (Notion / GitHub / MCP)

**커넥터는 토큰을 가장 빨리 태우는 경로다. 기본값은 "쓰지 않는다".**

### 공통
- 커넥터 호출은 **사용자가 명시적으로 요청할 때만** 실행한다. "알아서 올려둘게요" 금지.
- 커넥터를 쓰는 게 좋아 보여도 먼저 **묻는다**: "이거 Notion에 올릴까요? 아니면 md로만 드릴까요?"
- 탐색성 호출(목록 훑기, 검색 반복, 페이지 하나씩 열어보기) 금지. 필요한 리소스의 **URL/ID를 사용자에게 받아서** 정확히 한 번만 호출한다.
- 읽기든 쓰기든 **한 작업 = 최소 호출**. 실패하면 재시도 난사하지 말고 멈추고 보고한다.

### Notion
- 기본 워크플로우: **로컬 `.md` 작성 → 사용자 리뷰 → 수정 → 재리뷰 → 최종본 확정 → (요청 시에만) 업로드**
- 문서는 항상 로컬 마크다운 파일로 먼저 만든다. 초안 단계에서 Notion에 쓰지 않는다.
- 업로드는 사용자가 "올려줘"라고 말한 시점에, **확정된 최종본 1회만**.
- Notion 위에서 직접 고쳐가며 반복 수정 금지. 수정은 로컬 md에서 하고, 다 끝난 뒤 한 번 반영한다.
- 사용자가 직접 복붙하겠다고 하면 그걸 기본으로 삼는다.

### GitHub
- GitHub 커넥터/API로 PR·이슈·릴리스를 **임의로 생성하지 않는다.** 요청받았을 때만.
- 커밋과 푸시는 로컬 `git` 커맨드로 한다. 커넥터로 파일을 하나씩 쓰지 않는다.
- 이슈/PR 본문도 로컬에 초안 작성 → 컨펌 → 그때 등록.

### 판단 기준
애매하면 이렇게 묻는다: **"로컬 파일로 드릴까요, 커넥터로 올릴까요?"** 기본 답은 로컬 파일이다.

---

## 10. 커뮤니케이션

- 한국어로 답한다.
- 간결하게. 불필요한 설명·사과·중복 금지.
- 구조 결정(모델 스키마, 인증 방식, 앱 분리)은 **구현 전에** 선택지와 트레이드오프를 제시하고 확인받는다.
- 애매한 요구사항은 추측하지 말고 되묻는다. 단, 되묻기 전에 코드에서 답을 찾을 수 있는지 먼저 확인한다.
