"""Publish candidates into the Notion 지원사업 DB.

The database is a human review surface, and its `적격성 판정` property says so:
사람 확정 전 자동 승격 금지. This module encodes that split rather than trusting a
caller to remember it. The machine owns what it observed on a board; a person owns
every judgement about it.

Nothing here decides eligibility, and no payload this module can build is capable
of setting a judgement field on a row that already exists.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

from .notice import is_weak_match, mentions
from .policy import PolicyViolation, PublicUrl

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2022-06-28")
TOKEN_ENV = "NOTION_TOKEN"
DATABASE_ENV = "NOTION_DATABASE_ID"

# What the machine saw on a board. Safe to write and to refresh.
MACHINE_OWNED = frozenset(
    {"공고명", "원문 URL", "원천 ID", "접수 마감", "기관", "관심 축", "수집 근거", "최초 수집일", "최종 확인일"}
)

# What a person decides. The machine seeds these once when it creates a row and
# never touches them again, because a later run must not undo a review.
HUMAN_OWNED = frozenset({"상태", "적격성 판정", "근거 단계", "권리·대표권 확인", "메모", "지원 유형", "지역 조건", "지원 규모·비용"})

SEED_ON_CREATE = {
    "상태": "발견",
    "적격성 판정": "미검토",
    "근거 단계": "목록 발견",
    "권리·대표권 확인": "확인 전",
}

# Refreshed on every revisit: a board can extend a deadline, and the last-checked
# date is what tells a reader the row is not stale.
REFRESH_ON_REVISIT = frozenset({"접수 마감", "최종 확인일"})

# 기관 is set only where the board IS the body running the programme. Bizinfo and
# the MCST index are aggregators carrying other bodies' notices - the running body
# sits in a column this tool does not read, so the field is left empty rather than
# guessed. An unset property reads as unknown; a wrong one reads as a fact.
PUBLISHER_TO_AGENCY = {
    "kocca_pims_open": "KOCCA",
    "kocca_pims_archive": "KOCCA",
    "welcon_events": "WelCon/KOCCA",
    "kofic_business_notices": "기타",
}
AGGREGATOR_SOURCES = frozenset({"bizinfo_notices", "mcst_culture_support"})

# 관심 축 is derived from words actually present in the title. It is a topical
# tag, not a fit judgement.
# The words follow how the boards actually title notices: 방송콘텐츠 and 해외유통
# appear as often as 방송영상 and 해외진출.
AXIS_KEYWORDS = {
    "AI 숏드라마": ("인공지능", "ai", "생성형", "숏드라마", "숏폼"),
    "웹툰/IP": ("웹툰", "webtoon", "만화", "ip", "지식재산", "스토리"),
    "방송영상": ("방송영상", "방송콘텐츠", "드라마", "영상", "애니메이션", "실감콘텐츠"),
    "해외진출": ("해외진출", "해외유통", "수출", "글로벌", "참가기업"),
}


class NotionNotConfigured(RuntimeError):
    """Raised when a real sync is requested without credentials."""


@dataclass(frozen=True)
class NotionConfig:
    token: str
    database_id: str

    @classmethod
    def from_env(cls) -> "NotionConfig":
        token = os.environ.get(TOKEN_ENV, "").strip()
        database = os.environ.get(DATABASE_ENV, "").strip()
        missing = [name for name, value in ((TOKEN_ENV, token), (DATABASE_ENV, database)) if not value]
        if missing:
            raise NotionNotConfigured(
                f"set {' and '.join(missing)} in the environment; this repository never stores them"
            )
        return cls(token=token, database_id=database)


# Each board already issues a stable id for a notice. Using it as 원천 ID matches
# the rows a person entered by hand and survives a board editing a title, which a
# title-based key would not.
NATIVE_ID_PARAMS = ("pblancId", "intcNo", "rcrtSn", "seqNo", "idx", "no")

SOURCE_PREFIX = {
    "kocca_pims_open": "kocca",
    "kocca_pims_archive": "kocca",
    "welcon_events": "welcon",
    "mcst_culture_support": "mcst",
    "kofic_business_notices": "kofic",
    "bizinfo_notices": "bizinfo",
}


def native_id(url: str) -> str | None:
    """The board's own identifier for a notice, from its detail link."""
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    for name in NATIVE_ID_PARAMS:
        value = params.get(name, "").strip()
        if value:
            return value
    slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
    return slug or None


