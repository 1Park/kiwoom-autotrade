import json

import cli


class StubClient:
    def __init__(self) -> None:
        self.credentials = type("Creds", (), {"base_url": "https://api.kiwoom.com"})()

    def issue_token(self) -> dict:
        return {"token": "token", "expires_dt": "2099-01-01"}

    def fetch_accounts(self, token: str):
        return {}, {"acctNo": ["1111111111"]}

    def fetch_holdings(self, token: str, account_no: str):
        return {}, {"stk_acnt_evlt_prst": [{"stk_cd": "379800", "stk_nm": "ETF", "rmnd_qty": "1"}]}

    def fetch_quote(self, token: str, stock_code: str):
        assert stock_code == "379800"
        return {}, {"stk_cd": stock_code, "cur_prc": "10000"}

    def place_buy_order(self, token: str, account_no: str, stock_code: str, quantity: int, *, price: int = 0, order_type: str = "03"):
        assert stock_code == "379800"
        return {}, {"ord_no": "123"}

    def place_sell_order(self, token: str, account_no: str, stock_code: str, quantity: int, *, price: int = 0, order_type: str = "03"):
        assert stock_code == "379800"
        return {}, {"ord_no": "456"}

    def fetch_open_orders(self, token: str, account_no: str, stock_code: str = ""):
        return {}, {"items": []}

    def cancel_order(self, token: str, account_no: str, order_no: str, stock_code: str, quantity: int):
        return {}, {"result": "ok"}


def test_doctor_reports_static_universe(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(cli, "build_client", lambda: (StubClient(), cli.RuntimeConfig(static_universe=["379800", "449180", "001500"])))
    monkeypatch.setattr(cli, "resolve_universe", lambda client, token, config: cli.UniverseSnapshot(source="static_fallback", codes=["379800", "449180", "001500"], warnings=["autotrade unavailable"]))
    monkeypatch.setattr(cli, "DB_PATH", tmp_path / "runtime.sqlite3")

    rc = cli.main(["doctor"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["universe_source"] == "static_fallback"
    assert output["allowed_stock_codes"] == ["379800", "449180", "001500"]


def test_buy_dry_run_rejects_outside_universe(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "build_client", lambda: (StubClient(), cli.RuntimeConfig(target_account_id="1111111111", static_universe=["379800", "449180", "001500"])))
    monkeypatch.setattr(cli, "resolve_universe", lambda client, token, config: cli.UniverseSnapshot(source="static_fallback", codes=["379800", "449180", "001500"], warnings=[]))
    monkeypatch.setattr(cli, "DB_PATH", tmp_path / "runtime.sqlite3")

    rc = cli.main(["buy", "005930", "1", "--dry-run"])
    assert rc == 2


def test_holdings_command_uses_target_account(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "build_client", lambda: (StubClient(), cli.RuntimeConfig(target_account_id="1111111111")))

    rc = cli.main(["holdings"])
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["account_no"] == "1111111111"
    assert output["holdings"][0]["stock_code"] == "379800"
