#!/usr/bin/env python3
"""Collect a bounded, public, no-auth announcement snapshot.

The collector deliberately stores neither page bodies nor application data. It only
keeps a receipt for the fetched public page and candidate rows whose visible text
matches the discovery vocabulary. A match is not an eligibility or funding claim.

Rows are read as list rows, not as bare links, so a candidate carries the notice
period and status the board already publishes. A source may declare a server-side
search so the radar queries the board's own index instead of scraping page one of
a date-sorted list.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

KEYWORDS = (
    "인공지능", "ai", "생성형", "방송영상", "드라마", "숏드라마", "숏폼",
    "웹툰", "webtoon", "ip", "지식재산", "콘텐츠", "해외진출", "수출",
    "제작지원", "제작 지원",
)
NOTICE_SIGNALS = ("공고", "모집", "지원", "사업", "참가", "쇼케이스", "공모")
MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = "shortform-support-radar/0.2 (public-candidate-research; no-auth)"
REQUEST_INTERVAL_SECONDS = 1.0
RECEIPT_SCHEMA = "shortform-support-radar-public-receipt/v2"
REGISTRY_SCHEMA = "shortform-support-radar-source-registry/v1"

ROW_TAGS = {"tr", "li"}
BADGE_PREFIXES = ("새글", "공지", "신규", "NEW", "new")
STATUS_LABELS = ("모집중", "접수중", "진행중", "접수예정", "모집예정", "마감", "종료", "상시")

_DATE = r"(\d{2,4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*\.?"
DATE_RANGE_RE = re.compile(_DATE + r"\s*~\s*" + _DATE)
ANY_DATE_RE = re.compile(_DATE)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def today_kst() -> dt.date:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).date()


def load_registry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_public_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def validate_registry(registry: dict) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    if registry.get("schema") != REGISTRY_SCHEMA:
        errors.append("unsupported or missing registry schema")
    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
        return errors
    for source in sources:
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append("source has no id")
            continue
        if source_id in seen:
            errors.append(f"duplicate source id: {source_id}")
        seen.add(source_id)
        if not is_public_https_url(str(source.get("url", ""))):
            errors.append(f"source URL must be public HTTPS without credentials: {source_id}")
        if source.get("enabled") is not True:
            errors.append(f"source must explicitly set enabled=true: {source_id}")
        errors.extend(validate_search(source_id, source.get("search")))
    return errors


def validate_search(source_id: str, search: object) -> list[str]:
    if search is None:
        return []
    if not isinstance(search, dict):
        return [f"search must be an object: {source_id}"]
    errors: list[str] = []
    if not isinstance(search.get("param"), str) or not search.get("param"):
        errors.append(f"search.param must be a non-empty string: {source_id}")
    queries = search.get("queries")
    if not isinstance(queries, list) or not queries or not all(isinstance(q, str) and q for q in queries):
        errors.append(f"search.queries must be a non-empty list of strings: {source_id}")
    extra = search.get("extraParams", {})
    if not isinstance(extra, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in extra.items()):
        errors.append(f"search.extraParams must be a string map: {source_id}")
    return errors


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def strip_badges(value: str) -> str:
    text = value
    changed = True
    while changed:
        changed = False
        for badge in BADGE_PREFIXES:
            if text.startswith(badge):
                text = text[len(badge):].lstrip()
                changed = True
    return text


def with_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    merged = dict(parse_qsl(parts.query, keep_blank_values=True))
    merged.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment))


def normalize_date(year: str, month: str, day: str) -> str | None:
    y, m, d = int(year), int(month), int(day)
    if y < 100:
        y += 2000
    try:
        return dt.date(y, m, d).isoformat()
    except ValueError:
        return None


def extract_period(text: str) -> tuple[str | None, str | None]:
    """Return (start, end) ISO dates for the first date range found in the row."""
    match = DATE_RANGE_RE.search(text)
    if not match:
        return None, None
    start = normalize_date(*match.group(1, 2, 3))
    end = normalize_date(*match.group(4, 5, 6))
    return start, end


def extract_status(text: str) -> str | None:
    for label in STATUS_LABELS:
        if label in text:
            return label
    return None


class RowCollector(HTMLParser):
    """Collect list rows with their anchors and visible cell text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._stack: list[dict] = []
        self._anchor: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {key.lower(): (value or "") for key, value in attrs}
        if tag in ROW_TAGS:
            self._stack.append({"texts": [], "anchors": []})
        if tag in {"td", "th"} and attributes.get("title"):
            self._push_text(attributes["title"])
        if tag == "a":
            self._anchor = {"href": attributes.get("href"), "title": attributes.get("title", ""), "parts": []}

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor["parts"].append(data)
        self._push_text(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self._anchor is not None:
            if self._stack:
                self._stack[-1]["anchors"].append(
                    {
                        "text": strip_badges(normalize_text(" ".join(self._anchor["parts"]))),
                        "title": strip_badges(normalize_text(self._anchor["title"])),
                        "href": self._anchor["href"],
                    }
                )
            self._anchor = None
        if tag in ROW_TAGS and self._stack:
            self.rows.append(self._stack.pop())

    def _push_text(self, data: str) -> None:
        for row in self._stack:
            row["texts"].append(data)


def best_anchor(row: dict) -> dict | None:
    ranked = [a for a in row["anchors"] if a.get("href")]
    if not ranked:
        return None
    return max(ranked, key=lambda a: len(a["text"] or a["title"]))


def extract_candidates(
    page: str,
    base_url: str,
    keywords: Iterable[str] = KEYWORDS,
    observed_on: dt.date | None = None,
) -> list[dict]:
    parser = RowCollector()
    parser.feed(page)
    observed_on = observed_on or today_kst()
    lowered_keywords = tuple(word.lower() for word in keywords)
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in parser.rows:
        anchor = best_anchor(row)
        if anchor is None:
            continue
        title = anchor["text"] or anchor["title"]
        if len(title) < 4:
            continue
        lowered = title.lower()
        if not any(keyword in lowered for keyword in lowered_keywords):
            continue
        if not any(signal in title for signal in NOTICE_SIGNALS):
            continue
        url = urljoin(base_url, anchor["href"])
        if not is_public_https_url(url):
            continue
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        row_text = normalize_text(" ".join(row["texts"]))
        status = extract_status(row_text)
        # A board row always publishes a date or a recruitment state. A bare link
        # with neither is site navigation (related agencies, footer menus), not a notice.
        if not ANY_DATE_RE.search(row_text) and status is None:
            continue
        start, end = extract_period(row_text)
        candidate = {
            "title": title[:500],
            "url": url,
            "period_start": start,
            "period_end": end,
            "status_label": status,
        }
        candidate["open_on_observation"] = None if end is None else end >= observed_on.isoformat()
        candidates.append(candidate)
    return candidates[:100]


def decode_body(body: bytes, content_type: str | None) -> str:
    charset = "utf-8"
    if content_type:
        match = re.search(r"charset=([\w\-]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1)
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch_decoded(url: str) -> tuple[int, str, bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=20) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError(f"response exceeded {MAX_RESPONSE_BYTES} byte limit")
        return response.status, response.geturl(), body, decode_body(body, response.headers.get("Content-Type"))


def build_requests(source: dict) -> list[tuple[str | None, str]]:
    """Return (query, url) pairs. A search source queries the board's own index."""
    search = source.get("search")
    if not search:
        return [(None, source["url"])]
    extra = search.get("extraParams", {})
    param = search["param"]
    return [(query, with_query(source["url"], {**extra, param: query})) for query in search["queries"]]


def collect(source: dict) -> dict:
    observed_at = utc_now()
    observed_on = today_kst()
    fetches: list[dict] = []
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for index, (query, url) in enumerate(build_requests(source)):
        if index:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        status, final_url, body, page = fetch_decoded(url)
        fetches.append(
            {
                "query": query,
                "requested_url": url,
                "final_url": final_url,
                "http_status": status,
                "page_sha256": hashlib.sha256(body).hexdigest(),
                "page_bytes": len(body),
            }
        )
        for candidate in extract_candidates(page, final_url, observed_on=observed_on):
            key = (candidate["title"], candidate["url"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append({**candidate, "matched_query": query})
    candidates.sort(key=lambda c: (c["period_end"] is None, c["period_end"] or "", c["title"]))
    return {
        "schema": RECEIPT_SCHEMA,
        "candidate_only": True,
        "not_an_eligibility_decision": True,
        "source": {key: source[key] for key in ("id", "publisher", "category", "authority", "url")},
        "observed_at": observed_at,
        "observed_on_kst": observed_on.isoformat(),
        "search_mode": "server_side_query" if source.get("search") else "list_page",
        "fetches": fetches,
        "keyword_set": list(KEYWORDS),
        "candidate_count": len(candidates),
        "open_candidate_count": sum(1 for c in candidates if c["open_on_observation"] is True),
        "candidate_links": candidates,
    }


def write_receipt(receipt: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{receipt['source']['id']}.json"
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def candidate_index(receipt: dict) -> dict[tuple[str, str], dict]:
    return {(c["title"], c["url"]): c for c in receipt.get("candidate_links", [])}


def diff_receipts(previous: dict, current: dict) -> dict:
    before = candidate_index(previous)
    after = candidate_index(current)
    appeared = [after[key] for key in after.keys() - before.keys()]
    disappeared = [before[key] for key in before.keys() - after.keys()]
    return {
        "source_id": current["source"]["id"],
        "previous_observed_at": previous.get("observed_at"),
        "current_observed_at": current.get("observed_at"),
        "appeared": sorted(appeared, key=lambda c: c["title"]),
        "disappeared": sorted(disappeared, key=lambda c: c["title"]),
        "unchanged_count": len(after.keys() & before.keys()),
    }


def run_diff(previous_dir: Path, current_dir: Path) -> dict:
    results: list[dict] = []
    for current_path in sorted(current_dir.glob("*.json")):
        previous_path = previous_dir / current_path.name
        current = json.loads(current_path.read_text(encoding="utf-8"))
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
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        results.append(diff_receipts(previous, current))
    return {
        "schema": "shortform-support-radar-public-diff/v1",
        "candidate_only": True,
        "previous_dir": str(previous_dir),
        "current_dir": str(current_dir),
        "generated_at": utc_now(),
        "sources": results,
        "appeared_total": sum(len(r["appeared"]) for r in results),
        "disappeared_total": sum(len(r["disappeared"]) for r in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "collect", "diff"))
    parser.add_argument("--registry", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--source", help="one source id, or 'all'; required for collect")
    parser.add_argument("--out", type=Path, default=Path("evidence"))
    parser.add_argument("--previous", type=Path, help="previous receipt directory; required for diff")
    parser.add_argument("--current", type=Path, help="current receipt directory; required for diff")
    args = parser.parse_args()

    if args.command == "diff":
        if not args.previous or not args.current:
            parser.error("--previous and --current are required for diff")
        report = run_diff(args.previous, args.current)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    registry = load_registry(args.registry)
    errors = validate_registry(registry)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False))
        return 2
    if args.command == "validate":
        print(json.dumps({"status": "valid", "source_count": len(registry["sources"])}, ensure_ascii=False))
        return 0
    if not args.source:
        parser.error("--source is required for collect")

    if args.source == "all":
        selected = list(registry["sources"])
    else:
        selected = [item for item in registry["sources"] if item["id"] == args.source]
        if not selected:
            parser.error(f"unknown source: {args.source}")

    exit_code = 0
    for source in selected:
        try:
            receipt = collect(source)
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            print(json.dumps({"status": "error", "source": source["id"], "error": str(error)}, ensure_ascii=False))
            exit_code = 1
            continue
        path = write_receipt(receipt, args.out)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "source": source["id"],
                    "receipt": str(path),
                    "candidate_count": receipt["candidate_count"],
                    "open_candidate_count": receipt["open_candidate_count"],
                },
                ensure_ascii=False,
            )
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
