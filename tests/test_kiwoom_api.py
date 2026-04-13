from types import SimpleNamespace

import pytest

from kiwoom_api import (
    KiwoomApiError,
    KiwoomClient,
    KiwoomCredentials,
    RuntimeConfig,
    choose_account,
    normalize_stock_code,
    normalize_accounts,
    normalize_holdings,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {"content-type": "application/json"}
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def build_client(fake_session: object | None = None) -> KiwoomClient:
    creds = KiwoomCredentials("app", "secret", "https://api.kiwoom.com")
    return KiwoomClient(creds, session=fake_session or SimpleNamespace())


def test_choose_account_prefers_explicit_account() -> None:
    assert choose_account({"acctNo": ["1111111111"]}, "2222222222") == "2222222222"


def test_choose_account_uses_first_account_from_list() -> None:
    assert choose_account({"acctNo": ["1111111111", "3333333333"]}) == "1111111111"


def test_normalize_accounts_deduplicates() -> None:
    assert normalize_accounts({"acctNo": ["1111111111", "1111111111"]}) == ["1111111111"]


def test_normalize_stock_code_removes_leading_a() -> None:
    assert normalize_stock_code("A379800") == "379800"
    assert normalize_stock_code("379800") == "379800"


def test_normalize_holdings_finds_output1_list() -> None:
    holdings = normalize_holdings({"output1": [{"stk_cd": "005930"}], "output2": {}})
    assert holdings == [{"stk_cd": "005930"}]


def test_normalize_holdings_finds_kiwoom_balance_list() -> None:
    holdings = normalize_holdings({"stk_acnt_evlt_prst": [{"stk_cd": "379800"}]})
    assert holdings == [{"stk_cd": "379800"}]


def test_runtime_config_uses_fallback_universe_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KIWOOM_STATIC_UNIVERSE", raising=False)
    monkeypatch.delenv("KIWOOM_ACCOUNT_NO", raising=False)
    config = RuntimeConfig.from_env()
    assert config.static_universe == ["379800", "449180", "001500"]
    assert config.target_account_id == ""


def test_issue_token_posts_expected_payload() -> None:
    class FakeSession:
        def post(self, url, headers, json, timeout):
            assert url == "https://api.kiwoom.com/oauth2/token"
            assert json["grant_type"] == "client_credentials"
            assert json["appkey"] == "app"
            assert json["secretkey"] == "secret"
            assert "api-id" not in headers
            assert timeout == 15
            return FakeResponse(200, {"token": "abc", "expires_dt": "2099-01-01"})

    client = build_client(FakeSession())
    response = client.issue_token()

    assert response["token"] == "abc"


def test_fetch_holdings_posts_api_id_and_payload() -> None:
    class FakeSession:
        def post(self, url, headers, json, timeout):
            assert url == "https://api.kiwoom.com/api/dostk/acnt"
            assert headers["api-id"] == "kt00004"
            assert headers["authorization"] == "Bearer token"
            assert json["acct_no"] == "1111111111"
            assert json["dmst_stex_tp"] == "KRX"
            assert json["qry_tp"] == "1"
            return FakeResponse(200, {"stk_acnt_evlt_prst": [{"stk_cd": "005930"}]})

    client = build_client(FakeSession())
    _, body = client.fetch_holdings("token", "1111111111")

    assert body["stk_acnt_evlt_prst"][0]["stk_cd"] == "005930"


def test_fetch_open_orders_posts_expected_payload() -> None:
    class FakeSession:
        def post(self, url, headers, json, timeout):
            assert url == "https://api.kiwoom.com/api/dostk/acnt"
            assert headers["api-id"] == "ka10075"
            assert json["acct_no"] == "1111111111"
            assert json["stk_cd"] == "379800"
            assert json["stex_tp"] == "KRX"
            return FakeResponse(200, {"oso": []})

    client = build_client(FakeSession())
    _, body = client.fetch_open_orders("token", "1111111111", "A379800")
    assert body["oso"] == []


def test_place_buy_order_posts_expected_payload() -> None:
    class FakeSession:
        def post(self, url, headers, json, timeout):
            assert url == "https://api.kiwoom.com/api/dostk/ordr"
            assert headers["api-id"] == "kt10000"
            assert json["dmst_stex_tp"] == "KRX"
            assert json["acct_no"] == "1111111111"
            assert json["stk_cd"] == "379800"
            assert json["ord_qty"] == "2"
            assert json["ord_uv"] == "0"
            assert json["trde_tp"] == "03"
            return FakeResponse(200, {"rt_cd": "0", "ord_no": "123"})

    client = build_client(FakeSession())
    _, body = client.place_buy_order("token", "1111111111", "379800", 2)
    assert body["ord_no"] == "123"


def test_raises_api_error_on_non_200() -> None:
    class FakeSession:
        def post(self, url, headers, json, timeout):
            return FakeResponse(400, {"msg": "bad request"})

    client = build_client(FakeSession())

    with pytest.raises(KiwoomApiError):
        client.fetch_accounts("token")
