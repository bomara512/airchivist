#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f demo.db ]; then
    echo "No demo.db found — seeding one now..."
    python scripts/seed_demo_db.py --output demo.db
fi

echo "Starting ViewTube demo at http://localhost:8080"
viewtube-web --db demo.db --port 8080
