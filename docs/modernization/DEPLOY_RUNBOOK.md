# 12A1 — 배포 런북(준비 단계)

상태: 저장소 쪽 준비만 끝난 상태. **실제 호스트 생성·도메인 연결·배포 실행은 별도 승인이며
이 문서의 어느 명령도 아직 실행하지 않았다.** 대상 형태는 AWS EC2 한 대, 도메인, HTTPS, nginx.
구성의 근거는 [배포 후보(4A3)](DEPLOYMENT_CANDIDATE.md)와 D-046·D-070이다.

## 구성 요약

| 파일 | 역할 |
| --- | --- |
| `compose.prod.yaml` | 후보 스택(4A3). 그대로 쓴다 |
| `compose.tls.yaml` | 12A1 오버레이. 프록시가 80/443을 발행하고 인증서·ACME 웹루트를 마운트한다. 로그 회전 |
| `scripts/nginx_tls/*.template` | 프록시 설정 템플릿. `render_nginx.sh`가 도메인을 넣어 `tls/conf.d/`로 렌더링(미커밋) |
| `scripts/deploy/server_setup.sh` | 호스트 1회 준비(docker, certbot, envsubst, 웹루트, 갱신 훅) |
| `scripts/deploy/make_secrets.sh` | `secrets/` 6개 파일 생성. 있는 파일은 건드리지 않는다 |
| `scripts/deploy/issue_cert.sh` | 첫 인증서 발급(http 부트스트랩 → certbot webroot → https 전환) |
| `scripts/deploy/deploy.sh` | ref 체크아웃 → 빌드 → check·migrate → `up -d` → 로그인 페이지 200 확인 |
| `.github/workflows/deploy.yml` | CD. `main`에 PR이 병합되면(push) 실행, 수동 실행은 되돌리기용. `BK_DEPLOY_ENABLED=true`일 때만 동작 |
| `.env.prod.example` | 호스트의 `.env` 예시(도메인·호스트·오리진). 비밀값 아님 |
| `.dockerignore` | 빌드 컨텍스트에서 `.git`·`secrets/`·`.env`·`tls/` 제외 |

## 왜 프록시 컨테이너가 TLS를 맡나 (D-070)

