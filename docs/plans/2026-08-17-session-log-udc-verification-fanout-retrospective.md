# Session log: the UDC verification fan-out — process retrospective

**Date:** 2026-08-17
**What happened:** the five `unverified` UDC tables (828 of 997 table rows) were
read cell-by-cell against rendered pages by nine parallel reading agents, one
extractor bug was found and fixed (ten corrupted 4-B cells), and the corpus went
to 20/20 `verified` — loaded, snapshotted, rebuilt, deployed, merged (#4), all in
one session. The two previous table passes took three sessions for fifteen
tables. This log is about why this one was cheap, and what almost made it not be.

---

## The shape of the process

1. **Setup and sanity** — download the PDF, check its sha256 against the fixture
   pin, render one page and confirm the page-numbering convention (PDF page 139 =
   printed "138 | Page") *before* briefing anyone.
2. **One shared briefing file** (`BRIEFING.md` in the scratchpad) — what to
   check, the reporting format, the conventions that are not errors, the known
   hazards. Nine short per-agent prompts pointing at it, each naming only a page
   range and a slice name.
3. **Fan-out** — 9 agents: one per small table, three per 333-row 2-C matrix,
   slicing by page range and aligning to row indices by content. All launched
   concurrently; the whole read took ~6 minutes of wall clock for ~10,000 cells.
4. **Spot-check before promotion** — every load-bearing claim re-read on a fresh
   render by the orchestrator: all ten 4-B defects, the merged 5178 tower rows
   (p83), the "Day Car" typos (p92), the empty p94.
5. **Batch the fixes, rerun once, diff the whole corpus** — the old vs new
   `extracted_cells.json` diff was the promotion evidence: exactly the ten 4-B
   cells changed, nothing else in 20 tables.
6. **Promote in one place** (`VERIFIED_AGAINST_RENDER`), publish, load, verify in
   the DB, snapshot, build, deploy, check the live origin.

## What worked, and is worth repeating

- **Brief on what to check, never on what they will find.** All nine briefings
  were identical in method. Four tables came back clean and one came back with
  ten defects — the difference came from the pages, not from the prompt. The
  earlier lesson (12-A's briefing contaminating the reader) held: nothing in the
  briefing told the 4-B agent to expect glued cells, and it found them anyway,
  with the exact stored-vs-rendered values that made verification trivial.
- **Falsifiable claims are what make delegation safe.** The report format
  demanded `{row, col, page, stored, rendered}` per discrepancy. That is what
  let ten claims be spot-checked in two page renders, and it is why the "unsure
  is useful, a guess is poison" line belongs in every reading briefing.
- **Slicing big tables by page range worked** because coverage was reported as
  explicit row-index ranges per page and the orchestrator checked they tiled:
  0–122 / 123–250 / 251–332 with no gap or overlap. An agent asked to "read the
  table" cannot be reconciled; an agent asked "which indices did you cover, per
  page" can.
- **Independent corroboration came free.** The two 2-D tables share rows, and
  both readers independently reported the same source typos ("Swamp Meets",
  "Accessory Day Car Centers") at the same row indices. Overlapping slices
  weren't designed for this, but where they exist, agreement is evidence.
- **The one-page sanity check before briefing** (render p139, see "138 | Page")
  killed the entire class of off-by-one page reports before it could exist.
  Minutes spent; every downstream report used the same convention.
- **Committing the derived artifact paid off again.** `var/extracted_cells.json`
  being in git meant the post-fix rerun could be diffed against the exact bytes
  the agents had verified — "only the ten cells changed" is a strong statement
  only because the baseline was pinned.
- **The known-hazards section changed agent behavior.** Told that
  single-letter-in-narrow-column misattribution was the likely failure, several
  agents invented header-x-position crops and pixel-alignment checks on their
  own. Naming the failure mode is cheaper than prescribing the method.

## What almost went wrong — the container is part of the experiment

- **pymupdf 1.28 printed a banner on the subprocess's data channel**, the parser
  swallowed the decode error, and every page silently became "no ruled table
  found". A fresh rerun in this container would have produced an empty corpus
  with exit 0. It was caught only because the test suite ran *before* the rerun
  was trusted — 17 of 23 tests failed on what looked like a healthy setup.
  **Rule: in a fresh container, run the extraction suite first, before
  re-running anything whose output you intend to compare.** Library drift
  between the container that produced a committed artifact and the container
  re-verifying it is a real failure channel, now documented in CLAUDE.md.
- **The sha256 pin earned its keep.** The PDF was re-downloaded from the city on
  a new day; had Duluth amended it in the interim, all nine readings would have
  verified cells against a document the store no longer describes. One hash
  check forecloses that.

## What the readings found beyond the defects

The zero-discrepancy tables were not zero-information. The structural
observations (band rows stored as blank rows, the folded 5178 rows whose merged
cross-reference spans all districts, footnote digits, position-only
subordination) went into the `verification_note`s — that is the channel for
"correct but misleading", and the agents surfaced more of it per table than the
earlier hand passes did, because each was asked explicitly for "anything a
reader who cannot see the page would be misled by".

## Cost accounting

~810k subagent tokens across nine readers, ~6 minutes wall for the reading,
roughly one session end to end including the fix loop, deploy and merge.
Against the alternative — the earlier passes averaged five tables per session
reading serially — the fan-out is roughly a session's work saved per five
tables, with *better* evidence quality (explicit coverage ranges, falsifiable
claims) rather than a speed/rigor trade.

## For next time

- Keep promotion serial and human-shaped even when reading is parallel. The
  bottleneck (orchestrator spot-checks) is the point, not overhead to optimize
  away.
- Reports as scratchpad JSON files + compact summaries worked; the files
  survived agent completion and were re-checkable. Keep that.
- If slices are designed to overlap by one row on purpose, coverage
  reconciliation catches misalignment *and* every boundary gets read twice.
  This pass tiled exactly; a one-row overlap would have been strictly better
  for near-zero cost.
- The briefing said renders were `pNNN.png` zero-padded; the 4-B renders were
  written unpadded (`p139.png`). The readers coped, but exact paths in
  briefings should match exactly — an agent that trusts the briefing over `ls`
  would have stalled.
