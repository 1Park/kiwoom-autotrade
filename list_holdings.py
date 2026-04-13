import json
import os
import sys

from kiwoom_api import (
    KiwoomApiError,
    KiwoomClient,
    KiwoomCredentials,
    choose_account,
    normalize_holdings,
)


def parse_number(value: str) -> int | float | str:
    text = str(value).strip()
    if not text:
        return text
    if "." in text:
        return float(text)
    return int(text)


def simplify_holding(row: dict) -> dict:
    return {
        "stock_code": row.get("stk_cd"),
        "stock_name": row.get("stk_nm"),
        "quantity": parse_number(row.get("rmnd_qty", "0")),
        "avg_price": parse_number(row.get("avg_prc", "0")),
        "current_price": parse_number(row.get("cur_prc", "0")),
        "evaluation_amount": parse_number(row.get("evlt_amt", "0")),
        "profit_loss_amount": parse_number(row.get("pl_amt", "0")),
        "profit_loss_rate": parse_number(row.get("pl_rt", "0")),
    }


def main() -> int:
    try:
        client = KiwoomClient(KiwoomCredentials.from_env())
        token = client.issue_token()["token"]
        _, accounts_body = client.fetch_accounts(token)
        account_no = choose_account(accounts_body, os.getenv("KIWOOM_ACCOUNT_NO"))
        _, holdings_body = client.fetch_holdings(token, account_no)
        holdings = normalize_holdings(holdings_body)
        simplified = [simplify_holding(row) for row in holdings]

        print(
            json.dumps(
                {
                    "account_no": account_no,
                    "holdings_count": len(simplified),
                    "holdings": simplified,
                    "summary": {
                        key: value
                        for key, value in holdings_body.items()
                        if not isinstance(value, list)
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except KiwoomApiError as exc:
        print(f"API ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
