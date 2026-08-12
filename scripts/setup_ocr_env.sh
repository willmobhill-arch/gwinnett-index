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

cat <<'MSG'

Dependencies are ready. The remaining blocker for the OCR pass is NETWORK:
crawl_duluth.py must reach www.duluthga.net, which this environment's policy
currently rejects at the gateway (CONNECT -> 403).

Hosts the project needs egress to:
  www.duluthga.net, duluthga.net        the meeting PDFs           (OCR pass)
  losmnziukaqptxhqnhjh.supabase.co      snapshot export, PostgREST (site builds)
  gis3.gwinnettcounty.com               county ArcGIS + geocoder   (case ingest)
  geocoding.geo.census.gov              geocoder fallback          (worker tests)

Change it in the environment's network settings:
https://code.claude.com/docs/en/claude-code-on-the-web
MSG
