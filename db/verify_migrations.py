#!/usr/bin/env python3
"""Diff db/migrations/ against what is actually applied to the project.

Three migrations that had been applied to production for days had no file in this
repo at all: `resolver_score_function`, `resolver_score_cache` and
`duluth_loader_latest_decision_wins`. Nothing was broken and nothing complained --
the site built, the API answered, every page rendered. The damage would only have
appeared on a rebuild from `db/migrations` alone, which is exactly the moment you
cannot afford to discover that a quarter of the loader logic is missing.

It has happened before in the other direction too: `code_table.quality` and
`land_use_case.applicant_norm` existed only in production, and a loader written
against the repo's schema errored on first use.

So: compare by NAME, not by memory, and compare the md5 of the file body against
the md5 of the statement the database recorded. A filename that merely looks right
is not evidence.

    DATABASE_URL=postgresql://... python3 db/verify_migrations.py

Exit 0 clean, 1 on any disagreement.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
NAME_RE = re.compile(r"^(\d{14})_(.+)\.sql$")


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("set DATABASE_URL to a direct Postgres connection for this project")
        return 2
    try:
        import psycopg
    except ImportError:
        print("pip install psycopg[binary]")
        return 2

    files: dict[str, tuple[str, str]] = {}
    for p in sorted(MIGRATIONS.glob("*.sql")):
        m = NAME_RE.match(p.name)
        if not m:
            print(f"  BAD NAME  {p.name} — expected <14-digit version>_<name>.sql")
            return 1
        # The database stores the statement without a trailing newline; the file has
        # one. Strip exactly that, and nothing else -- normalising whitespace here
        # would hide the very drift this script exists to find.
        body = p.read_text().rstrip("\n")
        files[m.group(2)] = (m.group(1), hashlib.md5(body.encode()).hexdigest())

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT version, name, array_length(statements, 1), md5(statements[1]) "
            "FROM supabase_migrations.schema_migrations ORDER BY version"
        ).fetchall()

    # Every migration here was applied whole, so statements[1] IS the file body and
    # its md5 is directly comparable. If that ever stops being true the comparison
    # becomes meaningless, and a meaningless check that prints "ok" is worse than
    # no check -- so refuse rather than rejoin the pieces and hope.
    split = [(v, n) for v, n, k, _ in rows if k != 1]
    if split:
        for v, n in split:
            print(f"  MULTI-STATEMENT {v}_{n} — stored in pieces; md5 comparison is not valid")
        return 1
    applied = {name: (version, digest) for version, name, _k, digest in rows}

    bad = 0
    for name, (version, _) in applied.items():
        if name not in files:
            print(f"  MISSING FILE   {version}_{name}.sql — applied to the database, not in the repo")
            bad += 1
    for name, (version, _) in files.items():
        if name not in applied:
            print(f"  NOT APPLIED    {version}_{name}.sql — in the repo, never recorded as applied")
            bad += 1
    for name in sorted(set(files) & set(applied)):
        fver, fmd5 = files[name]
        dver, dmd5 = applied[name]
        if fmd5 != dmd5:
            print(f"  CONTENT DRIFT  {name}: file md5 {fmd5}, database md5 {dmd5}")
            bad += 1
        elif fver != dver:
            # Harmless on its own -- the file was named before it was applied -- but
            # it means repo filename order is not apply order, so say it out loud.
            print(f"  version differs {name}: file {fver}, applied {dver}")

    print(f"\n{len(files)} file(s), {len(applied)} applied, {bad} disagreement(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
