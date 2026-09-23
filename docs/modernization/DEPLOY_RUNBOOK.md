# 12A1 — 배포 런북(준비 단계)

상태: **첫 배포 완료(2026-09-23, `https://moau.store`)** — EC2 t4g.small·Amazon Linux 2023·EIP `43.201.151.63`,
브랜치 `phase-12a1-deploy-prep`(`d665f4e`)를 운영자 PC에서 ssh로 배포. 이후 배포는 CD(GitHub OIDC + IAM 역할 +
SSM, D-072)로 한다 — AWS 설정과 `BK_DEPLOY_ENABLED` 전까지는 꺼져 있다. 대상 형태는 AWS EC2 한 대,
도메인, HTTPS, nginx. 구성의 근거는 [배포 후보(4A3)](DEPLOYMENT_CANDIDATE.md)와 D-046·D-070·D-071이다.

## 구성 요약

| 파일 | 역할 |
| --- | --- |
| `compose.prod.yaml` | 후보 스택(4A3). 그대로 쓴다 |
| `compose.tls.yaml` | 12A1 오버레이. 프록시가 80/443을 발행하고 인증서·ACME 웹루트를 마운트한다. 로그 회전 |
| `scripts/nginx_tls/*.template` | 프록시 설정 템플릿. `render_nginx.sh`가 도메인을 넣어 `tls/conf.d/`로 렌더링(미커밋) |
| `scripts/deploy/server_setup.sh` | 호스트 1회 준비(Amazon Linux 2023: docker·buildx·compose 플러그인(체크섬 고정), certbot·갱신 타이머, envsubst, 웹루트, 갱신 훅) |
| `scripts/deploy/init_github_secrets.sh` | (운영자 PC) 앱 비밀값 5개를 만들어 GitHub `production` 환경에 바로 등록. 배포 키 쌍 생성 선택. 있는 값은 건드리지 않는다 |
| `scripts/deploy/install_config.sh` | (호스트) 표준입력으로 받은 값을 검증해 `.env`·`secrets/`에 쓴다. DB 비밀번호 불일치는 거부 |
| `scripts/deploy/ssm_deploy.sh` | (호스트, CD가 SSM으로 실행) Parameter Store의 설정 묶음을 읽고 삭제 → `install_config.sh` → `deploy.sh` |
| `scripts/deploy/issue_cert.sh` | 첫 인증서 발급(http 부트스트랩 → certbot webroot → https 전환) |
| `scripts/deploy/deploy.sh` | ref 체크아웃 → 디스크 확인 → 빌드 → check·migrate → 프록시 설정 렌더링 → `up -d`·reload → 로그인 페이지 200 확인 → 안 쓰는 이미지·빌드 캐시 정리 |
| `.github/workflows/deploy.yml` | CD(OIDC + SSM). `main`에 PR이 병합되면(push) 실행, 수동 실행은 되돌리기·`config_only`용. 매 실행마다 설정·비밀값을 먼저 쓴다. `BK_DEPLOY_ENABLED=true`일 때만 동작 |
| `.env.prod.example` | 호스트 `.env`의 키 설명. 실제 파일은 워크플로가 GitHub 변수로 만든다. 비밀값 아님 |
| `.dockerignore` | 빌드 컨텍스트에서 `.git`·`secrets/`·`.env`·`tls/` 제외 |

## 왜 프록시 컨테이너가 TLS를 맡나 (D-070)

