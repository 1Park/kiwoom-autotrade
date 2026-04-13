from dataclasses import dataclass, field

from kiwoom_api import KiwoomApiError, KiwoomClient, RuntimeConfig, extract_stock_codes


@dataclass
class UniverseSnapshot:
    source: str
    codes: list[str]
    warnings: list[str] = field(default_factory=list)


class UniverseProvider:
    def get_codes(self, client: KiwoomClient, token: str) -> UniverseSnapshot:
        raise NotImplementedError


class StaticUniverseProvider(UniverseProvider):
    def __init__(self, codes: list[str]) -> None:
        self.codes = list(codes)

    def get_codes(self, client: KiwoomClient, token: str) -> UniverseSnapshot:
        return UniverseSnapshot(source="static_fallback", codes=list(self.codes))


class KiwoomAutotradeProvider(UniverseProvider):
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def get_codes(self, client: KiwoomClient, token: str) -> UniverseSnapshot:
        if not self.config.autotrade_api_id or not self.config.autotrade_api_path:
            raise KiwoomApiError(
                "Direct autotrade lookup is not configured. "
                "Set KIWOOM_AUTOTRADE_API_ID and KIWOOM_AUTOTRADE_API_PATH to enable it."
            )

        _, body = client.fetch_autotrade_group(
            token,
            api_id=self.config.autotrade_api_id,
            path=self.config.autotrade_api_path,
            group_name=self.config.autotrade_group_name,
            payload=self.config.autotrade_payload,
        )
        codes = extract_stock_codes(body)
        if not codes:
            raise KiwoomApiError(
                f"No stock codes were found for autotrade group response: {body}"
            )
        return UniverseSnapshot(source="autotrade", codes=codes)


def resolve_universe(client: KiwoomClient, token: str, config: RuntimeConfig) -> UniverseSnapshot:
    warnings: list[str] = []
    providers: list[UniverseProvider] = [KiwoomAutotradeProvider(config)]
    if config.allow_manual_fallback:
        providers.append(StaticUniverseProvider(config.static_universe))

    for provider in providers:
        try:
            snapshot = provider.get_codes(client, token)
            snapshot.warnings = warnings + snapshot.warnings
            return snapshot
        except Exception as exc:
            warnings.append(str(exc))

    raise KiwoomApiError("; ".join(warnings) or "Unable to resolve trading universe.")
