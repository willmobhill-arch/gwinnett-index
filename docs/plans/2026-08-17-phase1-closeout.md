# Phase 1 closeout — outstanding items

**2026-08-17 (rev 2)** · `main` at `275acbf` · verified against production, not against the repo's
own claims. Destined for `docs/plans/`.

UDC table verification landed in #4: all 20 tables are `verified`, and production agrees
(`table-2-b.md` has its `RA-200` row, `table-9-a.md` has 8 `Local Street` rows, sitemap
15,238). What follows is what still stands between here and a clean Phase 1 close.

Two of these are **live wrong answers on agent-facing surfaces**, which for this product
is the most expensive category of defect there is: an agent cannot tell a confident wrong
answer from a right one.

---

## 1. Duluth has no `code_citation` in production — BLOCKER

`/j/duluth.md` states:

```
- **Code:** not indexed here
```

on the same page that reports **858 code sections**, while `/code/duluth` returns 200 and
serves the full corpus including all 20 verified tables. `resolve_jurisdiction` for a
Duluth address returns:

```json
"code": { "citation": null, "url": null }
```

The MCP tool's own description promises the governing jurisdiction "with its code
citation." For the one municipality with a complete corpus, it returns null.

**2 of 19 jurisdictions carry a citation** — `unincorporated-gwinnett` and
`gwinnett-county`, both pointing at the county UDO.

The tell: `site/fixtures/jurisdictions.json` has the correct value —
`duluth -> "Duluth Unified Development Code"`. The fixture is right and the database is
not, so a fixture-backed build looks correct and only production is wrong. Same shape as
the ten-record sample that passed CI for weeks.

Fix — one row in Supabase:

```sql
UPDATE jurisdiction
SET code_citation = 'Duluth Unified Development Code',
    code_url      = 'https://www.duluthga.net/UDC_ADOPTED_9.8.2025_Amended_7-13-26.pdf'
WHERE slug = 'duluth';
```

Do not hardcode that filename anywhere else — it encodes the amendment date and changes
on every amendment. Scrape the link. (Existing note in the 08-14 handoff.)

Then decide the general rule: 16 municipalities resolve correctly with no corpus behind
them. `null` is arguably honest for those. But `null` and "not indexed here" must not
render identically for a jurisdiction that *is* indexed.

## 2. The status page contradicts itself — BLOCKER

`status.md` Coverage table:

| Code tables | 20 |
| — verified against the source page | 20 |

`status.md` Known gaps, immediately below:

> **0 of 20 code tables are unverified.** Only Table 2-B has been checked against the
> rendered source page, and even its merged PUD and CBD rows remain unreliable.

The count is templated; the sentence after it is hardcoded prose from when only 2-B was
verified. The number updated. The claim did not.

This is on the one page whose entire job is to be honest about staleness, and it is
telling crawlers both "20 of 20 verified" and "only 2-B checked."

Three files carry it:

| File | Line | What |
|---|---|---|
| `site/src/pages/status.md.ts` | 62 | `${s.code_tables - s.code_tables_verified} of ${s.code_tables} … Only Table 2-B has been checked` |
| `site/src/pages/status.astro` | 74 | same sentence, HTML twin |
| `site/src/pages/llms.txt.ts` | 38 | `… ${…} of ${…} code tables have never been checked` — rule 5 |

Fix: suppress the bullet entirely when `code_tables_verified === code_tables`, and delete
the hardcoded "Only Table 2-B" clause rather than editing it — it will go stale again the
next time the count moves.

A regression guard worth adding: assert that no rendered page contains a hardcoded table
citation that isn't derived from the snapshot.

## 3. `tests/test_resolver.py` was never committed

Phase 1's own exit criteria in `docs/plans/2026-08-12-gwinnett-index-build-plan.md`:

> - [ ] Build a test set of **20 known addresses**: 10 inside Duluth city limits, 10 with
>       a Duluth mailing address but in unincorporated county.
> - [ ] Assert 20/20 correct. Commit as `tests/test_resolver.py`.

Both boxes are still unchecked and the file does not exist. `tests/` holds only
`test_ocr_scanned.py`, `test_udc_tables.py` and the fixture.

