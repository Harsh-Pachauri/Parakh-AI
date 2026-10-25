"""Print which database the backend uses and whether the demo data is present.

Run from the repo root:  python backend/scripts/check_setup.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import get_settings  # noqa: E402


def main() -> None:
    url = get_settings().DATABASE_URL
    print(f"DATABASE_URL : {url}")
    if not url.startswith("sqlite"):
        print("Non-SQLite database: inspect it with your own client.")
        return
    path = Path(url.split(":///", 1)[1])
    print(f"DB file      : {path}  (exists: {path.exists()})")
    if not path.exists():
        print("-> No database yet. Run: backend/scripts/seed.py")
        return
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    for needed in ("institutions", "users", "courses", "assessments", "assignments"):
        print(f"table {needed:12}: {'OK' if needed in tables else 'MISSING'}")
    if "users" in tables:
        cols = {r[1] for r in con.execute("pragma table_info(users)")}
        print(f"users.institution_id: {'OK' if 'institution_id' in cols else 'MISSING (old schema)'}")
        for (email,) in con.execute("select email from users order by email"):
            print("  user:", email)
    if "institutions" in tables:
        for name, code in con.execute("select name, code from institutions"):
            print(f"  institution: {name} ({code})")
    missing = {"institutions", "assignments"} - tables
    if missing or "users" in tables and "institution_id" not in cols:
        print("-> OLD/INCOMPLETE DATABASE. Delete the .db file(s) and run seed.py again.")


if __name__ == "__main__":
    main()
