"""Server commands. Usage:

    docker compose exec app python -m app.cli set-user <username>
    echo -n 'secret' | docker compose exec -T app python -m app.cli set-user <username> --password-stdin

set-user creates the account or replaces its password (and logs out its sessions).
reparse <run_id> parses an earlier run's stored pages again, without contacting the shop.
images copies new offer photos now (normally 4:45 each night).
"""

import argparse
import getpass
import sys

import psycopg
from argon2 import PasswordHasher

from . import config


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    set_user = sub.add_parser("set-user")
    set_user.add_argument("username")
    set_user.add_argument("--password-stdin", action="store_true")
    reparse = sub.add_parser("reparse", help="parse an earlier run's stored pages again")
    reparse.add_argument("run_id", type=int)
    sub.add_parser("images", help="copy new offer photos now")
    sub.add_parser("reassess-localities", help="place / collection-number names become forms")
    arc = sub.add_parser("archive", help="history from web archives")
    arc.add_argument("action", choices=["discover", "run", "reread", "reference"])
    arc.add_argument("shop_ids", type=int, nargs="+")
    arc.add_argument("--limit", type=int)
    arc.add_argument("--csv", help="reference CSV (for 'reference'), read from stdin if '-'")
    args = parser.parse_args()

    if args.cmd == "archive":
        from . import archive
        from .db import pool

        pool.open(wait=True)
        try:
            if args.action == "discover":
                for sid in args.shop_ids:
                    print(sid, archive.discover(sid))
            elif args.action == "run":
                print(archive.run_queue(args.shop_ids, args.limit))
            elif args.action == "reread":
                for sid in args.shop_ids:
                    print(sid, archive.reread(sid))
            else:
                text = sys.stdin.read() if args.csv in (None, "-") else open(args.csv, encoding="utf-8").read()
                print(archive.import_reference(args.shop_ids[0], text), "reference rows")
        finally:
            pool.close()
        return

    if args.cmd == "reassess-localities":
        from . import taxonomy
        from .db import pool

        pool.open(wait=True)
        try:
            print(taxonomy.reassess_localities())
        finally:
            pool.close()
        return

    if args.cmd == "images":
        from . import images
        from .db import pool

        pool.open(wait=True)
        try:
            print(images.nightly())
        finally:
            pool.close()
        return

    if args.cmd == "reparse":
        from . import collect
        from .db import pool

        pool.open(wait=True)
        try:
            print(collect.reparse_run(args.run_id))
        finally:
            pool.close()
        return

    if args.password_stdin:
        password = sys.stdin.read().rstrip("\r\n")
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat: "):
            sys.exit("Passwords differ.")
    if len(password) < 10:
        sys.exit("Password needs at least 10 characters.")

    password_hash = PasswordHasher().hash(password)
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)"
            " ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash"
            " RETURNING id",
            (args.username, password_hash),
        ).fetchone()
        conn.execute("DELETE FROM sessions WHERE user_id = %s", (row[0],))
    print(f"User '{args.username}' saved.")


if __name__ == "__main__":
    main()
