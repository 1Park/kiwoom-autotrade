import pytest

from kiwoom_api import KiwoomApiError, RuntimeConfig
from universe import resolve_universe


class AutotradeClient:
    def fetch_autotrade_group(self, token, *, api_id, path, group_name, payload):
        assert token == "token"
        assert api_id == "ka99999"
        assert path == "/api/dostk/watchlist"
        assert group_name == "autotrade"
        return {}, {"items": [{"stk_cd": "379800"}, {"stk_cd": "449180"}]}


class FailingAutotradeClient:
    def fetch_autotrade_group(self, token, *, api_id, path, group_name, payload):
        raise KiwoomApiError("autotrade unavailable")


def test_resolve_universe_prefers_autotrade() -> None:
    config = RuntimeConfig(
        static_universe=["001500"],
        autotrade_api_id="ka99999",
        autotrade_api_path="/api/dostk/watchlist",
    )
    snapshot = resolve_universe(AutotradeClient(), "token", config)
    assert snapshot.source == "autotrade"
    assert snapshot.codes == ["379800", "449180"]


def test_resolve_universe_falls_back_to_static_when_autotrade_fails() -> None:
    config = RuntimeConfig(
        static_universe=["379800", "449180", "001500"],
        autotrade_api_id="ka99999",
        autotrade_api_path="/api/dostk/watchlist",
    )
    snapshot = resolve_universe(FailingAutotradeClient(), "token", config)
    assert snapshot.source == "static_fallback"
    assert snapshot.codes == ["379800", "449180", "001500"]
    assert "autotrade unavailable" in snapshot.warnings[0]


def test_resolve_universe_raises_when_every_source_fails() -> None:
    config = RuntimeConfig(
        static_universe=[],
        autotrade_api_id="ka99999",
        autotrade_api_path="/api/dostk/watchlist",
        allow_manual_fallback=False,
    )
    with pytest.raises(KiwoomApiError):
        resolve_universe(FailingAutotradeClient(), "token", config)
