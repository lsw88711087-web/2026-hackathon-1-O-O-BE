# 배포 가이드 (가비아 클라우드 VM)

서버를 받은 날 위에서부터 순서대로 실행한다. 처음 한 번은 30~40분 걸린다.

## 전제

| 항목 | 값 |
| --- | --- |
| 서버 | 가비아 High CPU · 2vCore · 4GB · 공인 IP 1개 |
| OS | Ubuntu 22.04 LTS (24.04도 동일하게 동작) |
| 앱 위치 | `/srv/oando` |
| 프론트 | Netlify (HTTPS) |
| 서버 사용 기간 | 8/18 ~ **8/28 23:59 자동 삭제** |

### 왜 HTTPS가 필수인가

프론트가 Netlify(HTTPS)에 올라간다. **HTTPS 페이지에서 HTTP API를 호출하면 브라우저가 차단한다**(mixed content). 서버에 IP만 있고 인증서가 없으면 프론트 연동 자체가 안 된다.

도메인을 사지 않고 HTTPS를 얻기 위해 **sslip.io**를 쓴다. IP의 점을 하이픈으로 바꾼 주소가 그대로 그 IP를 가리키는 공개 DNS 서비스다.

```
서버 IP  211.234.1.2
도메인    211-234-1-2.sslip.io      ← 이 주소로 Let's Encrypt 인증서를 발급받는다
```

아래에서 `211-234-1-2.sslip.io`가 나오면 **본인 서버 IP로 바꿔서** 쓴다.

---

## 1. 서버 접속과 기본 패키지

가비아 콘솔에서 방화벽/보안그룹에 **22, 80, 443** 포트를 열어둔다. 열려 있지 않으면 인증서 발급(80 포트 검증)부터 실패한다.

가비아는 브라우저 터미널로 `root` 접속이 기본이다(SSH 키페어를 고르면 브라우저 터미널을 못 쓴다).
공인 IP가 붙어 있으면 로컬에서 SSH로도 들어갈 수 있다.

```bash
ssh root@211.234.1.2
```

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip git nginx certbot python3-certbot-nginx \n    postgresql postgresql-contrib redis-server
```

## 2. 코드 배치

앱을 root로 돌리지 않는다. 전용 계정을 만들고 그 계정 소유로 둔다.

```bash
adduser --system --group --home /srv/oando oando
sudo -u oando git clone https://github.com/LikeLion-at-DGU/2026-hackathon-1-O-O-BE.git /srv/oando
```

> 조직 레포(`LikeLion-at-DGU`)가 기준이다. 개인 포크를 clone하면 팀 최신 코드가 아니다.

## 3. 가상환경과 의존성

```bash
cd /srv/oando
sudo -u oando python3 -m venv venv
sudo -u oando ./venv/bin/pip install -U pip
sudo -u oando ./venv/bin/pip install -r requirements.txt
```

## 4. PostgreSQL · Redis

**둘 다 외부에 열지 않는다.** Django와 같은 서버에 있으므로 `127.0.0.1`로만 붙는다.
가비아 보안그룹에 5432·6379를 추가하지 않는다.

```bash
sudo -u postgres psql -c "CREATE USER oando WITH PASSWORD '강한비밀번호';"
sudo -u postgres psql -c "CREATE DATABASE oando OWNER oando;"
psql "postgresql://oando:강한비밀번호@127.0.0.1:5432/oando" -c "SELECT 1;"
redis-cli ping
```

`1`과 `PONG`이 나오면 된다.

### 왜 SQLite가 아닌가

관람 이벤트 배치·챗봇 로그·리포트 워커·화보 워커가 동시에 쓴다. SQLite는 쓰기가 DB
전체를 잠그므로, **심사가 끝나고 사람들이 동시에 창을 닫아 이벤트 버퍼가 몰리는 순간**
`database is locked`가 날 수 있다. 하필 그때 고칠 시간이 없다.

전환 비용은 거의 없다 — `settings.py`가 이미 `DATABASE_URL`로 갈라져 있어 코드 변경이 0줄이다.

### 왜 Redis가 필요한가

화보 진행률을 Django 캐시에 둔다. gunicorn 워커가 2개인데 캐시가 LocMem이면
**프로세스마다 캐시가 따로 놀아 폴링이 404**가 난다. `REDIS_URL`을 비워두면 안 된다.

## 5. `.env` 작성

```bash
cd /srv/oando && cp .env.example .env && nano .env
```

`211-234-1-2`와 Netlify 사이트 이름, 키 값을 실제 값으로 채운다.

```ini
DJANGO_SECRET_KEY=<아래 명령으로 생성>
DEBUG=False
ALLOWED_HOSTS=211-234-1-2.sslip.io,211.234.1.2
CORS_ALLOWED_ORIGINS=https://oando.netlify.app
CORS_ALLOWED_ORIGIN_REGEXES=^https://[a-z0-9-]+--oando\.netlify\.app$
CSRF_TRUSTED_ORIGINS=https://211-234-1-2.sslip.io
CORS_ALLOW_ALL_ORIGINS=False
DEFAULT_STORE_ID=s_mcm
OPENAI_API_KEY=<발급받은 키>
OPENAI_MODEL=gpt-4o-mini

DATABASE_URL=postgresql://oando:강한비밀번호@127.0.0.1:5432/oando
REDIS_URL=redis://127.0.0.1:6379/0

# 이미지 생성 벤더가 붙기 전까지는 가짜 결과로 화보 흐름을 돌린다.
# False로 바꾸면 NotImplementedError가 난다.
LOOKBOOK_FAKE_AI=True
```

시크릿 키 생성:

```bash
/srv/oando/venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`CORS_ALLOWED_ORIGIN_REGEXES`가 필요한 이유는 Netlify의 PR 미리보기와 브랜치 배포가 `deploy-preview-3--oando.netlify.app`처럼 매번 다른 주소를 쓰기 때문이다. 고정 목록만으로는 미리보기에서 API가 전부 막힌다.

