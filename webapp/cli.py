import argparse
import sqlite3
import sys
from pathlib import Path
from webapp.app import create_app
from webapp.db import collapse_case_variants


def main(args=None):
    parser = argparse.ArgumentParser(description="Airchivist web server")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    parser.add_argument("--normalize-tags", action="store_true",
                        help="Merge case-duplicate tags and exit (one-time maintenance)")

    parsed = parser.parse_args(args)

    if not Path(parsed.db).exists():
        print(f"Error: database not found: {parsed.db}", file=sys.stderr)
        sys.exit(1)

    if parsed.normalize_tags:
        conn = sqlite3.connect(parsed.db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        deleted = collapse_case_variants(conn)
        conn.close()
        print(f"Merged {deleted} duplicate tag row(s).")
        return

    app = create_app(parsed.db)
    app.run(host=parsed.host, port=parsed.port, debug=parsed.debug)


if __name__ == "__main__":
    main()
