import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests


DEFAULT_TIMEOUT = 15
ACCOUNT_API_PATH = "/api/dostk/acnt"
STOCK_INFO_API_PATH = "/api/dostk/stkinfo"
ORDER_API_PATH = "/api/dostk/ordr"
DEFAULT_AUTOTRADE_FALLBACK = ("379800", "449180", "001500")


def load_env_file(env_path: Path | None = None) -> None:
    target = env_path or Path(".env")
    if not target.exists():
        return

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def resolve_base_url() -> str:
    explicit = os.getenv("KIWOOM_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    env_name = os.getenv("KIWOOM_ENV", "prod").strip().lower()
    if env_name == "mock":
        return "https://mockapi.kiwoom.com"
    return "https://api.kiwoom.com"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is empty.")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def parse_csv_codes(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalize_stock_code(stock_code: str) -> str:
    code = stock_code.strip().upper()
    if code.startswith("A") and len(code) == 7:
        return code[1:]
    return code


def parse_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class KiwoomApiError(RuntimeError):
    pass


@dataclass
class KiwoomCredentials:
    app_key: str
    secret_key: str
    base_url: str

    @classmethod
    def from_env(cls) -> "KiwoomCredentials":
        load_env_file()
        return cls(
            app_key=require_env("KIWOOM_APP_KEY"),
            secret_key=require_env("KIWOOM_SECRET_KEY"),
            base_url=resolve_base_url(),
        )


@dataclass
class RuntimeConfig:
    target_account_id: str = ""
    static_universe: list[str] = field(
        default_factory=lambda: list(DEFAULT_AUTOTRADE_FALLBACK)
    )
    autotrade_group_name: str = "autotrade"
    autotrade_api_id: str = ""
    autotrade_api_path: str = ""
    autotrade_payload: dict[str, Any] = field(default_factory=dict)
    allow_manual_fallback: bool = True

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        load_env_file()
        payload_raw = optional_env("KIWOOM_AUTOTRADE_PAYLOAD", "")
        payload = json.loads(payload_raw) if payload_raw else {}
        return cls(
            target_account_id=optional_env("KIWOOM_ACCOUNT_NO", ""),
            static_universe=parse_csv_codes(optional_env("KIWOOM_STATIC_UNIVERSE", ""))
            or list(DEFAULT_AUTOTRADE_FALLBACK),
            autotrade_group_name=optional_env("KIWOOM_AUTOTRADE_GROUP", "autotrade")
            or "autotrade",
            autotrade_api_id=optional_env("KIWOOM_AUTOTRADE_API_ID", ""),
            autotrade_api_path=optional_env("KIWOOM_AUTOTRADE_API_PATH", ""),
            autotrade_payload=payload if isinstance(payload, dict) else {},
            allow_manual_fallback=parse_bool(
                os.getenv("KIWOOM_ALLOW_STATIC_FALLBACK"), default=True
            ),
        )


class KiwoomClient:
    def __init__(
        self,
        credentials: KiwoomCredentials,
        session: requests.Session | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.credentials = credentials
        self.session = session or requests.Session()
        self.timeout = timeout

    def _request(
        self,
        path: str,
        *,
        token: str | None = None,
        api_id: str | None = None,
        payload: dict | None = None,
    ) -> tuple[dict, dict]:
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        if api_id:
            headers["api-id"] = api_id

        response = self.session.post(
            f"{self.credentials.base_url}{path}",
            headers=headers,
            json=payload or {},
            timeout=self.timeout,
        )
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: requests.Response) -> tuple[dict, dict]:
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"raw": response.text}

        if response.status_code != 200:
            raise KiwoomApiError(f"HTTP {response.status_code}: {body}")

        if isinstance(body, dict):
            rt_cd = body.get("rt_cd") or body.get("return_code")
            msg = body.get("msg1") or body.get("msg") or body.get("return_msg")
            if rt_cd not in (None, "0", 0):
                raise KiwoomApiError(f"API {rt_cd}: {msg or body}")
            return dict(response.headers), body

        raise KiwoomApiError(f"Unexpected response body: {body}")

    def issue_token(self) -> dict:
        _, body = self._request(
            "/oauth2/token",
            payload={
                "grant_type": "client_credentials",
                "appkey": self.credentials.app_key,
                "secretkey": self.credentials.secret_key,
            },
        )
        token = body.get("token")
        if not token:
            raise KiwoomApiError(f"Token not found in response: {body}")
        return body

    def fetch_accounts(self, token: str) -> tuple[dict, dict]:
        return self._request(ACCOUNT_API_PATH, token=token, api_id="ka00001")

    def fetch_holdings(
        self,
        token: str,
        account_no: str,
        *,
        exchange_type: str = "KRX",
        query_type: str = "1",
    ) -> tuple[dict, dict]:
        payload = {
            "acct_no": account_no,
            "dmst_stex_tp": exchange_type,
            "qry_tp": query_type,
        }
        return self._request(
            ACCOUNT_API_PATH, token=token, api_id="kt00004", payload=payload
        )

    def fetch_quote(self, token: str, stock_code: str) -> tuple[dict, dict]:
        return self._request(
            STOCK_INFO_API_PATH,
            token=token,
            api_id="ka10001",
            payload={"stk_cd": normalize_stock_code(stock_code)},
        )

    def fetch_open_orders(
        self, token: str, account_no: str, stock_code: str = ""
    ) -> tuple[dict, dict]:
        payload = {
            "acct_no": account_no,
            "stk_cd": normalize_stock_code(stock_code),
            "all_stk_tp": "0",
            "trde_tp": "0",
            "stex_tp": "KRX",
        }
        return self._request(
            ACCOUNT_API_PATH, token=token, api_id="ka10075", payload=payload
        )

    def place_buy_order(
        self,
        token: str,
        account_no: str,
        stock_code: str,
        quantity: int,
        *,
        price: int = 0,
        order_type: str = "03",
    ) -> tuple[dict, dict]:
        payload = {
            "acct_no": account_no,
            "dmst_stex_tp": "KRX",
            "stk_cd": normalize_stock_code(stock_code),
            "ord_qty": str(quantity),
            "ord_uv": str(price),
            "trde_tp": order_type,
        }
        return self._request(
            ORDER_API_PATH, token=token, api_id="kt10000", payload=payload
        )

    def place_sell_order(
        self,
        token: str,
        account_no: str,
        stock_code: str,
        quantity: int,
        *,
        price: int = 0,
        order_type: str = "03",
    ) -> tuple[dict, dict]:
        payload = {
            "acct_no": account_no,
            "dmst_stex_tp": "KRX",
            "stk_cd": normalize_stock_code(stock_code),
            "ord_qty": str(quantity),
            "ord_uv": str(price),
            "trde_tp": order_type,
        }
        return self._request(
            ORDER_API_PATH, token=token, api_id="kt10001", payload=payload
        )

    def cancel_order(
        self,
        token: str,
        account_no: str,
        order_no: str,
        stock_code: str,
        quantity: int,
    ) -> tuple[dict, dict]:
        payload = {
            "acct_no": account_no,
            "ord_no": order_no,
            "stk_cd": normalize_stock_code(stock_code),
            "cncl_qty": str(quantity),
        }
        return self._request(
            ORDER_API_PATH, token=token, api_id="kt10003", payload=payload
        )

    def fetch_autotrade_group(
        self,
        token: str,
        *,
        api_id: str,
        path: str,
        group_name: str = "autotrade",
        payload: dict | None = None,
    ) -> tuple[dict, dict]:
        request_payload = {"group_name": group_name}
        if payload:
            request_payload.update(payload)
        return self._request(path, token=token, api_id=api_id, payload=request_payload)


