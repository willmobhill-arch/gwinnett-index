"""
The adapter contract.

Seventeen municipalities cannot be seventeen hand-written scrapers. Vendors
consolidate hard -- Municode, ArcGIS REST, CivicPlus, CivicClerk, BS&A, Accela -- so
roughly six adapters cover most of the county and adding a city becomes a config file.
The health metric in CLAUDE.md is the point of this module: **if a new city needs new
code rather than a new config, the adapter layer is leaking.**

This file was written against ONE adapter (`pdf_code`), on purpose. The build plan has
described a six-vendor abstraction since day one and nothing was ever built to it, and
a contract invented for five sources that do not exist yet would be shaped by
guesswork. So the stages below are the stages `pdf_code` actually has, and the second
adapter is expected to bend them. Bending them then is cheap; unbuilding a speculative
framework is not.

THE STAGES, and why each is separate:

  discover(config)  -> what the source says exists
  fetch(config)     -> bytes on disk, unchanged from the source
  parse(config)     -> source bytes to records, no database vocabulary
  normalize(config) -> records to the shape a loader takes, with provenance
  upsert(config)    -> hand the loader a URL; Postgres pulls it

`discover` is not folded into `parse` because counting what the source announces and
comparing it to what came out is the check that catches a whole class of silent loss:
the UDC announces twenty tables and the old extractor produced eighteen, which looked
like a smaller result and was a wrong one. Any adapter that cannot say what the source
claims to contain will lose things the same way.

`upsert` hands over a URL rather than rows because ingestion runs INSIDE Postgres, via
the http extension, against the repo's own raw files. That began as a sandbox
workaround and stayed because it is better: no worker, no credentials in transit, and
the exact bytes that were loaded stay in git.

Nothing here fetches or writes on import. `python3 -m ingest.adapters.base` lists what
is registered.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

REPO_RAW = 'https://raw.githubusercontent.com/willmobhill-arch/gwinnett-index'


@dataclass
class Artifact:
    """One file an adapter produced, and where it came from.

    `source_url` and `retrieved` are not optional anywhere in this project: a record
    without provenance cannot be re-checked, and a legal-reference index whose claims
    cannot be re-checked is not one.
    """
    path: str
    source_url: str
    retrieved: str
    sha256: str | None = None
    note: str | None = None


@dataclass
class LoadPlan:
    """How Postgres should pull an adapter's output.

    `sql` is the call, not the data. The published JSONL is fetched by the database
    itself from `url`.
    """
    sql: str
    url: str
    expect: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f'SELECT * FROM {self.sql};'


class Adapter(Protocol):
    """What every source adapter implements.

    Each stage takes the same config dict -- a city's entry in a config file -- so
    adding a jurisdiction is data, not code. A stage that cannot be implemented for a
    given source should raise NotImplementedError rather than return empty: an empty
    result is indistinguishable from success, and this project has been bitten by that
    often enough to have a rule about it. A queue of zero is a bug, not a result.
    """

    name: str

    def discover(self, config: dict) -> list[dict]:
        """What the source says it contains, before anything is parsed."""

    def fetch(self, config: dict) -> list[Artifact]:
        """Source bytes on disk, unmodified, with provenance."""

    def parse(self, config: dict) -> list[dict]:
        """Source bytes to records, in the source's own vocabulary."""

    def normalize(self, config: dict) -> list[dict]:
        """Records to the shape a loader accepts, provenance attached."""

    def upsert(self, config: dict) -> LoadPlan:
        """The in-database call that loads this adapter's published output."""


_REGISTRY: dict[str, Callable[[], Adapter]] = {}


def register(name: str) -> Callable[[Callable[[], Adapter]], Callable[[], Adapter]]:
    """Register an adapter factory under a vendor name."""
    def wrap(factory: Callable[[], Adapter]) -> Callable[[], Adapter]:
        if name in _REGISTRY:
            raise ValueError(f'adapter {name!r} is already registered')
        _REGISTRY[name] = factory
        return factory
    return wrap


def get(name: str) -> Adapter:
    if name not in _REGISTRY:
        raise KeyError(f'no adapter {name!r}; registered: {sorted(_REGISTRY)}')
    return _REGISTRY[name]()


def registered() -> list[str]:
    return sorted(_REGISTRY)


def raw_url(path: str, ref: str | None = None) -> str:
    """Raw URL for a repo file, for the database to fetch.

    The ref defaults to main because that is what a scheduled load should read. Pass
    GWINDEX_REF (or `ref`) to load from a branch before it merges -- which is a real
    workflow here, not a convenience: the load has to be proved before the branch is.
    """
    ref = ref or os.environ.get('GWINDEX_REF', 'main')
    return f'{REPO_RAW}/{ref}/{path.lstrip("/")}'


if __name__ == '__main__':
    # `python3 -m ingest.adapters.base` runs this file TWICE under two names: once as
    # ingest.adapters.base when the package __init__ imports it, and again as
    # __main__. Each copy gets its own _REGISTRY, and adapters register into the
    # package's -- so reading the one in __main__ reports an empty registry and no
    # error. Read the package's copy explicitly.
    import ingest.adapters.base as _pkg
    from ingest.adapters import pdf_code  # noqa: F401  (registers itself on import)
    for n in _pkg.registered():
        a = _pkg.get(n)
        first = a.__doc__.strip().splitlines()[0] if a.__doc__ else ''
        print(f'{n:12} {first}')