호스트에 nginx를 하나 더 두고 그 뒤에 컨테이너 프록시를 두면, 컨테이너 프록시는 `X-Forwarded-For`를
자기가 본 peer(호스트 nginx)로 **덮어쓰므로** 앱이 보는 클라이언트 주소가 전부 같아진다. 그러면 계정+IP별
로그인 실패 제한이 한 버킷으로 뭉쳐 10회 실패로 전 기기가 잠긴다([이슈 #61](https://github.com/rlagycks/bazaar_kiosk/issues/61)).
그래서 같은 프록시 컨테이너가 인증서를 들고 443을 직접 발행하며, `TRUSTED_PROXY_IPS=10.89.0.10`은 그대로다.
ALB/CloudFront를 앞에 두는 선택은 하지 않았다. 두려면 프록시의 `X-Forwarded-For` 처리와 신뢰 대역을 같이
바꿔야 하므로 D-070을 개정한다.

## 호스트 요구 사항 (AWS)

- EC2, Ubuntu 24.04 LTS. 크기는 실측 뒤 정한다(10E 로컬 수치로 EC2 용량을 단정하지 않는다, D-067).
  첫 후보는 t3.small 이상, 12A1 인수 때 같은 부하 도구로 측정한다.
- Elastic IP 하나, Route 53(또는 도메인 등록처)에 `BK_DOMAIN` A 레코드.
- 보안 그룹 인바운드: 80/tcp·443/tcp는 전체, 22/tcp는 운영자 주소만. 그 외 없음. DB·앱 포트는 호스트에
  발행되지 않으므로 열 것이 없다.
- IAM: 인스턴스 역할 불필요(외부 AWS 서비스를 쓰지 않는다). 백업(12A2)에서 S3를 쓰게 되면 그때 최소 권한으로.
- 디스크: 루트 20 GB 이상. Docker 로그는 컨테이너당 10 MB×5로 회전한다.

## 첫 배포 순서

```sh
# 0. (로컬) 배포 키 준비: 배포 전용 ssh 키 쌍을 만들고 공개키를 호스트 사용자에 등록
# 1. (호스트, sudo) 1회 준비
sudo bash scripts/deploy/server_setup.sh ubuntu
#    -> 로그아웃 후 재로그인(docker 그룹)
# 2. (호스트) 저장소
git clone https://github.com/rlagycks/bazaar_kiosk.git /srv/bazaar_kiosk && cd /srv/bazaar_kiosk
cp .env.prod.example .env && $EDITOR .env          # BK_DOMAIN 등
# 3. 비밀값 파일(대화형: 행사 공용 비밀번호 1회 입력 → 해시만 저장)
scripts/deploy/make_secrets.sh
# 4. DNS가 이 호스트를 가리키는지 확인한 뒤 인증서
scripts/deploy/issue_cert.sh ops@example.org --staging   # 리허설
sudo rm -rf /etc/letsencrypt/live/$BK_DOMAIN /etc/letsencrypt/archive/$BK_DOMAIN /etc/letsencrypt/renewal/$BK_DOMAIN.conf
scripts/deploy/issue_cert.sh ops@example.org             # 실제
# 5. 배포 (main이 배포 브랜치)
scripts/deploy/deploy.sh main
# 6. 관리자 계정(운영자 등록용, Django 관리자 화면)
docker compose -f compose.prod.yaml -f compose.tls.yaml exec app python manage.py createsuperuser
```

이후 운영자는 `https://BK_DOMAIN/admin/`의 "계정"에서 이름·권한을 등록하고, 각 기기는 이름 + 행사 공용
비밀번호로 로그인한다([ACCOUNTS](ACCOUNTS.md)).

## 이후 배포

- **브랜치 흐름:** 작업은 PR로 `develop`에 모이고, 릴리스는 `develop → main` PR이다. 그 PR을 병합하면
  `deploy.yml`이 병합 커밋을 배포한다. `main`에는 직접 push하지 않는다(브랜치 보호 권장: PR 필수, CI 통과 필수).
- 호스트에서: `scripts/deploy/deploy.sh <ref>`. 되돌리기는 이전 ref로 같은 명령(`deploy.log`에 이력).
  GitHub에서 되돌릴 때는 Actions → deploy → 이전 커밋 SHA를 ref로 수동 실행.
  호스트 체크아웃에서는 커밋하지 않는다(origin의 ref만 실행). origin에 없는 커밋이 있으면 스크립트가 거부한다.
  `.env`는 `BK_KEY=VALUE` 줄만 읽는다(셸로 실행하지 않음).
- GitHub 워크플로는 저장소 변수 `BK_DEPLOY_ENABLED=true`와 비밀 4개
  (`BK_DEPLOY_HOST`·`BK_DEPLOY_USER`·`BK_DEPLOY_SSH_KEY`·`BK_DEPLOY_KNOWN_HOSTS`)를 넣기 전까지는 아무 일도
  하지 않는다. `production` 환경에 필수 승인자를 두면 실행 전 승인 단계가 생긴다.
- **행사 시간 중 배포 금지(D-067).** 앱 교체는 열린 주방 스트림을 끊는다. 화면은 몇 초 안에 다시 붙지만
  부하 중에 그것을 믿지 않는다.
- migration은 새 이미지로, 이전 앱이 아직 서비스하는 동안 적용된다. 되돌릴 수 없는 migration(컬럼 삭제 등)이
  포함된 배포는 행사 밖에서 `down` → `migrate` → `up`으로 잠깐 세우고 한다. 자동 롤백은 코드만이며 DB는
  12A2의 백업으로 되돌린다.

## 인증서

- 발급·갱신 모두 호스트 certbot(webroot). `certbot.timer`가 갱신하고, `server_setup.sh`가 넣은
  `/etc/letsencrypt/renewal-hooks/deploy/bazaar-kiosk-reload.sh`가 프록시를 reload한다.
- 확인: `sudo certbot renew --dry-run`.
- HSTS는 `BK_HSTS_MAX_AGE=300`으로 시작한다. https가 안정된 뒤 `31536000`으로 올리고
  `render_nginx.sh` → `exec proxy nginx -s reload`. 잘못된 인증서 상태에서 큰 값을 켜면 되돌리기 어렵다.

## 보안 점검에서 12A1로 넘어온 항목의 처리

2026-09-23 운영 준비 점검(도구 없이 저장소·이력·설정·의존성·프록시 경계를 직접 확인, WORKLOG 참조).

| 항목 | 처리 |
| --- | --- |
| `check --deploy` W004(HSTS)·W008(HTTPS 리다이렉트) | 프록시에서 처리: 80→301 https, HSTS 헤더. Django 설정은 그대로(프록시가 종단) |
| 관리자 화면 `/admin/` 로그인에 실패 제한 없음 | 프록시 `limit_req`(주소당 20 r/m, burst 20). 로그인 페이지도 60 r/m·burst 60 |
| `server_tokens`, 요청 제한 | TLS 템플릿에 포함 |
| `.dockerignore` 없음 | 추가. 이미지에 들어간 적은 없으나 컨텍스트에서 `.git`·`secrets/`·`.env` 제외 |
| Docker 로그 무제한 | 오버레이에서 json-file 10 MB×5 |
| CSP | 인라인 `<script>` 정리가 선행이라 미적용([CONTENT_SECURITY](CONTENT_SECURITY.md)). 12B 후보 |
| readiness 엔드포인트·경보 | 미구현. `deploy.sh`는 로그인 페이지 200으로 확인. 12A1 인수 때 결정 |

## 이 단계가 하지 않은 것

- 실제 EC2·EIP·DNS·SG 생성과 첫 배포 실행(승인 뒤 위 순서대로)
- 백업·복원(12A2), 데이터 이전(12A3), 릴리스 감사(12B)
- 실기기·브라우저에서의 https 로그인·SSE 확인(V-BROWSER): 호스트가 생긴 뒤 12A1 인수 항목
