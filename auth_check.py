import json
import sys

from kiwoom_api import KiwoomClient, KiwoomCredentials


def main() -> int:
    try:
        client = KiwoomClient(KiwoomCredentials.from_env())
        token_response = client.issue_token()
        token = token_response["token"]
        _, accounts_body = client.fetch_accounts(token)

        masked_token = f"{token[:10]}..." if len(token) > 10 else token

        print("[1] token issued")
        print(
            json.dumps(
                {
                    "base_url": client.credentials.base_url,
                    "token_type": token_response.get("token_type"),
                    "expires_dt": token_response.get("expires_dt"),
                    "token_preview": masked_token,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        print("\n[2] linked accounts")
        print(json.dumps(accounts_body, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
