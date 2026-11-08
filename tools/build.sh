#!/usr/bin/env bash
# Build the designed Arabic PDF study from the Markdown sources.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python tools/build_html.py
node tools/render_pdf.js "$@"
echo "== output =="
ls -lh dist/
