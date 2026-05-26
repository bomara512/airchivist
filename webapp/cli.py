import argparse
import sys
from pathlib import Path
from webapp.app import create_app


def main(args=None):
    parser = argparse.ArgumentParser(description="ViewTube web server")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")

    parsed = parser.parse_args(args)

    if not Path(parsed.db).exists():
        print(f"Error: database not found: {parsed.db}", file=sys.stderr)
        sys.exit(1)

    app = create_app(parsed.db)
    app.run(host=parsed.host, port=parsed.port, debug=parsed.debug)


if __name__ == "__main__":
    main()
