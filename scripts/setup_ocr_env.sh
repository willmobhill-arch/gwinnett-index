#!/usr/bin/env bash
# Install what the Duluth OCR pass needs. Verified working in the Claude Code web
# container on 2026-08-12: tesseract 5.3.4 + pymupdf 1.28.2, 7/7 fields recovered
# from a synthetic image-only PDF.
#
# The container is ephemeral, so this has to be re-run in each new session. It is
# idempotent and takes about two minutes.
#
# NOTE: the Ubuntu archive is reachable through the agent proxy, but the launchpad
# PPAs are not. `apt-get update` prints 403s for those and still succeeds for the
# packages we need -- do not be alarmed by the warnings, and do not disable the
# proxy or TLS verification to make them go away.
set -euo pipefail

echo "==> tesseract"
if ! command -v tesseract >/dev/null 2>&1; then
  apt-get update -qq 2>/dev/null || true      # PPA 403s are expected and harmless
  apt-get install -y -qq tesseract-ocr
fi
tesseract --version | head -1

echo "==> python packages"
pip install --quiet pymupdf httpx
python3 -c "import pymupdf, httpx; print(f'  pymupdf {pymupdf.__version__}, httpx {httpx.__version__}')"

echo "==> self-test (no network needed)"
python3 -m unittest discover -s tests -q 2>&1 | tail -2

echo "==> network reachability (the other half of the problem)"
# Do not assert this -- measure it. The environment's policy can change between
# sessions, and a stale claim in either direction sends the next person the wrong
# way: chasing a firewall that is already open, or starting a 356-PDF crawl into
# a closed gateway.
blocked=0
for h in www.duluthga.net losmnziukaqptxhqnhjh.supabase.co gis3.gwinnettcounty.com geocoding.geo.census.gov; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "https://$h/" 2>/dev/null || echo 000)
  # any HTTP answer means the gateway let us through; 000 is a CONNECT refusal
  if [ "$code" = "000" ]; then printf '  BLOCKED  %s\n' "$h"; blocked=1
  else printf '  ok %-6s %s\n' "($code)" "$h"; fi
done

if [ "$blocked" = "1" ]; then
  cat <<'MSG'

At least one host is unreachable: the gateway is rejecting CONNECT for it.
crawl_duluth.py cannot fetch the meeting PDFs until that changes. Fix it in the
environment's network settings -- not by touching HTTPS_PROXY or TLS verification:
https://code.claude.com/docs/en/claude-code-on-the-web
MSG
  exit 1
fi

cat <<'MSG'

Ready. Run the pass from ingest/duluth_agendas:
  python3 crawl_duluth.py && python3 extract_text.py \
    && python3 ocr_scanned.py --jobs 8 && python3 parse_cases.py && python3 publish.py
MSG