def choose_account(accounts_body: dict, explicit_account: str | None = None) -> str:
    if explicit_account:
        return explicit_account

    candidates: list[str] = []

    for key in ("acctNo", "acct_no", "account_no"):
        value = accounts_body.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
        elif isinstance(value, list):
            candidates.extend(
                item.strip() for item in value if isinstance(item, str) and item.strip()
            )

    if not candidates:
        raise KiwoomApiError(f"Unable to find account number in response: {accounts_body}")

    return candidates[0]


def normalize_holdings(body: dict) -> list[dict]:
    candidate_lists = [
        body.get("stk_acnt_evlt_prst"),
        body.get("items"),
        body.get("list"),
        body.get("stocks"),
        body.get("holdings"),
        body.get("output"),
        body.get("output1"),
    ]

    for candidate in candidate_lists:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]

    for value in body.values():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return value

    return []


def normalize_accounts(body: dict) -> list[str]:
    accounts = []
    for key in ("acctNo", "acct_no", "account_no"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            accounts.append(value.strip())
        elif isinstance(value, list):
            accounts.extend(item.strip() for item in value if isinstance(item, str) and item.strip())
    seen = set()
    unique = []
    for account in accounts:
        if account not in seen:
            seen.add(account)
            unique.append(account)
    return unique


def extract_stock_codes(body: dict) -> list[str]:
    codes: list[str] = []
    for item in normalize_holdings(body):
        for key in ("stk_cd", "stock_code", "code"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                codes.append(normalize_stock_code(value))
                break

    if not codes:
        for key in ("stk_cd", "stock_code", "codes"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                codes.extend(normalize_stock_code(item) for item in parse_csv_codes(value))
            elif isinstance(value, list):
                codes.extend(
                    normalize_stock_code(item)
                    for item in value
                    if isinstance(item, str) and item.strip()
                )

    seen = set()
    unique = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            unique.append(code)
    return unique