## 6. DB · 정적 파일 · 관리자 계정

```bash
cd /srv/oando
sudo -u oando ./venv/bin/python manage.py check --deploy
sudo -u oando ./venv/bin/python manage.py migrate
sudo -u oando ./venv/bin/python manage.py collectstatic --noinput
sudo -u oando ./venv/bin/python manage.py createsuperuser
```

`collectstatic`을 빼먹으면 `django-admin` 화면이 CSS 없이 깨진 채로 뜬다. 상품 데이터를 admin에서 입력할 거라 실제로 문제가 된다.

시연용 임시 데이터가 필요하면:

```bash
cd /srv/oando
sudo -u oando ./venv/bin/python manage.py seed_demo
sudo -u oando ./venv/bin/python manage.py seed_characters
sudo -u oando ./venv/bin/python manage.py seed_compositions
```

> **관리자 로그인은 HTTPS를 붙인 뒤에 시도한다.** `DEBUG=False`면 세션 쿠키가 secure로
> 나가서, 아직 http인 상태에서는 비밀번호가 맞아도 로그인이 되지 않는다.

## 7. 앱을 서비스로 등록

```bash
sudo cp /srv/oando/deploy/oando.service /etc/systemd/system/oando.service
sudo systemctl daemon-reload && sudo systemctl enable --now oando
sudo systemctl status oando --no-pager
```

`active (running)`이 아니면 로그를 본다:

```bash
sudo journalctl -u oando -n 50 --no-pager
```

## 8. nginx

```bash
sudo cp /srv/oando/deploy/nginx.conf /etc/nginx/sites-available/oando
sudo sed -i 's/SERVER_NAME/211-234-1-2.sslip.io/' /etc/nginx/sites-available/oando
sudo ln -sf /etc/nginx/sites-available/oando /etc/nginx/sites-enabled/oando
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

여기까지 하면 `http://211-234-1-2.sslip.io/api/schema/swagger-ui/`가 뜬다. 아직 HTTP다.

## 9. HTTPS 발급

```bash
sudo certbot --nginx -d 211-234-1-2.sslip.io --redirect --agree-tos -m <팀메일주소> --no-eff-email
```

certbot이 nginx 설정에 443 블록을 추가하고 80을 리다이렉트로 바꾼다. 끝나면 확인:

```bash
curl -I https://211-234-1-2.sslip.io/api/schema/swagger-ui/
```

`HTTP/1.1 200 OK`가 나오면 성공이다.

## 10. 프론트에 전달할 값

```
API BASE   https://211-234-1-2.sslip.io/api/v1
Swagger    https://211-234-1-2.sslip.io/api/schema/swagger-ui/
관리자     https://211-234-1-2.sslip.io/django-admin/
```

Netlify 사이트 주소가 정해지면 `.env`의 `CORS_ALLOWED_ORIGINS`에 넣고 서비스를 재시작한다.

---

## 코드 갱신 (배포 후 매번)

```bash
cd /srv/oando
sudo -u oando git pull
sudo -u oando ./venv/bin/pip install -r requirements.txt
sudo -u oando ./venv/bin/python manage.py migrate
sudo -u oando ./venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart oando
```

> 재시작하면 **진행 중인 리포트·화보 생성 스레드가 사라진다.** 둘 다 백그라운드 스레드로
> 돌기 때문이다. 데모 중에는 생성 작업이 없는 순간에 재배포한다.

## 상태 확인 · 로그

```bash
sudo systemctl status oando --no-pager
sudo journalctl -u oando -f
```

## 백업 — 8/28에 반드시

서버는 **8/28 23:59에 통보 없이 삭제된다.** 데모가 끝나면 즉시 실행한다.

```bash
bash /srv/oando/deploy/backup.sh
```

만들어진 `.tar.gz`를 **로컬로 내려받는다.** 서버에만 두면 같이 사라진다.

```bash
scp root@211.234.1.2:/srv/oando/backups/oando-*.tar.gz .
```

---

## 막혔을 때

| 증상 | 원인 | 확인 |
| --- | --- | --- |
| 502 Bad Gateway | gunicorn이 안 떠 있음 | `sudo journalctl -u oando -n 50` |
| 관리자 화면 CSS 깨짐 | `collectstatic` 누락 | `ls /srv/oando/staticfiles/admin` |
| 상품 이미지 안 보임 | nginx `/media/` 경로 오타 | `ls /srv/oando/media` |
| 프론트에서 CORS 에러 | `CORS_ALLOWED_ORIGINS`에 Netlify 주소 누락 | `.env` 확인 후 `restart` |
| 챗봇 답변이 한 번에 몰려서 나옴 | nginx가 SSE를 버퍼링 | `nginx.conf`의 `proxy_buffering off` 확인 |
| DisallowedHost 400 | `ALLOWED_HOSTS`에 도메인 누락 | `.env` 확인 |
| 인증서 발급 실패 | 80 포트 차단 | 가비아 콘솔 방화벽 |
| 화보 폴링이 404 | `REDIS_URL` 비어 있음 (워커마다 캐시가 따로 놈) | `.env` 확인 후 `restart` |
| 관리자 로그인이 안 됨 | http에서 secure 쿠키 | HTTPS 발급 후 재시도 |
| `database is locked` | SQLite로 돌고 있음 | `.env`의 `DATABASE_URL` 확인 |

기술지원은 **8/21 18:00까지**다(gajet@gabia.com). 서버 자체 문제는 그 전에 해결해야 한다.
