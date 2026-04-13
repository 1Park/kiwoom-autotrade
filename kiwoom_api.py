import json
import os
from dataclasses import dataclass
from pathlib import Path

import requests


DEFAULT_TIMEOUT = 15
ACCOUNT_API_PATH = "/api/dostk/acnt"


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

    def _post(self, path: str, api_id: str | None = None, payload: dict | None = None) -> tuple[dict, dict]:
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        if api_id:
            headers["api-id"] = api_id

        response = self.session.post(
            f"{self.credentials.base_url}{path}",
            headers=headers,
            json=payload or {},
            timeout=self.timeout,
        )
        return self._parse_response(response)

    def _authed_post(self, path: str, token: str, api_id: str, payload: dict | None = None) -> tuple[dict, dict]:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "api-id": api_id,
        }
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

        return dict(response.headers), body

    def issue_token(self) -> dict:
        _, body = self._post(
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
        return self._authed_post(ACCOUNT_API_PATH, token, "ka00001")

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
        return self._authed_post(ACCOUNT_API_PATH, token, "kt00004", payload)


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
