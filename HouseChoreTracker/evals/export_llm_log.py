"""Print the chore-bot's llm_log, to turn misses into eval cases.

On the VM:
    docker exec chore-bot python evals/export_llm_log.py            # last 50 entries
    docker exec chore-bot python evals/export_llm_log.py --scopes   # scope ids, for LLM_SCOPES
    docker exec chore-bot python evals/export_llm_log.py --jsonl > misses.jsonl

--jsonl writes eval-case skeletons; fix the "expect" part by hand and append
them to intent_cases.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("DATABASE_PATH", "/data/chores.db"))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--outcome", help="only this outcome, e.g. failed, chatter, unclear, low_confidence")
    parser.add_argument("--scopes", action="store_true", help="list known scope ids and exit")
    parser.add_argument("--jsonl", action="store_true", help="print eval-case skeletons")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    if args.scopes:
        rows = conn.execute(
            "SELECT scope_id, COUNT(*) AS chores FROM chores GROUP BY scope_id ORDER BY scope_id"
        ).fetchall()
        for row in rows:
            print(f"{row['scope_id']}  ({row['chores']} chores)")
        return

    query = "SELECT * FROM llm_log"
    params: list[object] = []
    if args.outcome:
        query += " WHERE outcome = ?"
        params.append(args.outcome)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)
    rows = list(reversed(conn.execute(query, params).fetchall()))

    for row in rows:
        if args.jsonl:
            chores = [r["name"] for r in conn.execute("SELECT name FROM chores WHERE scope_id = ?", (row["scope_id"],))]
            language_row = conn.execute(
                "SELECT language FROM chat_settings WHERE scope_id = ?", (row["scope_id"],)
            ).fetchone()
            print(
                json.dumps(
                    {
                        "language": language_row["language"] if language_row else "de",
                        "text": row["text"],
                        "chores": chores,
                        "group": row["scope_id"].startswith("group"),
                        "expect": {"kind": "?", "intent": None, "slots": {}},
                        "_got": row["raw_output"],
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(
                f"{row['created_at']}  {row['outcome']:<16} {row['latency_ms'] or 0:5d} ms  "
                f"{row['context'] or '-':<22} {row['text']!r}\n    -> {row['raw_output'][:300]}"
            )


if __name__ == "__main__":
    main()
