"""Tests for the support radar package.

The boundary tests matter most: a credentialed URL must not be constructible, and
a candidate must not be able to carry an eligibility verdict.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shortform_support_radar.boards import read_candidates  # noqa: E402
from shortform_support_radar.notice import (  # noqa: E402
    Candidate,
    NoticePeriod,
    carries_notice_metadata,
    find_status_label,
    looks_like_notice_title,
    strip_badges,
)
from shortform_support_radar.policy import (  # noqa: E402
    PolicyViolation,
    PublicUrl,
    enforce_response_cap,
    policy_stamp,
)
from shortform_support_radar.receipts import diff_documents  # noqa: E402
from shortform_support_radar.registry import REGISTRY_SCHEMA, load_registry, read_registry  # noqa: E402

OBSERVED_ON = dt.date(2026, 9, 1)
BASE = PublicUrl("https://example.go.kr/list")


class PolicyBoundaryTests(unittest.TestCase):
    def test_public_url_rejects_credentials_and_plaintext(self):
        self.assertEqual(str(PublicUrl("https://example.go.kr/notices")), "https://example.go.kr/notices")
        for rejected in ("http://example.go.kr", "https://user:password@example.go.kr", "ftp://x.go.kr"):
            with self.subTest(rejected=rejected):
                self.assertIsNone(PublicUrl.parse(rejected))
                with self.assertRaises(PolicyViolation):
                    PublicUrl(rejected)

    def test_with_query_preserves_existing_params(self):
        url = PublicUrl("https://example.go.kr/list.do?menuNo=204104").with_query({"page": "2"})
        self.assertIn("menuNo=204104", str(url))
        self.assertIn("page=2", str(url))

    def test_join_keeps_the_boundary(self):
        self.assertEqual(str(BASE.join("/notice/1")), "https://example.go.kr/notice/1")
        self.assertIsNone(BASE.join("mailto:hello@example.go.kr"))

    def test_response_cap_is_enforced(self):
        self.assertEqual(enforce_response_cap(b"short"), b"short")
        with self.assertRaises(PolicyViolation):
            enforce_response_cap(b"x" * 2_000_001)

    def test_policy_stamp_is_the_single_source_of_the_claim(self):
        self.assertEqual(policy_stamp(), {"candidate_only": True, "not_an_eligibility_decision": True})

    def test_candidate_cannot_carry_a_verdict(self):
        candidate = Candidate(title="2026 webtoon IP support", url=BASE, period=NoticePeriod())
        fields = set(candidate.to_json(OBSERVED_ON))
        self.assertEqual(fields & {"eligible", "eligibility", "decision", "recommended", "selected"}, set())
        with self.assertRaises(TypeError):
            Candidate(title="x", url=BASE, period=NoticePeriod(), eligible=True)


class NoticeDomainTests(unittest.TestCase):
    def test_period_parsing_across_board_formats(self):
        self.assertEqual(
            NoticePeriod.parse("접수기간 26.08.31 ~ 26.09.21"),
            NoticePeriod(dt.date(2026, 8, 31), dt.date(2026, 9, 21)),
        )
        self.assertEqual(
            NoticePeriod.parse("모집기간 2026.07.01.~ 2026.08.31."),
            NoticePeriod(dt.date(2026, 7, 1), dt.date(2026, 8, 31)),
        )
        self.assertEqual(
            NoticePeriod.parse("2026-08-27 ~ 2026-09-10"),
            NoticePeriod(dt.date(2026, 8, 27), dt.date(2026, 9, 10)),
        )
        self.assertEqual(NoticePeriod.parse("상시모집"), NoticePeriod())

    def test_open_state_restates_the_board_end_date(self):
        self.assertTrue(NoticePeriod(end=dt.date(2026, 9, 21)).is_open_on(OBSERVED_ON))
        self.assertFalse(NoticePeriod(end=dt.date(2026, 8, 31)).is_open_on(OBSERVED_ON))
        self.assertIsNone(NoticePeriod().is_open_on(OBSERVED_ON))

    def test_title_and_row_predicates(self):
        self.assertTrue(looks_like_notice_title("2026 웹툰 IP 제작지원 모집"))
        self.assertFalse(looks_like_notice_title("공지"))
        self.assertFalse(looks_like_notice_title("2026 한글런 참가자 모집 안내"))
        self.assertFalse(carries_notice_metadata("지역콘텐츠기업지원센터"))
        self.assertTrue(carries_notice_metadata("2026-09-01 ~ 2026-09-30"))
        self.assertEqual(find_status_label("미국 모집중 2027 콘텐츠"), "모집중")
        self.assertIsNone(find_status_label("일반 안내"))

    def test_strip_badges(self):
        self.assertEqual(strip_badges("새글 공지 2026 지원사업"), "2026 지원사업")
        self.assertEqual(strip_badges("2026 지원사업"), "2026 지원사업")


class BoardReadingTests(unittest.TestCase):
    def test_reads_rows_with_period_and_open_state(self):
        page = """
        <table><tbody>
          <tr><td><a href="/a">웹툰 IP 제작지원 모집</a></td><td>2026-08-31 ~ 2026-09-21</td></tr>
          <tr><td><a href="/b">숏폼 드라마 제작지원 공고</a></td><td>2026.05.01.~ 2026.05.30.</td></tr>
        </tbody></table>
        """
        found = {c.title: c for c in read_candidates(page, BASE)}
        self.assertTrue(found["웹툰 IP 제작지원 모집"].period.is_open_on(OBSERVED_ON))
        self.assertFalse(found["숏폼 드라마 제작지원 공고"].period.is_open_on(OBSERVED_ON))

    def test_drops_dateless_navigation_rows(self):
        page = """
        <ul class="footer">
          <li><a href="/agency/1">지역콘텐츠기업지원센터</a></li>
          <li><a href="/agency/2">뉴콘텐츠기업지원센터</a></li>
          <li><a href="/agency/3">수출 플러스 지원단</a></li>
        </ul>
        <table><tbody>
          <tr><td><a href="/notice/9">2026 콘텐츠 제작지원 공고</a></td><td>2026-09-01 ~ 2026-09-30</td></tr>
        </tbody></table>
        """
        self.assertEqual([c.title for c in read_candidates(page, BASE)], ["2026 콘텐츠 제작지원 공고"])

    def test_keeps_dateless_row_with_a_status_label(self):
        page = '<ul><li><a href="/n/1">웹툰 IP 제작지원 상시모집 공고</a><span>상시</span></li></ul>'
        found = read_candidates(page, BASE)
        self.assertEqual(found[0].status_label, "상시")
        self.assertIsNone(found[0].period.end)

    def test_strips_badges_and_skips_non_public_links(self):
        page = """
        <table><tbody>
          <tr><td><a href="/n/1"><span>새글</span> 2026 웹툰 IP 제작지원 모집</a></td><td>2026-09-01 ~ 2026-09-30</td></tr>
          <tr><td><a href="mailto:x@example.go.kr">웹툰 지원 공고</a></td><td>2026-09-01 ~ 2026-09-30</td></tr>
        </tbody></table>
        """
        self.assertEqual([c.title for c in read_candidates(page, BASE)], ["2026 웹툰 IP 제작지원 모집"])

    def test_records_the_query_that_surfaced_the_row(self):
        page = (
            '<table><tbody><tr><td><a href="/n/1">2026 웹툰 IP 제작지원 모집</a></td>'
            "<td>2026-09-01 ~ 2026-09-30</td></tr></tbody></table>"
        )
        self.assertEqual(read_candidates(page, BASE, matched_query="웹툰")[0].matched_query, "웹툰")


class RegistryTests(unittest.TestCase):
    def document(self, **source) -> dict:
        base = {"id": "one", "url": "https://example.go.kr", "enabled": True}
        return {"schema": REGISTRY_SCHEMA, "sources": [{**base, **source}]}

    def test_valid_registry_parses(self):
        sources, errors = read_registry(self.document())
        self.assertEqual(errors, [])
        self.assertEqual(sources[0].search_mode, "list_page")
        self.assertEqual(sources[0].requests(), [(None, PublicUrl("https://example.go.kr"))])

    def test_rejects_plaintext_url_and_implicit_enable(self):
        _, errors = read_registry(self.document(url="http://example.go.kr"))
        self.assertIn("source URL must be public HTTPS without credentials: one", errors)
        _, errors = read_registry(
            {"schema": REGISTRY_SCHEMA, "sources": [{"id": "one", "url": "https://example.go.kr"}]}
        )
        self.assertIn("source must explicitly set enabled=true: one", errors)

    def test_rejects_malformed_search_block(self):
        _, errors = read_registry(self.document(search={"param": "q", "queries": []}))
        self.assertIn("search.queries must be a non-empty list of strings: one", errors)

    def test_reports_every_malformed_search_field_at_once(self):
        _, errors = read_registry(
            self.document(search={"param": "", "queries": [], "extraParams": {"k": 1}})
        )
        self.assertEqual(
            errors,
            [
                "search.param must be a non-empty string: one",
                "search.queries must be a non-empty list of strings: one",
                "search.extraParams must be a string map: one",
            ],
        )

    def test_search_source_builds_one_request_per_query(self):
        sources, errors = read_registry(
            self.document(
                url="https://example.go.kr/list.jsp",
                search={"param": "q", "extraParams": {"type": "01"}, "queries": ["웹툰", "콘텐츠"]},
            )
        )
        self.assertEqual(errors, [])
        requests = sources[0].requests()
        self.assertEqual([q for q, _ in requests], ["웹툰", "콘텐츠"])
        self.assertIn("type=01", str(requests[0][1]))
        self.assertEqual(sources[0].search_mode, "server_side_query")

    def test_live_registry_parses_without_error(self):
        sources, errors = load_registry(ROOT / "config" / "sources.json")
        self.assertEqual(errors, [])
        self.assertTrue(sources)


class DiffTests(unittest.TestCase):
    def test_reports_new_and_closed_candidates(self):
        previous = {
            "source": {"id": "one"},
            "observed_at": "2026-08-25T00:00:00+00:00",
            "candidate_links": [
                {"title": "A 공고", "url": "https://example.go.kr/1"},
                {"title": "B 공고", "url": "https://example.go.kr/2"},
            ],
        }
        current = {
            "source": {"id": "one"},
            "observed_at": "2026-09-01T00:00:00+00:00",
            "candidate_links": [
                {"title": "B 공고", "url": "https://example.go.kr/2"},
                {"title": "C 공고", "url": "https://example.go.kr/3"},
            ],
        }
        report = diff_documents(previous, current)
        self.assertEqual([c["title"] for c in report["appeared"]], ["C 공고"])
        self.assertEqual([c["title"] for c in report["disappeared"]], ["A 공고"])
        self.assertEqual(report["unchanged_count"], 1)


if __name__ == "__main__":
    unittest.main()