def source_key(candidate: dict, source_id: str) -> str:
    """A stable identifier for one notice, used as 원천 ID to avoid duplicates.

    Falls back to the title only when a board publishes no identifier of its own.
    """
    prefix = SOURCE_PREFIX.get(source_id, source_id)
    identifier = native_id(candidate.get("url", "")) or f"title:{candidate['title']}"
    return f"{prefix}:{identifier}"[:2000]


# A board that runs a programme is preferred over an aggregator that relists it,
# so the surviving row carries the agency rather than an empty 기관.
SOURCE_PRIORITY = ("kocca_pims_open", "welcon_events", "kocca_pims_archive", "kofic_business_notices")

_NOISE = re.compile(r"\([^)]*\)|\[[^\]]*\]|20\d\d\s*년?|[^0-9a-z가-힣]")
_TRAILING = ("공고문", "공고", "안내", "모집")


def programme_name(title: str) -> str:
    """A comparable form of a notice title, for spotting one programme on two boards.

    2027 콘텐츠 아메리카(Content Americas) 한국공동관 ... 모집 and
    2027 콘텐츠 아메리카 한국공동관 ... 모집공고 are the same call; the receipts keep
    both as separate observations, but a review database wants one row.
    """
    text = _NOISE.sub("", title.lower())
    changed = True
    while changed:
        changed = False
        for suffix in _TRAILING:
            if text.endswith(suffix) and len(text) > len(suffix) + 4:
                text = text[: -len(suffix)]
                changed = True
    return text


def _priority(source_id: str) -> int:
    return SOURCE_PRIORITY.index(source_id) if source_id in SOURCE_PRIORITY else len(SOURCE_PRIORITY)


def interest_axes(title: str) -> list[str]:
    """Topical tags for the words the title actually uses. Not a fit judgement."""
    return [axis for axis, words in AXIS_KEYWORDS.items() if any(mentions(w, title) for w in words)]


def _title(value: str) -> dict:
    return {"title": [{"text": {"content": value[:2000]}}]}


def _text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": value[:2000]}}]}


def _date(start: str | None, end: str | None = None) -> dict:
    if start is None:
        return {"date": None}
    return {"date": {"start": start, "end": end}}


def machine_properties(candidate: dict, source_id: str, observed_on: dt.date) -> dict:
    """Everything the machine observed. No judgement fields."""
    weak = is_weak_match(candidate["title"])
    # A weak match has no topical evidence, so it gets no topical tag.
    axes = [] if weak else interest_axes(candidate["title"])
    properties: dict = {
        "공고명": _title(candidate["title"]),
        "원천 ID": _text(source_key(candidate, source_id)),
        "접수 마감": _date(candidate.get("period_start"), candidate.get("period_end")),
        "수집 근거": _text(
            f"{source_id} 목록 행 관측"
            + (f" · 검색어 {candidate['matched_query']}" if candidate.get("matched_query") else "")
            + (" · 집계 게시판이라 수행기관 미확인" if source_id in AGGREGATOR_SOURCES else "")
            + (" · AI/IP 단독 매치라 콘텐츠 사업 여부 미확인" if weak else "")
        ),
        "최초 수집일": _date(observed_on.isoformat()),
        "최종 확인일": _date(observed_on.isoformat()),
    }
    agency = PUBLISHER_TO_AGENCY.get(source_id)
    if agency:
        properties["기관"] = {"select": {"name": agency}}
    url = candidate.get("url")
    if url and PublicUrl.parse(url) is not None:
        properties["원문 URL"] = {"url": url}
    if axes:
        properties["관심 축"] = {"multi_select": [{"name": a} for a in axes]}
    return properties


def create_payload(candidate: dict, source_id: str, observed_on: dt.date, database_id: str) -> dict:
    properties = machine_properties(candidate, source_id, observed_on)
    for name, value in SEED_ON_CREATE.items():
        properties[name] = {"select": {"name": value}}
    return {"parent": {"database_id": database_id}, "properties": properties}


