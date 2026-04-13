# kiwoom-autotrade

키움증권 REST API 기반 자동매매/수동거래 CLI 프로젝트입니다. 현재 레포는 인증, 계좌 조회, 보유종목 조회, 수동 매수/매도 CLI, `autotrade` 우선 유니버스 해석, 3종목 fallback까지 포함합니다.

## 1. 키움 포털에서 먼저 할 일

1. `https://openapi.kiwoom.com` 에서 `API 사용신청`을 진행합니다.
2. `계좌 App Key 관리` 또는 `모의투자 App Key 관리`에서 현재 사용 중인 공인 IP를 등록합니다.
3. 같은 화면에서 `계좌 등록하기`를 눌러 비밀번호/SMS 인증으로 연동 계좌를 등록합니다.
4. App Key / App Secret 을 다운로드합니다.

참고:
- 실전과 모의투자는 App Key / Secret 이 분리됩니다.
- 키움 공식 안내 기준으로 등록 IP 에서만 API 인증이 가능합니다.
- 접근 토큰 유효기간은 24시간입니다.

## 2. 가상환경과 의존성

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3. `.env` 설정

이 레포는 `.env`만 공식 설정 파일로 사용합니다.

최소 설정:

```dotenv
KIWOOM_ENV=prod
KIWOOM_APP_KEY=발급받은_app_key
KIWOOM_SECRET_KEY=발급받은_secret_key
KIWOOM_ACCOUNT_NO=1234567890
```

선택 설정:

```dotenv
# autotrade 직접 조회가 가능한 경우만 설정
KIWOOM_AUTOTRADE_GROUP=autotrade
KIWOOM_AUTOTRADE_API_ID=
KIWOOM_AUTOTRADE_API_PATH=
KIWOOM_AUTOTRADE_PAYLOAD={}

# 직접 조회 실패 시 fallback 유니버스
KIWOOM_STATIC_UNIVERSE=379800,449180,001500
KIWOOM_ALLOW_STATIC_FALLBACK=true
```

설명:
- `KIWOOM_ENV=prod` 는 실전 `https://api.kiwoom.com`
- `KIWOOM_ENV=mock` 는 모의 `https://mockapi.kiwoom.com`
- `KIWOOM_BASE_URL` 을 직접 넣으면 위 값보다 우선합니다.
- `KIWOOM_ACCOUNT_NO` 는 실운영에서 사실상 필수입니다.
- `KIWOOM_AUTOTRADE_API_ID`, `KIWOOM_AUTOTRADE_API_PATH` 가 설정되어 있으면 `autotrade` 직접 조회를 먼저 시도합니다.
- 직접 조회가 실패하거나 설정되지 않으면 `379800`, `449180`, `001500` fallback 이 사용됩니다.

## 4. CLI 명령

```powershell
python .\cli.py doctor
python .\cli.py accounts
python .\cli.py holdings
python .\cli.py quote 379800
python .\cli.py buy 379800 1 --dry-run
python .\cli.py sell 379800 1 --dry-run
python .\cli.py open-orders
python .\cli.py cancel 주문번호 379800 1
python .\cli.py dry-run
python .\cli.py run
```

호환 스크립트:

```powershell
python .\auth_check.py
python .\list_holdings.py
```

명령 설명:
- `doctor`: 인증, 계좌, 현재 유니버스 원천, 허용 종목 목록을 출력합니다.
- `accounts`: 현재 토큰으로 조회 가능한 계좌번호를 반환합니다.
- `holdings`: 대상 계좌의 보유종목을 조회하고 SQLite 상태를 갱신합니다.
- `buy` / `sell`: 자동매매와 동일한 종목 제한 검사를 거쳐 주문합니다.
- `dry-run`: 전략 연결 전 기본 점검 루프를 실제 주문 없이 실행합니다.
- `run`: 현재는 `dry-run`과 동일한 placeholder 동작입니다.

## 5. 실행 순서

처음 실행할 때 권장 순서:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python .\cli.py doctor
python .\cli.py accounts
python .\cli.py holdings
python .\cli.py buy 379800 1 --dry-run
```

실거래 예시:

```powershell
python .\cli.py quote 379800
python .\cli.py buy 379800 1
python .\cli.py sell 379800 1
python .\cli.py open-orders
```

## 6. 거래 유니버스 정책

- 1순위는 키움 `관심종목 autotrade` 직접 조회입니다.
- 직접 조회가 성공하면 해당 목록만 거래 허용 종목으로 사용합니다.
- 직접 조회가 안 되거나 불안정하면 fallback `379800`, `449180`, `001500`만 거래 허용합니다.
- 수동 주문과 자동 주문 모두 동일한 유니버스 검사를 통과해야 합니다.

## 7. 테스트

```powershell
pytest
```

## 8. 운영 파일

- `runtime.sqlite3`: 주문/포지션/유니버스 스냅샷 저장용 로컬 DB
- `auth_check.py`, `list_holdings.py`: 기존 진입점 호환 래퍼

## 9. 흔한 실패 원인

- `토큰 발급 실패`
  App Key / Secret 이 잘못됐거나 실전/모의 환경이 맞지 않을 수 있습니다.
- `계좌번호 조회 실패`
  포털에서 계좌 등록이 안 되었거나, IP 등록이 누락됐거나, 해당 토큰의 환경과 계좌 등록 환경이 다를 수 있습니다.
- `autotrade` 직접 조회 실패
  관련 API ID/URL/payload 가 아직 확인되지 않았거나 응답 형식이 예상과 다를 수 있습니다. 이 경우 fallback 유니버스로 자동 전환됩니다.
- 접속 자체가 안 됨
  사내망/VPN/NAT 환경 때문에 포털에 등록한 외부 IP 와 실제 요청 IP 가 다를 수 있습니다.
