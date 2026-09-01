"""Board adapter: read HTML list rows into notice candidates.

This is the only module shaped by how the boards render. It reads rows rather
than bare links, because the period and recruitment state a radar needs live in
sibling cells, not in the anchor.
"""

from __future__ import annotations

from html.parser import HTMLParser

from .notice import (
    MIN_TITLE_LENGTH,
    Candidate,
    NoticePeriod,
    carries_notice_metadata,
    find_status_label,
    looks_like_notice_title,
    normalize_text,
    strip_badges,
)
from .policy import PublicUrl

ROW_TAGS = {"tr", "li"}
MAX_CANDIDATES_PER_PAGE = 100


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


def _best_anchor(row: dict) -> dict | None:
    linked = [anchor for anchor in row["anchors"] if anchor.get("href")]
    if not linked:
        return None
    return max(linked, key=lambda anchor: len(anchor["text"] or anchor["title"]))


def read_candidates(
    page: str,
    base_url: PublicUrl,
    matched_query: str | None = None,
    all_rows_in_scope: bool = False,
    search_param_names: frozenset[str] = frozenset(),
) -> list[Candidate]:
    """Read notice rows.

    `all_rows_in_scope` is for a board whose every row is already a notice this
    radar wants - a content agency's own programme list. Applying the discovery
    vocabulary there subtracts rather than filters: WelCon's event board lost
    콘텐츠IP 마켓 and ATF 애니메이션 to it.
    """
    parser = RowCollector()
    parser.feed(page)
    candidates: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for row in parser.rows:
        anchor = _best_anchor(row)
        if anchor is None:
            continue
        title = anchor["text"] or anchor["title"]
        if all_rows_in_scope:
            if len(title) < MIN_TITLE_LENGTH:
                continue
        elif not looks_like_notice_title(title):
            continue
        url = base_url.join(anchor["href"])
        if url is None:
            continue
        row_text = normalize_text(" ".join(row["texts"]))
        if not carries_notice_metadata(row_text):
            continue
        identity = url.without_params_named(search_param_names) if search_param_names else url
        if matched_query:
            identity = identity.without_params_valued({matched_query})
        candidate = Candidate(
            title=title[:500],
            url=url,
            period=NoticePeriod.parse(row_text),
            status_label=find_status_label(row_text),
            matched_query=matched_query,
            identity_url=identity,
        )
        if candidate.key() in seen:
            continue
        seen.add(candidate.key())
        candidates.append(candidate)
    return candidates[:MAX_CANDIDATES_PER_PAGE]
