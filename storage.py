import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Storage:
    path: Path

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    side TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    order_type TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_payload TEXT NOT NULL,
                    response_body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    source_order_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS positions (
                    stock_code TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    avg_price REAL NOT NULL,
                    raw_body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runtime_flags (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS universe_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    codes_csv TEXT NOT NULL,
                    warnings TEXT NOT NULL
                );
                """
            )

    def set_runtime_flag(self, name: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_flags (name, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (name, value, utc_now()),
            )

    def save_universe_snapshot(self, source: str, codes: list[str], warnings: list[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO universe_snapshots (created_at, source, codes_csv, warnings)
                VALUES (?, ?, ?, ?)
                """,
                (utc_now(), source, ",".join(codes), "\n".join(warnings)),
            )

    def record_order(
        self,
        *,
        side: str,
        stock_code: str,
        quantity: int,
        price: int,
        order_type: str,
        mode: str,
        status: str,
        request_payload: dict,
        response_body: dict,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    created_at, side, stock_code, quantity, price, order_type,
                    mode, status, request_payload, response_body
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    side,
                    stock_code,
                    quantity,
                    price,
                    order_type,
                    mode,
                    status,
                    json.dumps(request_payload, ensure_ascii=False),
                    json.dumps(response_body, ensure_ascii=False),
                ),
            )

    def upsert_positions(self, rows: list[dict]) -> None:
        with self.connect() as conn:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO positions (stock_code, updated_at, quantity, avg_price, raw_body)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(stock_code) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        quantity=excluded.quantity,
                        avg_price=excluded.avg_price,
                        raw_body=excluded.raw_body
                    """,
                    (
                        row.get("stk_cd"),
                        utc_now(),
                        int(str(row.get("rmnd_qty", "0")).strip() or 0),
                        float(str(row.get("avg_prc", "0")).strip() or 0),
                        json.dumps(row, ensure_ascii=False),
                    ),
                )
