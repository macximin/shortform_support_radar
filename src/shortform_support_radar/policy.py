"""Boundary invariants for the support radar.

This context collects public announcement candidates. It never authenticates,
never stores applicant data, and never records an eligibility decision. The types
here exist so those rules are structural rather than conventional: a URL carrying
credentials cannot be constructed, and every receipt is stamped from one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit, urlparse

USER_AGENT = "shortform-support-radar/0.3 (public-candidate-research; no-auth)"
MAX_RESPONSE_BYTES = 2_000_000
REQUEST_INTERVAL_SECONDS = 1.0


class PolicyViolation(ValueError):
    """Raised when a value would cross this context's collection boundary."""


@dataclass(frozen=True)
class PublicUrl:
    """An anonymous, public HTTPS endpoint.

    Construction rejects a non-HTTPS scheme and any embedded credential, so no
    later code path has to remember to check.
    """

    value: str

    def __post_init__(self) -> None:
        parsed = urlparse(self.value)
        if parsed.scheme != "https":
            raise PolicyViolation(f"collection requires https: {self.value}")
        if not parsed.netloc:
            raise PolicyViolation(f"collection requires a host: {self.value}")
        if parsed.username or parsed.password:
            raise PolicyViolation("collection URL must not carry credentials")

    @classmethod
    def parse(cls, value: str) -> "PublicUrl | None":
        """Return the URL, or None when it falls outside the boundary."""
        try:
            return cls(value)
        except PolicyViolation:
            return None

    def join(self, href: str) -> "PublicUrl | None":
        return PublicUrl.parse(urljoin(self.value, href))

    def with_query(self, params: dict[str, str]) -> "PublicUrl":
        parts = urlsplit(self.value)
        merged = dict(parse_qsl(parts.query, keep_blank_values=True))
        merged.update(params)
        return PublicUrl(urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment)))

    def __str__(self) -> str:
        return self.value


def enforce_response_cap(body: bytes) -> bytes:
    """Reject an oversized response instead of buffering it."""
    if len(body) > MAX_RESPONSE_BYTES:
        raise PolicyViolation(f"response exceeded {MAX_RESPONSE_BYTES} byte limit")
    return body


def policy_stamp() -> dict[str, bool]:
    """The claim every artifact of this context carries.

    A collection result is a candidate observation. Promoting one to an
    eligibility or funding conclusion happens outside this context, against the
    notice text itself.
    """
    return {"candidate_only": True, "not_an_eligibility_decision": True}
