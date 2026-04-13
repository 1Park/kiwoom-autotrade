import argparse
import json
import sys
from pathlib import Path

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
from storage import Storage
from universe import UniverseSnapshot, resolve_universe


DB_PATH = Path("runtime.sqlite3")


def parse_number(value: str) -> int | float | str:
    text = str(value).strip()
    if not text:
        return text
    if "." in text:
        return float(text)
    return int(text)


def simplify_holding(row: dict) -> dict:
    return {
        "stock_code": normalize_stock_code(str(row.get("stk_cd", ""))),
        "stock_name": row.get("stk_nm"),
        "quantity": parse_number(row.get("rmnd_qty", "0")),
        "avg_price": parse_number(row.get("avg_prc", "0")),
        "current_price": parse_number(row.get("cur_prc", "0")),
        "evaluation_amount": parse_number(row.get("evlt_amt", "0")),
        "profit_loss_amount": parse_number(row.get("pl_amt", "0")),
        "profit_loss_rate": parse_number(row.get("pl_rt", "0")),
    }


def build_client() -> tuple[KiwoomClient, RuntimeConfig]:
    client = KiwoomClient(KiwoomCredentials.from_env())
    config = RuntimeConfig.from_env()
    return client, config


def dump(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def resolve_account(config: RuntimeConfig, accounts_body: dict, explicit_account: str | None = None) -> str:
    account_no = explicit_account or config.target_account_id
    if not account_no:
        return choose_account(accounts_body)
    chosen = choose_account(accounts_body, account_no)
    if chosen not in normalize_accounts(accounts_body):
        raise KiwoomApiError(f"Target account {chosen} was not found in linked accounts.")
    return chosen


def guard_universe(universe: UniverseSnapshot, stock_code: str) -> None:
    normalized_code = normalize_stock_code(stock_code)
    if normalized_code not in universe.codes:
        raise KiwoomApiError(
            f"Stock code {normalized_code} is outside the allowed universe {universe.codes}."
        )


def command_doctor(args: argparse.Namespace) -> int:
    client, config = build_client()
    storage = Storage(DB_PATH)
    storage.init_db()
    token_response = client.issue_token()
    token = token_response["token"]
    _, accounts_body = client.fetch_accounts(token)
    accounts = normalize_accounts(accounts_body)
    universe = resolve_universe(client, token, config)
    storage.save_universe_snapshot(universe.source, universe.codes, universe.warnings)
    dump(
        {
            "base_url": client.credentials.base_url,
            "linked_accounts": accounts,
            "target_account_id": config.target_account_id or None,
            "autotrade_group_name": config.autotrade_group_name,
            "universe_source": universe.source,
            "allowed_stock_codes": universe.codes,
            "warnings": universe.warnings,
            "token_expires_dt": token_response.get("expires_dt"),
        }
    )
    return 0


def command_accounts(args: argparse.Namespace) -> int:
    client, _ = build_client()
    token = client.issue_token()["token"]
    _, body = client.fetch_accounts(token)
    dump({"accounts": normalize_accounts(body), "raw": body})
    return 0


def command_holdings(args: argparse.Namespace) -> int:
    client, config = build_client()
    storage = Storage(DB_PATH)
    storage.init_db()
    token = client.issue_token()["token"]
    _, accounts_body = client.fetch_accounts(token)
    account_no = resolve_account(config, accounts_body, args.account_no)
    _, holdings_body = client.fetch_holdings(token, account_no)
    raw_holdings = normalize_holdings(holdings_body)
    storage.upsert_positions(raw_holdings)
    holdings = [simplify_holding(row) for row in raw_holdings]
    dump({"account_no": account_no, "holdings": holdings, "summary": holdings_body})
    return 0


def command_quote(args: argparse.Namespace) -> int:
    client, _ = build_client()
    token = client.issue_token()["token"]
    normalized_code = normalize_stock_code(args.stock_code)
    _, body = client.fetch_quote(token, normalized_code)
    dump({"stock_code": normalized_code, "quote": body})
    return 0


def command_open_orders(args: argparse.Namespace) -> int:
    client, config = build_client()
    token = client.issue_token()["token"]
    _, accounts_body = client.fetch_accounts(token)
    account_no = resolve_account(config, accounts_body, args.account_no)
    _, body = client.fetch_open_orders(token, account_no, args.stock_code or "")
    dump({"account_no": account_no, "open_orders": body})
    return 0


def command_order(args: argparse.Namespace, *, side: str) -> int:
    client, config = build_client()
    storage = Storage(DB_PATH)
    storage.init_db()
    token = client.issue_token()["token"]
    _, accounts_body = client.fetch_accounts(token)
    account_no = resolve_account(config, accounts_body, args.account_no)
    universe = resolve_universe(client, token, config)
    request_payload = {
        "account_no": account_no,
        "stock_code": normalize_stock_code(args.stock_code),
        "quantity": args.quantity,
        "price": args.price,
        "order_type": args.order_type,
    }
    normalized_code = normalize_stock_code(args.stock_code)
    guard_universe(universe, normalized_code)

    if args.dry_run:
        storage.record_order(
            side=side,
            stock_code=normalized_code,
            quantity=args.quantity,
            price=args.price,
            order_type=args.order_type,
            mode="dry_run",
            status="validated",
            request_payload=request_payload,
            response_body={"universe_source": universe.source},
        )
        dump(
            {
                "mode": "dry_run",
                "side": side,
                "account_no": account_no,
                "stock_code": args.stock_code,
                "normalized_stock_code": normalized_code,
                "quantity": args.quantity,
                "price": args.price,
                "order_type": args.order_type,
                "universe_source": universe.source,
            }
        )
        return 0

    if side == "buy":
        _, body = client.place_buy_order(
            token,
            account_no,
            normalized_code,
            args.quantity,
            price=args.price,
            order_type=args.order_type,
        )
    else:
        _, body = client.place_sell_order(
            token,
            account_no,
            normalized_code,
            args.quantity,
            price=args.price,
            order_type=args.order_type,
        )

    storage.record_order(
        side=side,
        stock_code=normalized_code,
        quantity=args.quantity,
        price=args.price,
        order_type=args.order_type,
        mode="live",
        status="submitted",
        request_payload=request_payload,
        response_body=body,
    )
    dump(
        {
            "mode": "live",
            "side": side,
            "account_no": account_no,
            "stock_code": args.stock_code,
            "normalized_stock_code": normalized_code,
            "quantity": args.quantity,
            "price": args.price,
            "order_type": args.order_type,
            "universe_source": universe.source,
            "response": body,
        }
    )
    return 0


def command_cancel(args: argparse.Namespace) -> int:
    client, config = build_client()
    token = client.issue_token()["token"]
    _, accounts_body = client.fetch_accounts(token)
    account_no = resolve_account(config, accounts_body, args.account_no)
    _, body = client.cancel_order(
        token, account_no, args.order_no, args.stock_code, args.quantity
    )
    dump({"account_no": account_no, "response": body})
    return 0


def command_dry_run(args: argparse.Namespace) -> int:
    client, config = build_client()
    storage = Storage(DB_PATH)
    storage.init_db()
    token = client.issue_token()["token"]
    universe = resolve_universe(client, token, config)
    storage.save_universe_snapshot(universe.source, universe.codes, universe.warnings)
    dump(
        {
            "mode": "dry_run",
            "strategy": "manual_strategy_placeholder",
            "universe_source": universe.source,
            "allowed_stock_codes": universe.codes,
            "signals": [],
            "warnings": universe.warnings,
        }
    )
    return 0


def command_run(args: argparse.Namespace) -> int:
    return command_dry_run(args)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kiwoom ISA autotrade CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check auth, accounts, and universe.")
    doctor.set_defaults(func=command_doctor)

    accounts = subparsers.add_parser("accounts", help="List linked accounts.")
    accounts.set_defaults(func=command_accounts)

    holdings = subparsers.add_parser("holdings", help="Show holdings for the target account.")
    holdings.add_argument("--account-no", default="")
    holdings.set_defaults(func=command_holdings)

    quote = subparsers.add_parser("quote", help="Fetch quote for a stock.")
    quote.add_argument("stock_code")
    quote.set_defaults(func=command_quote)

    open_orders = subparsers.add_parser("open-orders", help="Show open orders.")
    open_orders.add_argument("--account-no", default="")
    open_orders.add_argument("--stock-code", default="")
    open_orders.set_defaults(func=command_open_orders)

    buy = subparsers.add_parser("buy", help="Place a buy order.")
    buy.add_argument("stock_code")
    buy.add_argument("quantity", type=int)
    buy.add_argument("--price", type=int, default=0)
    buy.add_argument("--order-type", default="03")
    buy.add_argument("--account-no", default="")
    buy.add_argument("--dry-run", action="store_true")
    buy.set_defaults(func=lambda args: command_order(args, side="buy"))

    sell = subparsers.add_parser("sell", help="Place a sell order.")
    sell.add_argument("stock_code")
    sell.add_argument("quantity", type=int)
    sell.add_argument("--price", type=int, default=0)
    sell.add_argument("--order-type", default="03")
    sell.add_argument("--account-no", default="")
    sell.add_argument("--dry-run", action="store_true")
    sell.set_defaults(func=lambda args: command_order(args, side="sell"))

    cancel = subparsers.add_parser("cancel", help="Cancel an order.")
    cancel.add_argument("order_no")
    cancel.add_argument("stock_code")
    cancel.add_argument("quantity", type=int)
    cancel.add_argument("--account-no", default="")
    cancel.set_defaults(func=command_cancel)

    dry_run = subparsers.add_parser("dry-run", help="Run a non-trading strategy cycle.")
    dry_run.set_defaults(func=command_dry_run)

    run = subparsers.add_parser("run", help="Run the trading loop placeholder.")
    run.set_defaults(func=command_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KiwoomApiError as exc:
        print(f"API ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
