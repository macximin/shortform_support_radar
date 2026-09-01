"""Receipts: the dated, immutable record of one collection run, and run-over-run diff.

A receipt keeps the source, the per-fetch page hashes, and the candidate rows. It
never keeps HTML, session state, credentials, applicant data, or application
documents.

A page hash cannot answer "what changed": view counters and session tokens move it
on every fetch. Change is a comparison of candidate sets, which is what diff does.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from .notice import Candidate
from .policy import policy_stamp
from .registry import Source

RECEIPT_SCHEMA = "shortform-support-radar-public-receipt/v3"
DIFF_SCHEMA = "shortform-support-radar-public-diff/v1"


@dataclass(frozen=True)
class Fetch:
    """One public page read, recorded as a hash rather than a body."""

    query: str | None
    requested_url: str
    final_url: str
    http_status: int
    page_sha256: str
    page_bytes: int

    def to_json(self) -> dict:
        return {
            "query": self.query,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "page_sha256": self.page_sha256,
            "page_bytes": self.page_bytes,
        }


@dataclass(frozen=True)
class Receipt:
    source: Source
    observed_at: str
    observed_on: dt.date
    fetches: tuple[Fetch, ...]
    candidates: tuple[Candidate, ...]
    keyword_set: tuple[str, ...]

    @property
    def open_candidate_count(self) -> int:
        return sum(1 for c in self.candidates if c.period.is_open_on(self.observed_on) is True)

    def to_json(self) -> dict:
        return {
            "schema": RECEIPT_SCHEMA,
            **policy_stamp(),
            "source": self.source.to_json(),
            "observed_at": self.observed_at,
            "observed_on_kst": self.observed_on.isoformat(),
            "search_mode": self.source.search_mode,
            "fetches": [f.to_json() for f in self.fetches],
            "keyword_set": list(self.keyword_set),
            "candidate_count": len(self.candidates),
            "open_candidate_count": self.open_candidate_count,
            "candidate_links": [c.to_json(self.observed_on) for c in self.candidates],
        }

    def write(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{self.source.id}.json"
        target.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target


def _candidate_index(document: dict) -> dict[tuple[str, str], dict]:
    return {(c["title"], c["url"]): c for c in document.get("candidate_links", [])}


def diff_documents(previous: dict, current: dict) -> dict:
    before = _candidate_index(previous)
    after = _candidate_index(current)
    return {
        "source_id": current["source"]["id"],
        "previous_observed_at": previous.get("observed_at"),
        "current_observed_at": current.get("observed_at"),
        "appeared": sorted((after[k] for k in after.keys() - before.keys()), key=lambda c: c["title"]),
        "disappeared": sorted((before[k] for k in before.keys() - after.keys()), key=lambda c: c["title"]),
        "unchanged_count": len(after.keys() & before.keys()),
    }


def diff_directories(previous_dir: Path, current_dir: Path, generated_at: str) -> dict:
    results: list[dict] = []
    for current_path in sorted(current_dir.glob("*.json")):
        current = json.loads(current_path.read_text(encoding="utf-8"))
        previous_path = previous_dir / current_path.name
        if not previous_path.exists():
            results.append(
                {
                    "source_id": current["source"]["id"],
                    "previous_observed_at": None,
                    "current_observed_at": current.get("observed_at"),
                    "appeared": current.get("candidate_links", []),
                    "disappeared": [],
                    "unchanged_count": 0,
                }
            )
            continue
        results.append(diff_documents(json.loads(previous_path.read_text(encoding="utf-8")), current))
    return {
        "schema": DIFF_SCHEMA,
        **{"candidate_only": policy_stamp()["candidate_only"]},
        "previous_dir": str(previous_dir),
        "current_dir": str(current_dir),
        "generated_at": generated_at,
        "sources": results,
        "appeared_total": sum(len(r["appeared"]) for r in results),
        "disappeared_total": sum(len(r["disappeared"]) for r in results),
    }
