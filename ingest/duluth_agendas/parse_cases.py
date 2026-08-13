#!/usr/bin/env python3
"""
Parse structured land-use case items out of Duluth agendas and minutes.

Duluth publishes no case tracker of any kind -- no portal, no dashboard, no
export. The only public record of what was filed and what happened to it is the
agenda text, which fortunately follows a rigid template:

    1. Case: MZ2026-001, Ariel Rodriguez Collazo, 3465 Duluth Hwy 120 Duluth, GA. 30097
       Request: Approval of a Modification of Rezoning from PUD to PUD to allow
       for a hair salon as a by-right use in the overall PUD.

Prefixes observed across the corpus: Z (rezoning), SU/SUP (special use permit),
TA (text amendment), MZ (modification of rezoning), V (variance), A (annexation).

This is a REGEX parse of a template, not an LLM inference. Every field maps to a
literal span of the source document and carries its page and URL, so anything
here can be checked against the PDF. Where the template does not hold, the item
is skipped rather than guessed at.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
IN_CANDIDATES = ["duluth_meeting_text_ocr.jsonl", "duluth_meeting_text.jsonl"]
OUT = HERE / "duluth_cases.jsonl"

CASE_NO = r"([A-Z]{1,4})\s*(\d{4})\s*-\s*(\d{1,3})"

# Three formats, discovered by reading the actual documents:
#
#  Planning Commission agenda:
#      1. Case: TA2026-007, City of Duluth, 3167 Main Street Duluth, GA. 30096
#         Request: Text Amendment to Article 14 ...
#  Zoning Board of Appeals agenda -- NO COLON, address on its own line:
#      1. Case V2026-001, Jessica Pappe
#         4168 Suzanne Lane Duluth, GA. 30096
#         Request: Variance from ...
#  Council agenda packet -- the DECISION record, with vote:
#      1. ORDINANCE OF REZONING - CASE Z2026-004 - 3276 DELMA CT
#         ... Voted For: Council members Park, Thomas, ...
#
# Requiring the colon silently excluded every ZBA variance in the corpus.
# `rest` is an applicant plus a street address -- at most a couple of lines. It
# MUST be bounded. Left as an unbounded lazy `.+?`, it ran from a "Case:" in a
# council packet all the way to a "Request:" thousands of characters later,
# swallowing an entire staff report: one record came out at 777 KB with 67,553
# characters of narrative sitting in the `address` field.
RE_ITEM = re.compile(
    r"Case:?\s*" + CASE_NO + r"\s*,?\s*(?P<rest>[^\n]{0,140}(?:\n[^\n]{0,140}){0,2}?)"
    r"\s*Request:\s*(?P<request>.{0,1800}?)"
    r"(?=(?:\n\s*\d{1,2}\.\s)|(?:\n\s*[IVX]{1,5}\.\s)|(?:\n\s*Case:?\s*[A-Z]{1,4}\d{4})|\Z)",
    re.I | re.S)

# Decision headings inside council packets.
RE_DECISION = re.compile(
    r"(?P<action>ORDINANCE OF REZONING|RESOLUTION|ORDINANCE|SPECIAL USE PERMIT|VARIANCE|"
    r"TEXT AMENDMENT|ANNEXATION)[^\n]{0,60}?\bCASE\s+" + CASE_NO +
    r"\s*[-–—]?\s*(?P<caption>[^\n]{0,90})",
    re.I)

# "Voted For: Council members Park, Thomas, Doss ... Motion carried."
#
# The clerk is not consistent, and this is not cosmetic: across the OCR'd minutes
# the tally line appears 330 times as "Voted for/For" but 93 times as "Voting
# for", and the colon is sometimes absent. Matching only "Voted For:" silently
# dropped every decision written the other way -- the same trap as the
# "Case:" vs "CASE" guard that once skipped every council packet.
VOTE_FOR = r"Vot(?:ed|ing)\s+for"
VOTE_AGAINST = r"Vot(?:ed|ing)\s+against"
RE_VOTE = re.compile(
    VOTE_FOR + r"\s*:?\s*(?P<for>.{0,220}?)\s*"
    r"(?:" + VOTE_AGAINST + r"\s*:?\s*(?P<against>.{0,160}?)\s*)?"
    r"(?P<result>Motion\s+(?:carried|failed)[^\n.]{0,40})",
    re.I | re.S)

# OCR output labels each reconstructed page "[page N]". Useful for tracing a value
# back to a page; not something that should ever land inside an address or a
# request string.
RE_PAGE_MARKER = re.compile(r"\[page\s+\d+\]\s*")

# ---------------------------------------------------------------------------
# Minutes.
#
# Agendas say what was PROPOSED; minutes say what was DECIDED and by what vote.
# Neither RE_ITEM (the agenda template) nor RE_DECISION (packet headings) fits
# them: minutes narrate in prose, so 83 of 138 of them yielded nothing at all
# until now.
#
# The obvious approach -- attach each vote to the nearest case number above it --
# is wrong and quietly so. 558 of the 719 motion blocks in these minutes are
# adjournments, consent agendas and budget items with no case at all; "nearest
# preceding" would staple every one of them to whatever case was last mentioned
# and produce confident, invisible nonsense.
#
# The minutes bind the case themselves: "to approve ordinance O2026-31 for case
# A2026-001 to annex 2407 Main Street". So the case is read from INSIDE the motion
# span. 142 blocks name exactly one case, 2 name several (skipped as ambiguous),
# and the remaining 575 name none and are correctly not land-use votes.
#
# Prefixes are whitelisted because a bare pattern also matches ordinance and
# resolution numbers -- O2024-38, R2023-12 -- which are the majority of numbered
# things in a set of minutes. And the leading (?<![A-Z0-9]) guard matters for the
# same reason \b did in the filename dates: without it "PROPOSED 2024-38" yields
# a case called OSED2024-38.
CASE_STRICT = re.compile(
    r"(?<![A-Z0-9])(Z|MZ|SU|SUP|TA|V|A|AA)\s*(\d{4})\s*-\s*(\d{1,3})(?![0-9])")

# Deliberately loose between the motion opener and the tally. Requiring the exact
# "made by X, seconded by Y," shape looked tidier and silently matched only 84 of
# the 719 motion blocks present -- the clerk varies commas, line breaks and
# wording, and OCR adds its own. The case binding is the load-bearing part; who
# moved and who seconded are read from inside the span afterwards, and are allowed
# to be absent.
RE_MINUTES_MOTION = re.compile(
    # (?!A motion was made by) stops the span at the LAST motion opener before the
    # tally. Without it a single match swallowed every failed motion that preceded
    # the successful one -- in SU2025-001 a move to approve that died for lack of a
    # second, a move to deny that also died, and then the motion that actually
    # carried. Conflating them puts three different intentions in one record.
    r"(?P<motion>A\s+motion\s+was\s+made\s+by\b"
    r"(?:(?!A\s+motion\s+was\s+made\s+by).){0,700}?)"
    r"Vot(?:ed|ing)\s+for\s*:?\s*(?P<for>.{0,260}?)\s*"
    r"(?:Vot(?:ed|ing)\s+against\s*:?\s*(?P<against>.{0,200}?)\s*)?"
    r"(?P<result>Motion\s+(?:carried|failed)[^\n.]{0,40})",
    re.I | re.S)

# Names wrap across lines in the source ("seconded by Councilmember\nCummings"),
# so the capture must allow newlines and stop only at a comma. Excluding \n here
# matched 9 of 91 motions instead of nearly all of them; squash() puts the line
# back together afterwards.
# What the motion actually asked for. "Motion carried" alone is genuinely
# misleading: SU2025-001 carried a motion to POSTPONE, and a reader shown only
# "Motion carried" against a special use permit will read it as approved. The
# outcome is meaningless without the verb it applied to.
# Both "to approve ..." and the gerund "approving ordinance O2025-33 for Case
# Z2025-001" occur; matching only the infinitive left the action blank on records
# that plainly state it.
RE_MOTION_ACTION = re.compile(
    r"\b(?:to\s+)?(?P<action>approv(?:e|ing)|den(?:y|ies|ied|ying)|postpon(?:e|ing)|"
    r"tabl(?:e|ing)|continu(?:e|ing)|defer(?:ring)?|withdraw(?:ing)?|remand(?:ing)?|"
    r"adopt(?:ing)?|accept(?:ing)?|reject(?:ing)?)\b", re.I)

# approving -> approve, denying -> deny, so the field groups cleanly
ACTION_CANON = {
    "approving": "approve", "denies": "deny", "denied": "deny", "denying": "deny",
    "postponing": "postpone", "tabling": "table", "continuing": "continue",
    "deferring": "defer", "withdrawing": "withdraw", "remanding": "remand",
    "adopting": "adopt", "accepting": "accept", "rejecting": "reject",
}

RE_MOVER = re.compile(
    r"motion\s+was\s+made\s+by\s+(?P<mover>[^,]{2,60}?)\s*,\s*"
    r"(?:and\s+)?seconded\s+by\s+(?P<seconder>[^,]{2,60}?)\s*[,.]", re.I | re.S)


def motion_case(span: str) -> str | None:
    """The single case a motion is about, or None if it names none or several."""
    found = {f"{a.upper()}{y}-{s.zfill(3)}" for a, y, s in CASE_STRICT.findall(span)}
    return found.pop() if len(found) == 1 else None


TYPE_BY_PREFIX = {
    "Z": "rezoning",
    "MZ": "modification_of_rezoning",
    "SU": "special_use_permit",
    "SUP": "special_use_permit",
    "TA": "text_amendment",
    "V": "variance",
    "A": "annexation",
    "AA": "annexation",       # present in the corpus, previously typed "other"
}

# The zoning-change clause inside the Request text, e.g.
# "Rezoning from R-100 (Single Family Residential) to C-2 (General Business)".
RE_ZONE_CHANGE = re.compile(
    r"from\s+([A-Z][A-Z0-9\-]{0,9})\s*(?:\([^)]*\))?\s*to\s+([A-Z][A-Z0-9\-]{0,9})",
    re.I)


def squash(s: str) -> str:
    # Strip OCR page labels before collapsing whitespace: they are provenance for
    # the text as a whole, not content of any field that happens to span a page.
    s = RE_PAGE_MARKER.sub(" ", s or "")
    return re.sub(r"\s+", " ", s).strip(" ,;–-")


def split_rest(rest: str) -> tuple[str, str]:
    """'<applicant>, <address>' -- address is the tail starting at the street number."""
    rest = squash(rest)
    m = re.search(r",\s*(\d{2,6}\s+[A-Za-z].*)$", rest)
    if m:
        return squash(rest[:m.start()]), squash(m.group(1))
    parts = [p.strip() for p in rest.split(",")]
    if len(parts) >= 2:
        return squash(parts[0]), squash(", ".join(parts[1:]))
    return rest, ""


def main() -> int:
    src = next((HERE / f for f in IN_CANDIDATES if (HERE / f).exists()), None)
    if src is None:
        print("no input corpus found")
        return 1
    print(f"source: {src.name}")

    rows = [json.loads(l) for l in src.open()]
    out, seen = [], set()
    # True  = the motion mentioned several cases and was skipped as ambiguous
    # False = it mentioned none, i.e. was not a land-use vote at all
    ambiguous = {True: 0, False: 0}

    for r in rows:
        text = (r.get("text") or "") + "\n" + (r.get("text_ocr") or "")
        # Must be case-insensitive and colon-free: agendas write "Case:" but the
        # council packets write "CASE Z2026-004" in an all-caps heading. Guarding
        # on the literal "Case:" skipped every packet -- i.e. every decision.
        if not re.search(r"\bcase\b", text, re.I):
            continue
        # RE_ITEM is the AGENDA template. Packets are narrative staff reports with
        # no numbered-item structure to terminate a match, so they are handled
        # only by RE_DECISION below.
        for m in (RE_ITEM.finditer(text) if r.get("doc_type") != "packet" else []):
            prefix, yr, seq = m.group(1).upper(), m.group(2), m.group(3)
            case_no = f"{prefix}{yr}-{seq.zfill(3)}"
            applicant, address = split_rest(m.group("rest"))
            request = squash(m.group("request"))[:2000]
            if not request or len(request) < 10:
                continue

            zc = RE_ZONE_CHANGE.search(request)
            key = (case_no, r["body_slug"], r.get("meeting_date_final"), r["doc_type"])
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "case_number": case_no,
                "case_prefix": prefix,
                "case_year": int(yr),
                "case_type": TYPE_BY_PREFIX.get(prefix, "other"),
                "applicant": applicant,
                "address": address,
                "request": request,
                "zone_from": zc.group(1).upper() if zc else None,
                "zone_to": zc.group(2).upper() if zc else None,
                "body_slug": r["body_slug"],
                "body_name": r["body_name"],
                "doc_type": r["doc_type"],
                "meeting_date": r.get("meeting_date_final"),
                "source_url": r["url"],
                "source_filename": r["filename"],
                "text_source": r.get("text_source", "embedded"),
                "extraction": "regex_template",
                "record_kind": "request",
            })

        # Minutes: decisions, bound to the case the motion itself names.
        if r.get("doc_type") == "minutes":
            for m in RE_MINUTES_MOTION.finditer(text):
                case_no = motion_case(m.group("motion"))
                if not case_no:
                    ambiguous[bool(CASE_STRICT.search(m.group("motion")))] += 1
                    continue
                prefix = re.match(r"[A-Z]+", case_no).group(0)
                mv = RE_MOVER.search(m.group("motion"))
                act = RE_MOTION_ACTION.search(m.group("motion"))
                key = (case_no, r["body_slug"], r.get("meeting_date_final"), "minutes")
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "case_number": case_no,
                    "case_prefix": prefix,
                    "case_year": int(case_no[len(prefix):len(prefix) + 4]),
                    "case_type": TYPE_BY_PREFIX.get(prefix, "other"),
                    "applicant": None,
                    "address": None,
                    "request": squash(m.group("motion")[mv.end():] if mv
                                       else m.group("motion"))[:2000] or None,
                    "zone_from": None, "zone_to": None,
                    "moved_by": squash(mv.group("mover")) if mv else None,
                    "seconded_by": squash(mv.group("seconder")) if mv else None,
                    "voted_for": squash(m.group("for")) or None,
                    "voted_against": squash(m.group("against")) if m.group("against") else None,
                    "outcome": squash(m.group("result")) or None,
                    "motion_action": (lambda v: ACTION_CANON.get(v, v))(
                        act.group("action").lower()) if act else None,
                    "body_slug": r["body_slug"],
                    "body_name": r["body_name"],
                    "doc_type": r["doc_type"],
                    "meeting_date": r.get("meeting_date_final"),
                    "source_url": r["url"],
                    "source_filename": r["filename"],
                    "text_source": r.get("text_source", "embedded"),
                    "extraction": "minutes_motion",
                    "record_kind": "decision",
                })

        # Council packets carry the DECISION -- the agenda says what was asked,
        # only the packet says what passed and who voted for it.
        if r.get("doc_type") == "packet":
            for m in RE_DECISION.finditer(text):
                # group 1 is the action verb, so the case-number groups are 2-4.
                prefix, yr, seq = m.group(2).upper(), m.group(3), m.group(4)
                case_no = f"{prefix}{yr}-{seq.zfill(3)}"
                key = (case_no, r["body_slug"], r.get("meeting_date_final"), "decision")
                if key in seen:
                    continue
                seen.add(key)
                window = text[m.end(): m.end() + 6000]
                v = RE_VOTE.search(window)
                out.append({
                    "case_number": case_no,
                    "case_prefix": prefix,
                    "case_year": int(yr),
                    "case_type": TYPE_BY_PREFIX.get(prefix, "other"),
                    "applicant": None,
                    "address": squash(m.group("caption")),
                    "request": squash(m.group("action")),
                    "zone_from": None, "zone_to": None,
                    "voted_for": squash(v.group("for")) if v else None,
                    "voted_against": squash(v.group("against")) if v and v.group("against") else None,
                    "outcome": squash(v.group("result")) if v else None,
                    "body_slug": r["body_slug"],
                    "body_name": r["body_name"],
                    "doc_type": r["doc_type"],
                    "meeting_date": r.get("meeting_date_final"),
                    "source_url": r["url"],
                    "source_filename": r["filename"],
                    "text_source": r.get("text_source", "embedded"),
                    "extraction": "regex_template",
                    "record_kind": "decision",
                })

    with OUT.open("w", encoding="utf-8") as fh:
        for o in out:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")

    import collections
    mins_rows = [x for x in out if x.get("extraction") == "minutes_motion"]
    print(f"minutes decisions : {len(mins_rows)} "
          f"({ambiguous[True]} skipped as ambiguous, "
          f"{ambiguous[False]} motions with no case = not land-use votes)")
    print(f"case items parsed : {len(out)}")
    print(f"distinct cases    : {len({o['case_number'] for o in out})}")
    print("by type           :", dict(collections.Counter(o["case_type"] for o in out)))
    print("by body           :", dict(collections.Counter(o["body_slug"] for o in out)))
    print("with zone change  :", sum(1 for o in out if o["zone_from"]))
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
