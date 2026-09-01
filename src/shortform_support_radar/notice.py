"""Notice domain: the discovery vocabulary, a recruitment period, and a candidate.

A Candidate deliberately has no field capable of holding a verdict. Whether a
company may apply, and whether it would be selected, is decided against the
notice text outside this context.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass

from .policy import PublicUrl

KEYWORDS = (
    "인공지능", "ai", "생성형", "방송영상", "드라마", "숏드라마", "숏폼",
    "웹툰", "webtoon", "ip", "지식재산", "콘텐츠", "해외진출", "수출",
    "제작지원", "제작 지원",
)
NOTICE_SIGNALS = ("공고", "모집", "지원", "사업", "참가", "쇼케이스", "공모")
STATUS_LABELS = ("모집중", "접수중", "진행중", "접수예정", "모집예정", "마감", "종료", "상시")
BADGE_PREFIXES = ("새글", "공지", "신규", "NEW", "new")

_DATE = r"(\d{2,4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*\.?"
DATE_RANGE_RE = re.compile(_DATE + r"\s*~\s*" + _DATE)
ANY_DATE_RE = re.compile(_DATE)

MIN_TITLE_LENGTH = 4


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def strip_badges(value: str) -> str:
    """Drop the list badges a board renders inside the link text."""
    text = value
    changed = True
    while changed:
        changed = False
        for badge in BADGE_PREFIXES:
            if text.startswith(badge):
                text = text[len(badge):].lstrip()
                changed = True
    return text


def looks_like_notice_title(title: str) -> bool:
    """A title is a discovery match, never a fit conclusion."""
    if len(title) < MIN_TITLE_LENGTH:
        return False
    lowered = title.lower()
    if not any(keyword in lowered for keyword in (k.lower() for k in KEYWORDS)):
        return False
    return any(signal in title for signal in NOTICE_SIGNALS)


def _to_date(year: str, month: str, day: str) -> dt.date | None:
    y, m, d = int(year), int(month), int(day)
    if y < 100:
        y += 2000
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


@dataclass(frozen=True)
class NoticePeriod:
    """The recruitment window a board publishes, as published."""

    start: dt.date | None = None
    end: dt.date | None = None

    @classmethod
    def parse(cls, text: str) -> "NoticePeriod":
        match = DATE_RANGE_RE.search(text)
        if not match:
            return cls()
        return cls(_to_date(*match.group(1, 2, 3)), _to_date(*match.group(4, 5, 6)))

    def state_on(self, day: dt.date) -> str | None:
        """Restate the board's own dates as a state. Not an eligibility test.

        A window that has not started yet is "upcoming", not "open"; reporting it
        as open is what a radar must not do.
        """
        if self.end is None:
            return None
        if self.end < day:
            return "closed"
        if self.start is not None and self.start > day:
            return "upcoming"
        return "open"

    def is_open_on(self, day: dt.date) -> bool | None:
        """True only while the window has started and has not ended."""
        state = self.state_on(day)
        return None if state is None else state == "open"


def find_status_label(text: str) -> str | None:
    for label in STATUS_LABELS:
        if label in text:
            return label
    return None


def carries_notice_metadata(text: str) -> bool:
    """A board row always publishes a date or a recruitment state.

    A row with neither is site navigation - a footer menu or a related-agency
    link - not a notice.
    """
    return bool(ANY_DATE_RE.search(text)) or find_status_label(text) is not None


@dataclass(frozen=True)
class Candidate:
    """A public notice observed on a board. Never a decision about it."""

    title: str
    url: PublicUrl
    period: NoticePeriod
    status_label: str | None = None
    matched_query: str | None = None

    def key(self) -> tuple[str, str]:
        """Identity of the notice, not of the search path that reached it."""
        url = self.url.without_params_valued({self.matched_query}) if self.matched_query else self.url
        return (self.title, str(url))

    def to_json(self, observed_on: dt.date) -> dict:
        return {
            "title": self.title,
            "url": str(self.url),
            "period_start": self.period.start.isoformat() if self.period.start else None,
            "period_end": self.period.end.isoformat() if self.period.end else None,
            "status_label": self.status_label,
            "period_state": self.period.state_on(observed_on),
            "open_on_observation": self.period.is_open_on(observed_on),
            "matched_query": self.matched_query,
        }

    def sort_key(self) -> tuple[bool, str, str]:
        return (self.period.end is None, self.period.end.isoformat() if self.period.end else "", self.title)