호스트에 nginx를 하나 더 두고 그 뒤에 컨테이너 프록시를 두면, 컨테이너 프록시는 `X-Forwarded-For`를
자기가 본 peer(호스트 nginx)로 **덮어쓰므로** 앱이 보는 클라이언트 주소가 전부 같아진다. 그러면 계정+IP별
로그인 실패 제한이 한 버킷으로 뭉쳐 10회 실패로 전 기기가 잠긴다([이슈 #61](https://github.com/rlagycks/bazaar_kiosk/issues/61)).
그래서 같은 프록시 컨테이너가 인증서를 들고 443을 직접 발행하며, `TRUSTED_PROXY_IPS=10.89.0.10`은 그대로다.
ALB/CloudFront를 앞에 두는 선택은 하지 않았다. 두려면 프록시의 `X-Forwarded-For` 처리와 신뢰 대역을 같이
바꿔야 하므로 D-070을 개정한다.

## 호스트 요구 사항 (AWS)

- EC2, **Amazon Linux 2023**(aarch64), 사용자 `ec2-user`. 현재 t4g.small(2 vCPU, 2 GB). 크기의 합격은 실측 뒤
  정한다(10E 로컬 수치로 EC2 용량을 단정하지 않는다, D-067). 12A1 인수 때 같은 부하 도구로 측정한다.
- Elastic IP 하나, Route 53(또는 도메인 등록처)에 `BK_DOMAIN` A 레코드.
- 보안 그룹 인바운드: 80/tcp·443/tcp는 전체. 22/tcp는 **운영자 주소만(2026-09-23 사용자 결정)**. 참고로 선택지는: GitHub 러너는 주소가 고정되지 않아서
  운영자 주소로만 열면 CD가 접속하지 못한다. (a) 전체에 열고 키 인증만(단순, 행사용 단기 호스트에 현실적)
  (b) 운영자 주소만 열고 CD 대신 호스트에서 수동 배포 (c) SSM 등으로 전환(워크플로·IAM 변경). 그 외 포트 없음.
  DB·앱 포트는 호스트에 발행되지 않으므로 열 것이 없다.
- IAM: 인스턴스 역할 `bazaar-kiosk-ec2`(SSM 관리 + 배포 파라미터 읽기·삭제만), GitHub 배포 역할
  `bazaar-kiosk-github-deploy`(아래 CD 경로). 백업(12A2)에서 S3를 쓰게 되면 그때 최소 권한으로.
- 디스크: 루트 **8 GB 유지**(D-071 B안). 첫 배포 뒤 예상 사용량은 3.5–4 GB(OS 1.7 GB, 이미지·빌드 캐시).
  `deploy.sh`가 빌드 전에 여유 2.5 GB(`BK_MIN_FREE_MB`)를 요구하고, 모자라면 안 쓰는 이미지와 빌드 캐시를 모두
  지운 뒤에도 모자랄 때 배포를 거부한다. 성공한 배포 뒤에는 dangling 이미지와 빌드 캐시를 정리한다(되돌리기는
  다시 빌드). 디스크가 차면 PostgreSQL 쓰기가 멈추므로(주문 저장 실패) 이 검사가 그 방어선이다. Docker 로그는
  컨테이너당 10 MB×5로 회전한다.

## CD 경로 (D-072: GitHub OIDC + IAM 역할 + SSM)

```
merge → main ─▶ GitHub Actions (environment: production)
                 │ 1. OIDC 토큰으로 IAM 역할 bazaar-kiosk-github-deploy 획득 (장기 키 없음)
                 │ 2. 설정 묶음을 SSM Parameter Store SecureString으로 올림
                 │    /bazaar-kiosk/production/deploy-payload
                 │ 3. SSM Run Command → 호스트에서 ssm_deploy.sh (ec2-user)
                 ▼
               EC2 (인스턴스 역할 bazaar-kiosk-ec2)
                   4. 파라미터를 읽고 즉시 삭제 → install_config.sh → deploy.sh
                 ▲ 5. 워크플로가 결과를 기다려 로그를 보여 주고, 끝나면 파라미터를 한 번 더 삭제
```

22번 포트는 운영자 주소만 열어 둔다(러너가 ssh하지 않는다). SSM 명령 기록에는 ref·커밋·모드만 남고 값은 없다.
설정·비밀값의 원본은 GitHub `production` 환경이다(D-071). `install_config.sh`가 검증해서 `.env`(0600)·
`secrets/`(0700, 파일 0444)에 쓴다. 파일이 0444인 이유: 컨테이너 사용자(app uid 10001, postgres uid 70)가 바인드
마운트된 파일을 읽어야 하고, 호스트의 다른 사용자는 0700 디렉터리가 막는다.

### AWS 설정 (1회, 콘솔)

아래 `<ACCOUNT_ID>`·`<INSTANCE_ID>`는 실제 값으로 바꾼다(공개 저장소라 문서에는 적지 않는다). 리전 `ap-northeast-2`.

1. **OIDC 공급자**: IAM → 자격 증명 공급자 → 추가 → OpenID Connect, URL `https://token.actions.githubusercontent.com`,
   대상 `sts.amazonaws.com`. (계정에 이미 있으면 재사용)
2. **인스턴스 역할 `bazaar-kiosk-ec2`**: 신뢰 대상 EC2, 관리형 정책 `AmazonSSMManagedInstanceCore` + 인라인 정책:
   ```json
   {"Version": "2012-10-17", "Statement": [{
     "Effect": "Allow",
     "Action": ["ssm:GetParameter", "ssm:DeleteParameter"],
     "Resource": "arn:aws:ssm:ap-northeast-2:<ACCOUNT_ID>:parameter/bazaar-kiosk/production/deploy-payload"
   }]}
   ```
   EC2 → 인스턴스 → 작업 → 보안 → IAM 역할 수정 → 이 역할 연결. 몇 분 뒤 Systems Manager → Fleet Manager에
   인스턴스가 "온라인"으로 보이면 된다(에이전트는 AL2023 기본 설치·실행 중).
3. **배포 역할 `bazaar-kiosk-github-deploy`**: 신뢰 정책(웹 자격 증명, 위 공급자):
   ```json
   {"Version": "2012-10-17", "Statement": [{
     "Effect": "Allow",
     "Principal": {"Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"},
     "Action": "sts:AssumeRoleWithWebIdentity",
     "Condition": {"StringEquals": {
       "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
       "token.actions.githubusercontent.com:sub": "repo:rlagycks/bazaar_kiosk:environment:production"
     }}
   }]}
   ```
   권한(인라인):
   ```json
   {"Version": "2012-10-17", "Statement": [
     {"Effect": "Allow", "Action": "ssm:SendCommand", "Resource": [
       "arn:aws:ec2:ap-northeast-2:<ACCOUNT_ID>:instance/<INSTANCE_ID>",
       "arn:aws:ssm:ap-northeast-2::document/AWS-RunShellScript"]},
     {"Effect": "Allow", "Action": ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"], "Resource": "*"},
     {"Effect": "Allow", "Action": ["ssm:PutParameter", "ssm:DeleteParameter"],
      "Resource": "arn:aws:ssm:ap-northeast-2:<ACCOUNT_ID>:parameter/bazaar-kiosk/production/deploy-payload"}
   ]}
   ```
   SecureString은 AWS 관리형 키 `aws/ssm`을 쓰므로 KMS 권한을 따로 주지 않는다.

신뢰 조건의 `sub`가 **`production` 환경**이라서, 그 환경에서 도는 job만 역할을 얻는다. 그래서 환경의 배포 브랜치를
`main`으로 제한하는 것이 이 경계의 일부다(아래 표).

### GitHub에 넣는 값

| 종류 | 이름 | 값 |
| --- | --- | --- |
| 저장소 변수 | `BK_DEPLOY_ENABLED` | `true`면 동작. job 수준 `if`는 환경 변수를 못 보므로 **저장소 변수**여야 한다 |
| 환경 변수 | `BK_AWS_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/bazaar-kiosk-github-deploy` |
| 환경 변수 | `BK_EC2_INSTANCE_ID` | `<INSTANCE_ID>` |
| 환경 변수 | `BK_AWS_REGION` | 선택, 기본 `ap-northeast-2` |
| 환경 변수 | `BK_DOMAIN` | 공개 도메인(필수) |
| 환경 변수 | `BK_ALLOWED_HOSTS`, `BK_CSRF_TRUSTED_ORIGINS`, `BK_HSTS_MAX_AGE`, `BK_DEPLOY_DIR` | 선택. 기본값은 `BK_DOMAIN`, `https://BK_DOMAIN`, `300`, `/srv/bazaar_kiosk` |
| 환경 비밀 | `BK_SECRET_KEY`, `BK_JWT_SIGNING_KEY` | `init_github_secrets.sh`가 생성 |
| 환경 비밀 | `BK_POSTGRES_BOOTSTRAP_PASSWORD`, `BK_POSTGRES_APP_PASSWORD` | 같은 스크립트가 생성. **한 번 정하면 그대로**(아래 교체 절차) |
| 환경 비밀 | `BK_EVENT_PASSWORD_HASH` | 행사 공용 비밀번호의 PBKDF2 해시(D-051). 평문은 어디에도 저장하지 않는다 |
| 환경 설정 | 배포 브랜치 | `main`만. 필수 승인자는 선택(두면 배포마다 승인 클릭) |

`database_url`은 호스트에서 앱 DB 비밀번호로 조립하므로 따로 두지 않는다. 저장소는 public이지만 fork PR에는
비밀값·OIDC 역할이 전달되지 않는다. GitHub 비밀값은 다시 읽을 수 없다: 호스트 복원의 원본은 되지만 사람이
값을 확인하는 백업은 아니다.

### 운영자 PC에서 직접 배포 (CD를 못 쓸 때)

운영자 주소에서 관리 키로 ssh → `cd /srv/bazaar_kiosk && bash scripts/deploy/deploy.sh <ref>`. 이 경로는 호스트에
이미 있는 `.env`·`secrets/`를 쓴다. 비밀값을 바꾼 뒤라면 CD의 `config_only` 실행을 먼저 한다.

## 새 호스트에서 처음부터 (첫 배포 순서)

2026-09-23의 실제 첫 배포는 CD가 생기기 전이라 5번을 운영자 PC에서 ssh로 대신했다(WORKLOG). 새 호스트라면:

```sh
# 0. (AWS) 위 "AWS 설정" 1–3, 인스턴스 역할 연결. DNS A 레코드 BK_DOMAIN -> EIP. SG: 80/443 전체, 22 운영자 주소
# 1. (GitHub) production 환경: 배포 브랜치 main, 환경 변수 BK_DOMAIN·BK_AWS_ROLE_ARN·BK_EC2_INSTANCE_ID,
#    저장소 변수 BK_DEPLOY_ENABLED=true
# 2. (운영자 PC) 비밀값 생성·등록. 행사 공용 비밀번호를 한 번 입력한다(해시만 등록)
scripts/deploy/init_github_secrets.sh
# 3. (호스트, 관리 키로 ssh) 1회 준비
sudo bash scripts/deploy/server_setup.sh ec2-user     # 저장소가 아직 없으면 이 파일만 먼저 복사해 실행
#    -> 로그아웃 후 재로그인(docker 그룹)
git clone https://github.com/rlagycks/bazaar_kiosk.git /srv/bazaar_kiosk
# 4. (GitHub) Actions > deploy 수동 실행: ref=main, config_only 체크 -> 호스트에 .env·secrets/가 생긴다
# 5. (호스트) 인증서. DNS가 이 호스트를 가리키는지 먼저 확인
scripts/deploy/issue_cert.sh <연락 이메일> --staging   # 리허설
sudo certbot delete --cert-name <BK_DOMAIN> --non-interactive
scripts/deploy/issue_cert.sh <연락 이메일>             # 실제
# 6. (GitHub) Actions > deploy 수동 실행: ref=main (또는 develop -> main PR 병합)
# 7. 관리자 계정 -> /admin/ 에서 행사일·계정·메뉴·테이블 등록
docker compose -f compose.prod.yaml -f compose.tls.yaml exec app python manage.py createsuperuser
```

## 이후 배포

- **브랜치 흐름:** 작업은 PR로 `develop`에 모이고, 릴리스는 `develop → main` PR이다. 그 PR을 병합하면
  `deploy.yml`이 병합 커밋을 배포한다. `main`에는 직접 push하지 않는다(브랜치 보호 권장: PR 필수, CI 통과 필수).
- 호스트에서: `scripts/deploy/deploy.sh <ref>`. 되돌리기는 이전 ref로 같은 명령(`deploy.log`에 이력).
  GitHub에서 되돌릴 때는 Actions → deploy → 이전 커밋 SHA를 ref로 수동 실행.
  호스트 체크아웃에서는 커밋하지 않는다(origin의 ref만 실행). origin에 없는 커밋이 있으면 스크립트가 거부한다.
  `.env`는 `BK_KEY=VALUE` 줄만 읽는다(셸로 실행하지 않음).
- GitHub 워크플로는 저장소 변수 `BK_DEPLOY_ENABLED=true` 전까지 아무 일도 하지 않는다. 켜진 뒤에는 매 실행이
  설정·비밀값을 먼저 쓰고(`install_config.sh`, 바뀐 파일만 교체) 배포한다. 값이 하나라도 비었거나 형식이
  틀리면 아무것도 쓰지 않고 실패한다. 쓰는 도중 실패하면(디스크 부족 등) 어떤 파일까지 바뀌었는지 출력하며,
  원인을 해결하고 다시 실행하면 같은 상태로 수렴한다. `production` 환경에 필수 승인자를 두면 실행 전 승인 단계가 생긴다.
- 도메인·HSTS 변경은 GitHub 변수를 바꾸고 배포하면 반영된다(`deploy.sh`가 프록시 설정을 다시 렌더링하고 reload).
- 호스트에서 직접 `deploy.sh`를 돌릴 때는 호스트에 이미 있는 `.env`·`secrets/`를 쓴다.
- CD 실패 시: Actions 로그에 SSM 명령 ID와 호스트 출력 마지막 80줄이 나온다. 전체는 Systems Manager → Run Command
  → 명령 기록. 호스트에서 `deploy.log`.
- **행사 시간 중 배포 금지(D-067).** 앱 교체는 열린 주방 스트림을 끊는다. 화면은 몇 초 안에 다시 붙지만
  부하 중에 그것을 믿지 않는다.
- migration은 새 이미지로, 이전 앱이 아직 서비스하는 동안 적용된다. 되돌릴 수 없는 migration(컬럼 삭제 등)이
  포함된 배포는 행사 밖에서 `down` → `migrate` → `up`으로 잠깐 세우고 한다. 자동 롤백은 코드만이며 DB는
  12A2의 백업으로 되돌린다.

## 비밀값 교체

- `BK_SECRET_KEY`·`BK_JWT_SIGNING_KEY`: GitHub에서 값을 바꾸고(또는 지우고 `init_github_secrets.sh`) 배포.
  모든 기기의 로그인이 풀린다. 행사 밖에서.
- `BK_EVENT_PASSWORD_HASH`: 지우고 `init_github_secrets.sh`로 새 비밀번호의 해시를 등록한 뒤 배포.
- DB 비밀번호 2개: PostgreSQL은 데이터 볼륨을 처음 만들 때만 비밀번호를 적용한다. 그래서 `install_config.sh`는
  GitHub 값이 호스트의 `secrets/` 값과 다르면 **아무것도 쓰지 않고 실패한다**(볼륨 유무와 무관. 볼륨을 지우고 새로
  시작할 때도 해당 파일을 먼저 지운다). 교체 순서:
  1. 호스트에서 DB 역할의 비밀번호를 먼저 바꾼다(앱 역할 예:
     `docker compose -f compose.prod.yaml -f compose.tls.yaml exec -T postgres psql -U bazaar_bootstrap -d bazaar -c "ALTER ROLE bazaar_app PASSWORD '<새 값>'"`,
     값이 셸 기록에 남지 않게 입력한다).
  2. 호스트의 `secrets/postgres_app_password`를 지운다(가드가 비교할 옛 값을 없앰). 부트스트랩 비밀번호도 같은 방식.
  3. GitHub 값을 같은 새 값으로 바꾸고 배포한다(`database_url`도 새로 조립되고 앱이 재시작된다).
- 배포 자격 증명: 장기 키가 없다(OIDC). 역할을 막으려면 IAM에서 배포 역할의 신뢰 정책이나 권한을 지운다.

## 인증서

- 발급·갱신 모두 호스트 certbot(webroot). `certbot-renew.timer`(AL2023, `server_setup.sh`가 켠다)가 갱신하고, `server_setup.sh`가 넣은
  `/etc/letsencrypt/renewal-hooks/deploy/bazaar-kiosk-reload.sh`가 프록시를 reload한다.
- 확인: `sudo certbot renew --dry-run`.
- HSTS는 `BK_HSTS_MAX_AGE=300`으로 시작한다. https가 안정된 뒤 `31536000`으로 올리고
  배포(GitHub 변수 `BK_HSTS_MAX_AGE`). 잘못된 인증서 상태에서 큰 값을 켜면 되돌리기 어렵다.
- `live/`·`archive/`는 root 전용(0700)이라 스크립트는 `/etc/letsencrypt/renewal/<도메인>.conf`로 인증서 유무를 판단한다.

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

- DNS·SG 22번 정책·GitHub 환경/비밀값 등록·서버 세팅·첫 배포 실행(승인 뒤 위 순서대로)
- 백업·복원(12A2), 데이터 이전(12A3), 릴리스 감사(12B)
- 실기기·브라우저에서의 https 로그인·SSE 확인(V-BROWSER): 호스트가 생긴 뒤 12A1 인수 항목