def update_payload(candidate: dict, source_id: str, observed_on: dt.date) -> dict:
    """Only the facts a board can revise, plus proof we looked again.

    A review already recorded against this row survives untouched.
    """
    observed = machine_properties(candidate, source_id, observed_on)
    properties = {name: observed[name] for name in REFRESH_ON_REVISIT if name in observed}
    leaked = set(properties) & HUMAN_OWNED
    if leaked:
        raise PolicyViolation(f"refusing to overwrite human-owned fields: {sorted(leaked)}")
    return {"properties": properties}


def _request(config: NotionConfig, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{NOTION_API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {config.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Notion {method} {path} failed: {error.code} {detail}") from error


def existing_rows(config: NotionConfig) -> list[dict]:
    """Every row already in the database, as {key, title, page_id}."""
    rows: list[dict] = []
    cursor: str | None = None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        page = _request(config, "POST", f"/databases/{config.database_id}/query", body)
        for row in page.get("results", []):
            properties = row.get("properties", {})
            key = "".join(
                part.get("plain_text", "") for part in (properties.get("원천 ID", {}).get("rich_text") or [])
            ).strip()
            title = "".join(
                part.get("plain_text", "") for part in (properties.get("공고명", {}).get("title") or [])
            ).strip()
            rows.append({"key": key, "title": title, "page_id": row["id"]})
        if not page.get("has_more"):
            return rows
        cursor = page.get("next_cursor")


def index_existing(rows: list[dict]) -> tuple[dict[str, str], set[str]]:
    """Keys to page ids, plus the programme names already represented.

    Both are needed: a board id catches the same notice seen again, and the
    programme name catches the same call arriving from a different board.
    """
    keys = {r["key"]: r["page_id"] for r in rows if r["key"]}
    names = {programme_name(r["title"]) for r in rows if r["title"]}
    return keys, names


def plan_sync(
    documents: list[dict],
    observed_on: dt.date,
    known: dict[str, str],
    publish_weak: bool = False,
    known_programmes: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[dict], list[dict]]:
    """Split observed candidates into rows to create and rows to refresh.

    Only candidates with a published window are published: a row with no deadline
    cannot be triaged in a deadline database, and the KOFIC board has no period
    column at all.

    A weak match - one whose only vocabulary is the ambiguous AI or IP token - is
    held back by default. Querying those tokens is what recovers 순천시 글로벌 IP
    창·제작, but it also returns 휴머노이드 제조혁신센터 and 레시피 특허 출원, and a
    review database earns its keep by not carrying those. Pass publish_weak to
    include them; a row already in the database is always refreshed either way.
    """
    creates: dict[str, dict] = {}
    updates: list[dict] = []
    seen: set[str] = set()
    for document in documents:
        source_id = document["source"]["id"]
        for candidate in document.get("candidate_links", []):
            if candidate.get("period_state") not in {"open", "upcoming"}:
                continue
            key = source_key(candidate, source_id)
            if key in seen:
                continue
            seen.add(key)
            if key not in known and not publish_weak and is_weak_match(candidate["title"]):
                continue
            entry = {"key": key, "source_id": source_id, "candidate": candidate}
            if key in known:
                updates.append({**entry, "page_id": known[key]})
                continue
            # One programme, one row: prefer the board that runs it, and never add
            # one the database already carries under another board's id.
            name = programme_name(candidate["title"])
            if name in known_programmes:
                continue
            held = creates.get(name)
            if held is None or _priority(source_id) < _priority(held["source_id"]):
                creates[name] = entry
    return list(creates.values()), updates


def apply_sync(
    config: NotionConfig,
    creates: list[dict],
    updates: list[dict],
    observed_on: dt.date,
) -> dict:
    created = 0
    refreshed = 0
    for entry in creates:
        _request(
            config,
            "POST",
            "/pages",
            create_payload(entry["candidate"], entry["source_id"], observed_on, config.database_id),
        )
        created += 1
    for entry in updates:
        _request(
            config,
            "PATCH",
            f"/pages/{entry['page_id']}",
            update_payload(entry["candidate"], entry["source_id"], observed_on),
        )
        refreshed += 1
    return {"created": created, "refreshed": refreshed}
