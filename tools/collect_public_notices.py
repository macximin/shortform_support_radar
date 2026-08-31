#!/usr/bin/env python3
"""Collect a bounded, public, no-auth announcement snapshot.

The collector deliberately stores neither page bodies nor application data. It only
keeps a receipt for the fetched public page and candidate links whose visible text
matches the discovery vocabulary. A match is not an eligibility or funding claim.
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
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

KEYWORDS = (
    "인공지능", "ai", "생성형", "방송영상", "드라마", "숏드라마", "숏폼",
    "웹툰", "webtoon", "ip", "지식재산", "콘텐츠", "해외진출", "수출",
    "제작지원", "제작 지원",
)
NOTICE_SIGNALS = ("공고", "모집", "지원", "사업", "참가", "쇼케이스")
MAX_RESPONSE_BYTES = 2_000_000
USER_AGENT = "shortform-support-radar/0.1 (public-candidate-research; no-auth)"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_registry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_public_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def validate_registry(registry: dict) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    if registry.get("schema") != "shortform-support-radar-source-registry/v1":
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
    return errors


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((normalize_text(" ".join(self._parts)), self._href))
            self._href = None
            self._parts = []


def extract_candidates(page: str, base_url: str, keywords: Iterable[str] = KEYWORDS) -> list[dict[str, str]]:
    parser = LinkCollector()
    parser.feed(page)
    lowered_keywords = tuple(word.lower() for word in keywords)
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for text, href in parser.links:
        normalized_lower = text.lower()
        if (
            len(text) < 4
            or not any(keyword in normalized_lower for keyword in lowered_keywords)
            or not any(signal in text for signal in NOTICE_SIGNALS)
        ):
            continue
        url = urljoin(base_url, href)
        if not is_public_https_url(url):
            continue
        key = (text, url)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({"title": text[:500], "url": url})
    return candidates[:100]


def fetch_public_page(url: str) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=15) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError(f"response exceeded {MAX_RESPONSE_BYTES} byte limit")
        return response.status, response.geturl(), body


def collect(source: dict) -> dict:
    observed_at = utc_now()
    status, final_url, body = fetch_public_page(source["url"])
    charset = "utf-8"
    page = body.decode(charset, errors="replace")
    return {
        "schema": "shortform-support-radar-public-receipt/v1",
        "candidate_only": True,
        "not_an_eligibility_decision": True,
        "source": {key: source[key] for key in ("id", "publisher", "category", "authority", "url")},
        "observed_at": observed_at,
        "http_status": status,
        "final_url": final_url,
        "page_sha256": hashlib.sha256(body).hexdigest(),
        "page_bytes": len(body),
        "keyword_set": list(KEYWORDS),
        "candidate_links": extract_candidates(page, final_url),
    }


def write_receipt(receipt: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{receipt['source']['id']}.json"
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "collect"))
    parser.add_argument("--registry", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--source", help="one source id; required for collect")
    parser.add_argument("--out", type=Path, default=Path("evidence"))
    args = parser.parse_args()
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
    source = next((item for item in registry["sources"] if item["id"] == args.source), None)
    if source is None:
        parser.error(f"unknown source: {args.source}")
    try:
        receipt = collect(source)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        print(json.dumps({"status": "error", "source": args.source, "error": str(error)}, ensure_ascii=False))
        return 1
    path = write_receipt(receipt, args.out)
    print(json.dumps({"status": "ok", "receipt": str(path), "candidate_count": len(receipt["candidate_links"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