The resolver is not unproven — `status.md` reports 1,915 probe points at 98.85% overall,
with the high-confidence band never wrong and every error inside 141 m of a line. That is
a stronger result than the 20-address test asked for. **But it is a one-time, DB-side
measurement, not a gate.** Nothing re-runs it on a build. The spine of the product has no
regression test, and a resolver that starts returning confidently wrong jurisdictions
would look exactly like one that is right.

Cheapest sufficient version: freeze 20 probes (10 city / 10 unincorporated mailing
address) as a committed fixture, assert 20/20 in CI against the live resolver.

## 4. Housekeeping

- ~~PR #5 open~~ **merged** (`275acbf`) — docs only, touches nothing the patch touches.
- **`docs/plans/2026-08-15-session-handoff.md` line 7** still reads
  `Branch: claude/buildout-process-continuation-tfh56r · PR #1 (draft)`. Fixed in the
  patch.
- **Two merged branches remain undeleted** on the remote:
  `claude/api-key-rotation-4wv8fl`, `claude/buildout-process-continuation-tfh56r`.
  (`claude/udc-table-verification-r6c2yl` was already cleaned up.)

## 5. Honestly-labelled gaps — scope decision, not defects

These are disclosed correctly on `status.md`. They are only blockers if Phase 1 is
defined to include them:

| Gap | State |
|---|---|
| 262 applicant name pairs await human review | developer counts are lower bounds |
| Duluth minutes 57–69% scanned, OCR pass incomplete | text stored as reconstruction, never quoted |
| ~23 of 110 Duluth cases have no parsed outcome | minutes parser round two |
| 16 municipalities have boundaries, no corpus | resolve correctly; Phase 2+ scope |

Recommendation: 1–4 close Phase 1. The table above is Phase 2 intake, with the exception
of anything that would change a *published* number.

---

## Verified on production, 2026-08-17

| Check | Result |
|---|---|
| Apex 301 → www, query preserved | ✅ |
| GPTBot / ClaudeBot / CCBot on `/j/duluth` | 200 / 200 / 200 |
| Sitemap `<loc>` count | 15,238 |
| `.md` twin present on 12 sampled pages | ✅ all |
| `/data.json`, `/catalog.jsonld` parse | ✅ 3 datasets each |
| MCP `initialize`, no credentials | ✅ proto 2025-06-18, 1,148-char instructions |
| All five MCP tools listed | ✅ |
| `resolve_jurisdiction` city vs unincorporated | ✅ both high confidence, correct |
| Registry `net.gwindex/gwinnett-index` | 0.1.0, active |
| Apex `AAAA` + `TXT` intact after deploy | ✅ both |
| Secret scan, all refs including #4 and #5 | no literal credentials |

---

## Resolution — 2026-08-17, same day

Items 1–4 closed in the PR that carries this document:

1. **Duluth `code_citation`** — the one-row UPDATE ran against production
   (citation + URL, filename not hardcoded anywhere in code). The general rule
   landed as a build gate: a jurisdiction whose own snapshot row says it has code
   sections must name its citation and must never render "not indexed here" —
   `null` stays honest for the 16 municipalities without a corpus.
2. **Status contradiction** — the hardcoded "Only Table 2-B" clause is deleted in
   all three files; the unverified-count bullet renders only while
   `code_tables_verified < code_tables`. The suggested regression guard exists as
   a gate: status prose must agree with the snapshot's verified count, in both
   directions (no stale unverified claim when all are verified, no silent gap when
   some are not).
3. **`tests/test_resolver.py`** — committed, with
   `tests/fixtures/resolver_probes.json`: 20 frozen points (10 city / 10
   unincorporated within 3 km of the Duluth boundary), asserted correct at high
   confidence with the expected `code_citation`, via the same RPC the Worker
   calls, as the anon role. 20/20 against production before commit. Points, not
   addresses: the geocoder's drift is not the resolver's regression.
4. **Housekeeping** — handoff line fixed; build-plan §1.3 boxes checked. Branch
   deletion (`claude/api-key-rotation-4wv8fl`,
   `claude/buildout-process-continuation-tfh56r`) was blocked by session
   permissions — still open, one `git push origin --delete` from any operator.

Item 5 confirmed as Phase 2 intake. Snapshot re-exported, site rebuilt, deployed,
and re-verified against production after the fixes.
