"""
The resolver against twenty frozen probes — the spine of the product, finally gated.

This is the Phase 1 exit criterion from docs/plans/2026-08-12-gwinnett-index-build-plan.md
(10 points inside Duluth, 10 with a Duluth mailing address in unincorporated county),
committed 2026-08-17. The 1,915-point resolver_probe measurement is stronger evidence,
but it is a one-time, DB-side number; nothing re-ran it. A resolver that started
returning confidently wrong jurisdictions would have looked exactly like one that is
right, on the product whose entire pitch is that the mailing address is not the
jurisdiction.

Probes are POINTS, not addresses, on purpose: the public /v1/resolve geocodes first,
and a geocoder's drift is not the resolver's regression. The RPC is called the same
way the Worker calls it, with the anon key — which also asserts, on every run, that
anonymous execute on resolve_jurisdiction still works.

The citation assertion is not decoration. /j/duluth rendered "Code: not indexed here"
over an 858-section corpus because the jurisdiction row's code_citation was null in
production while the fixture had the right value — a fixture-backed build looked
correct and only production was wrong. A null citation for an indexed jurisdiction
fails here now.

Needs the database. Skips loudly rather than passing vacuously when it is absent:

    SUPABASE_URL=https://<ref>.supabase.co \\
    SUPABASE_ANON_KEY=sb_publishable_... \\
    python3 -m pytest tests/test_resolver.py -v
"""
from __future__ import annotations

import json
import os
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'resolver_probes.json')

URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
KEY = os.environ.get('SUPABASE_ANON_KEY', '')

needs_db = pytest.mark.skipif(
    not (URL and KEY),
    reason='set SUPABASE_URL and SUPABASE_ANON_KEY -- see this module docstring',
)


def resolve(lng: float, lat: float, band_m: int = 150) -> dict | None:
    req = urllib.request.Request(
        f'{URL}/rest/v1/rpc/resolve_jurisdiction', method='POST',
        data=json.dumps({'lon': lng, 'lat': lat, 'band_m': band_m}).encode(),
    )
    req.add_header('apikey', KEY)
    req.add_header('Authorization', f'Bearer {KEY}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.loads(r.read().decode())
    return rows[0] if rows else None


def probes():
    return json.load(open(FIXTURE))['probes']


@needs_db
@pytest.mark.parametrize('p', probes(), ids=lambda p: f"{p['expected_slug']}-{p['id']}")
def test_probe_resolves_to_frozen_answer(p):
    r = resolve(p['lng'], p['lat'])
    assert r is not None, f"probe {p['id']}: resolver returned no row"
    assert r['slug'] == p['expected_slug'], (
        f"probe {p['id']}: resolved to {r['slug']!r}, frozen answer is "
        f"{p['expected_slug']!r} -- the spine regressed"
    )
    # These points were chosen to be solidly inside their jurisdiction. A confidence
    # downgrade on them means the band logic moved, not that the ground did.
    assert r['confidence'] == 'high', (
        f"probe {p['id']}: confidence {r['confidence']!r}, frozen at 'high'"
    )
    assert r.get('code_citation') == p['expected_citation'], (
        f"probe {p['id']}: code_citation {r.get('code_citation')!r}, expected "
        f"{p['expected_citation']!r} -- an indexed jurisdiction answering without its "
        f"citation is the /j/duluth 'not indexed here' defect again"
    )
