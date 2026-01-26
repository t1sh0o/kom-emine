#!/bin/bash
set -e
cd "$(dirname "$0")/.."
python3 scripts/create_database.py
python3 scripts/export_json.py
echo "Done. Deploy web/ to Cloudflare Pages."
