"""The source registry: which public boards this radar is allowed to read.

A board that publishes thousands of notices is queried through its own search
index rather than scraped page by page, so a Source may carry a SearchPlan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .policy import PublicUrl

REGISTRY_SCHEMA = "shortform-support-radar-source-registry/v1"


@dataclass(frozen=True)
class SearchPlan:
    """Queries issued against a board's own search index."""

    param: str
    queries: tuple[str, ...]
    extra_params: dict[str, str] = field(default_factory=dict)

    def urls_for(self, base: PublicUrl) -> list[tuple[str, PublicUrl]]:
        return [(query, base.with_query({**self.extra_params, self.param: query})) for query in self.queries]


@dataclass(frozen=True)
class Source:
    """One registered public board."""

    id: str
    url: PublicUrl
    publisher: str | None = None
    category: str | None = None
    authority: str | None = None
    search: SearchPlan | None = None

    @property
    def search_mode(self) -> str:
        return "server_side_query" if self.search else "list_page"

    def requests(self) -> list[tuple[str | None, PublicUrl]]:
        """Return (query, url) pairs to fetch for this source."""
        if self.search is None:
            return [(None, self.url)]
        return list(self.search.urls_for(self.url))

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "publisher": self.publisher,
            "category": self.category,
            "authority": self.authority,
            "url": str(self.url),
        }


def _read_search(source_id: str, raw: object, errors: list[str]) -> SearchPlan | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"search must be an object: {source_id}")
        return None
    raw_param = raw.get("param")
    raw_queries = raw.get("queries")
    raw_extra = raw.get("extraParams", {})

    param: str | None = raw_param if isinstance(raw_param, str) and raw_param else None
    if param is None:
        errors.append(f"search.param must be a non-empty string: {source_id}")

    queries: tuple[str, ...] | None = None
    if isinstance(raw_queries, list) and raw_queries and all(isinstance(q, str) and q for q in raw_queries):
        queries = tuple(raw_queries)
    else:
        errors.append(f"search.queries must be a non-empty list of strings: {source_id}")

    extra: dict[str, str] | None = None
    if isinstance(raw_extra, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in raw_extra.items()):
        extra = dict(raw_extra)
    else:
        errors.append(f"search.extraParams must be a string map: {source_id}")

    # Every check runs before the bail-out so validate reports the whole problem,
    # not just the first field that failed.
    if param is None or queries is None or extra is None:
        return None
    return SearchPlan(param=param, queries=queries, extra_params=extra)


def read_registry(document: dict) -> tuple[list[Source], list[str]]:
    """Parse a registry document into sources plus the errors that blocked parsing."""
    errors: list[str] = []
    sources: list[Source] = []
    if document.get("schema") != REGISTRY_SCHEMA:
        errors.append("unsupported or missing registry schema")
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        errors.append("sources must be a non-empty list")
        return sources, errors

    seen: set[str] = set()
    for raw in raw_sources:
        source_id = raw.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append("source has no id")
            continue
        if source_id in seen:
            errors.append(f"duplicate source id: {source_id}")
        seen.add(source_id)

        url = PublicUrl.parse(str(raw.get("url", "")))
        if url is None:
            errors.append(f"source URL must be public HTTPS without credentials: {source_id}")
        if raw.get("enabled") is not True:
            errors.append(f"source must explicitly set enabled=true: {source_id}")
        search = _read_search(source_id, raw.get("search"), errors)
        if url is None:
            continue
        sources.append(
            Source(
                id=source_id,
                url=url,
                publisher=raw.get("publisher"),
                category=raw.get("category"),
                authority=raw.get("authority"),
                search=search,
            )
        )
    return sources, errors


def load_registry(path: Path) -> tuple[list[Source], list[str]]:
    return read_registry(json.loads(path.read_text(encoding="utf-8")))
