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
from shortform_support_radar.collection import HostRateLimiter  # noqa: E402
from shortform_support_radar.receipts import (  # noqa: E402
    diff_documents,
    open_candidates,
    previous_run_dir,
    status_markdown,
)
import tempfile  # noqa: E402
from shortform_support_radar.registry import REGISTRY_SCHEMA, load_registry, read_registry  # noqa: E402
from shortform_support_radar.notice import KEYWORDS  # noqa: E402

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

    def test_open_state_restates_the_board_dates(self):
        self.assertTrue(NoticePeriod(end=dt.date(2026, 9, 21)).is_open_on(OBSERVED_ON))
        self.assertFalse(NoticePeriod(end=dt.date(2026, 8, 31)).is_open_on(OBSERVED_ON))
        self.assertIsNone(NoticePeriod().is_open_on(OBSERVED_ON))

    def test_a_window_that_has_not_started_is_upcoming_not_open(self):
        upcoming = NoticePeriod(dt.date(2026, 10, 1), dt.date(2026, 10, 30))
        self.assertEqual(upcoming.state_on(OBSERVED_ON), "upcoming")
        self.assertFalse(upcoming.is_open_on(OBSERVED_ON))

    def test_period_states(self):
        cases = {
            "closed": NoticePeriod(dt.date(2026, 8, 1), dt.date(2026, 8, 31)),
            "open": NoticePeriod(dt.date(2026, 8, 20), dt.date(2026, 9, 21)),
            "upcoming": NoticePeriod(dt.date(2026, 10, 1), dt.date(2026, 10, 31)),
        }
        for expected, period in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(period.state_on(OBSERVED_ON), expected)
        self.assertIsNone(NoticePeriod().state_on(OBSERVED_ON))

    def test_title_and_row_predicates(self):
        self.assertTrue(looks_like_notice_title("2026 웹툰 IP 제작지원 모집"))
        self.assertFalse(looks_like_notice_title("공지"))
        self.assertFalse(looks_like_notice_title("2026 한글런 참가자 모집 안내"))
        self.assertFalse(carries_notice_metadata("지역콘텐츠기업지원센터"))
        self.assertTrue(carries_notice_metadata("2026-09-01 ~ 2026-09-30"))
        self.assertEqual(find_status_label("미국 모집중 2027 콘텐츠"), "모집중")
        self.assertIsNone(find_status_label("일반 안내"))

    def test_filter_vocabulary_covers_every_registry_query(self):
        # Querying a board for a word the filter then rejects loses real notices.
        sources, errors = load_registry(ROOT / "config" / "sources.json")
        self.assertEqual(errors, [])
        lowered = {k.lower() for k in KEYWORDS}
        for source in sources:
            if source.all_rows_in_scope:
                continue
            for plan in source.searches:
                if plan.probe:
                    continue  # a probe deliberately searches outside the vocabulary
                for query in plan.queries:
                    if query.endswith("진흥원") or query.endswith("공사"):
                        continue  # an agency axis names a body, not a topic
                    with self.subTest(source=source.id, query=query):
                        self.assertTrue(
                            any(k in query.lower() or query.lower() in k for k in lowered),
                            f"{source.id} queries {query!r} but the filter vocabulary cannot match it",
                        )

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

    def test_the_same_notice_found_by_two_queries_is_one_candidate(self):
        # A board echoes the search term into the detail link, so the two URLs
        # differ only by the term that reached them.
        row = '<table><tbody><tr><td><a href="{href}">2026 웹툰 콘텐츠 제작지원 공고</a></td><td>2026-09-01 ~ 2026-09-30</td></tr></tbody></table>'
        first = read_candidates(row.format(href="/d?pblancId=PBLN_1&keyword=콘텐츠"), BASE, matched_query="콘텐츠")[0]
        second = read_candidates(row.format(href="/d?pblancId=PBLN_1&keyword=웹툰"), BASE, matched_query="웹툰")[0]
        self.assertEqual(first.key(), second.key())
        self.assertNotEqual(str(first.url), str(second.url))

    def test_distinct_notices_keep_distinct_identities(self):
        row = '<table><tbody><tr><td><a href="{href}">2026 웹툰 콘텐츠 제작지원 공고</a></td><td>2026-09-01 ~ 2026-09-30</td></tr></tbody></table>'
        first = read_candidates(row.format(href="/d?pblancId=PBLN_1&keyword=콘텐츠"), BASE, matched_query="콘텐츠")[0]
        other = read_candidates(row.format(href="/d?pblancId=PBLN_2&keyword=콘텐츠"), BASE, matched_query="콘텐츠")[0]
        self.assertNotEqual(first.key(), other.key())

    def test_the_same_notice_found_by_two_axes_is_one_candidate(self):
        # Bizinfo echoes both the search field and the term into its detail link,
        # so a title hit and an agency hit on one notice differ by two params.
        row = '<table><tbody><tr><td><a href="{href}">2026 ATF 애니메이션 참가기업 모집 공고</a></td><td>2026-09-01 ~ 2026-09-30</td></tr></tbody></table>'
        names = frozenset({"condition", "keyword"})
        by_title = read_candidates(
            row.format(href="/d?pblancId=P1&condition=searchPblancNm&keyword=애니메이션"),
            BASE, matched_query="애니메이션", search_param_names=names,
        )[0]
        by_agency = read_candidates(
            row.format(href="/d?pblancId=P1&condition=searchExcInsttNm&keyword=한국콘텐츠진흥원"),
            BASE, matched_query="한국콘텐츠진흥원", search_param_names=names,
        )[0]
        self.assertEqual(by_title.key(), by_agency.key())
        self.assertNotEqual(str(by_title.url), str(by_agency.url))

    def test_board_scoped_source_keeps_rows_the_vocabulary_would_drop(self):
        page = """
        <ul>
          <li><a href="/e/1">2026 콘텐츠IP 마켓</a><span>2026-09-01 ~ 2026-09-30</span></li>
          <li><a href="/e/2">아시아 TV 포럼 &amp; 마켓</a><span>2026-09-01 ~ 2026-09-30</span></li>
        </ul>
        """
        self.assertEqual(read_candidates(page, BASE), [])
        scoped = read_candidates(page, BASE, all_rows_in_scope=True)
        self.assertEqual([c.title for c in scoped], ["2026 콘텐츠IP 마켓", "아시아 TV 포럼 & 마켓"])

    def test_board_scope_still_requires_notice_metadata(self):
        page = '<ul><li><a href="/nav">지역콘텐츠기업지원센터</a></li></ul>'
        self.assertEqual(read_candidates(page, BASE, all_rows_in_scope=True), [])

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


class SearchPaginationTests(unittest.TestCase):
    def plan(self, **search):
        base = {"param": "q", "queries": ["웹툰"]}
        document = {
            "schema": REGISTRY_SCHEMA,
            "sources": [{"id": "one", "url": "https://a.go.kr/l", "enabled": True, "search": {**base, **search}}],
        }
        return read_registry(document)

    def test_single_page_is_the_default(self):
        sources, errors = self.plan()
        self.assertEqual(errors, [])
        self.assertEqual(len(sources[0].requests()), 1)

    def test_pages_expand_into_one_request_per_page(self):
        sources, errors = self.plan(pages=3, pageParam="p")
        self.assertEqual(errors, [])
        urls = [str(u) for _, u in sources[0].requests()]
        self.assertEqual(len(urls), 3)
        self.assertNotIn("p=", urls[0])
        self.assertIn("p=2", urls[1])
        self.assertIn("p=3", urls[2])

    def test_pages_without_a_page_param_is_rejected(self):
        _, errors = self.plan(pages=2)
        self.assertIn("search.pages > 1 requires search.pageParam: one", errors)

    def test_pages_must_be_a_positive_integer(self):
        for bad in (0, -1, "2", True):
            with self.subTest(bad=bad):
                _, errors = self.plan(pages=bad, pageParam="p")
                self.assertIn("search.pages must be an integer >= 1: one", errors)


class HostRateLimiterTests(unittest.TestCase):
    def limiter(self):
        slept: list[float] = []
        now = [0.0]

        def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds

        return HostRateLimiter(interval=1.0, sleep=sleep, clock=lambda: now[0]), slept, now

    def test_first_request_to_a_host_does_not_wait(self):
        limiter, slept, _ = self.limiter()
        limiter.wait_for(PublicUrl("https://a.go.kr/1"))
        self.assertEqual(slept, [])

    def test_second_request_to_the_same_host_waits(self):
        limiter, slept, _ = self.limiter()
        limiter.wait_for(PublicUrl("https://a.go.kr/1"))
        limiter.wait_for(PublicUrl("https://a.go.kr/2"))
        self.assertEqual(slept, [1.0])

    def test_pacing_holds_across_sources_sharing_a_host(self):
        limiter, slept, _ = self.limiter()
        for url in ("https://a.go.kr/x", "https://b.go.kr/y", "https://a.go.kr/z"):
            limiter.wait_for(PublicUrl(url))
        self.assertEqual(slept, [1.0])

    def test_a_different_host_never_waits(self):
        limiter, slept, _ = self.limiter()
        limiter.wait_for(PublicUrl("https://a.go.kr/1"))
        limiter.wait_for(PublicUrl("https://b.go.kr/1"))
        self.assertEqual(slept, [])

    def test_a_failing_host_is_given_more_room_each_time(self):
        limiter, slept, _ = self.limiter()
        url = PublicUrl("https://a.go.kr/1")
        self.assertEqual(limiter.interval_for(url), 1.0)
        limiter.penalise(url)
        self.assertEqual(limiter.interval_for(url), 5.0)
        limiter.penalise(url)
        self.assertEqual(limiter.interval_for(url), 9.0)

    def test_a_penalty_does_not_touch_another_host(self):
        limiter, _, _ = self.limiter()
        limiter.penalise(PublicUrl("https://a.go.kr/1"))
        self.assertEqual(limiter.interval_for(PublicUrl("https://b.go.kr/1")), 1.0)

    def test_host_pacing_is_capped(self):
        limiter, _, _ = self.limiter()
        url = PublicUrl("https://a.go.kr/1")
        for _ in range(20):
            limiter.penalise(url)
        self.assertEqual(limiter.interval_for(url), 20.0)

    def test_a_penalised_host_actually_waits_longer(self):
        limiter, slept, _ = self.limiter()
        url = PublicUrl("https://a.go.kr/1")
        limiter.wait_for(url)
        limiter.penalise(url)
        limiter.wait_for(url)
        self.assertEqual(slept, [5.0])

    def test_elapsed_time_counts_against_the_interval(self):
        limiter, slept, now = self.limiter()
        limiter.wait_for(PublicUrl("https://a.go.kr/1"))
        now[0] += 0.75
        limiter.wait_for(PublicUrl("https://a.go.kr/2"))
        self.assertEqual(slept, [0.25])


class StatusTests(unittest.TestCase):
    def documents(self):
        return [
            {
                "source": {"id": "one"},
                "candidate_links": [
                    {"title": "닫힘 공고", "url": "https://a.go.kr/1", "period_end": "2026-08-31", "period_state": "closed"},
                    {"title": "열림 공고", "url": "https://a.go.kr/2", "period_end": "2026-09-21", "period_state": "open"},
                    {"title": "예정 공고", "url": "https://a.go.kr/3", "period_end": "2026-10-30", "period_state": "upcoming"},
                ],
            }
        ]

    def test_only_open_candidates_are_listed(self):
        rows = open_candidates(self.documents())
        self.assertEqual([r["title"] for r in rows], ["열림 공고"])
        self.assertEqual(rows[0]["source_id"], "one")

    def test_status_reports_days_left_and_disclaims_eligibility(self):
        md = status_markdown(self.documents(), OBSERVED_ON)
        self.assertIn("Open now (1)", md)
        self.assertIn("| 2026-09-21 | 20 | one |", md)
        self.assertIn("Eligibility", md)
        self.assertNotIn("닫힘 공고", md)

    def test_status_surfaces_what_is_new(self):
        diff = {
            "appeared_total": 1,
            "disappeared_total": 0,
            "sources": [{"appeared": [{"title": "새 공고", "url": "https://a.go.kr/9", "period_end": "2026-09-30"}]}],
        }
        md = status_markdown(self.documents(), OBSERVED_ON, diff)
        self.assertIn("1 appeared, 0 no longer listed", md)
        self.assertIn("[새 공고](https://a.go.kr/9) — closes 2026-09-30", md)

    def test_status_flags_a_partial_run(self):
        md = status_markdown(self.documents(), OBSERVED_ON, None, ["bizinfo_notices", "mcst_culture_support"])
        self.assertIn("Partial run", md)
        self.assertIn("`bizinfo_notices`", md)
        self.assertIn("`mcst_culture_support`", md)

    def test_status_says_nothing_about_partiality_on_a_full_run(self):
        self.assertNotIn("Partial run", status_markdown(self.documents(), OBSERVED_ON, None, []))

    def test_status_handles_an_empty_board(self):
        md = status_markdown([], OBSERVED_ON)
        self.assertIn("Nothing open on the registered boards.", md)

    def test_previous_run_dir_finds_the_last_dated_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for day in ("2026-08-30", "2026-08-31", "2026-09-01"):
                (root / day / "daily").mkdir(parents=True)
            self.assertEqual(previous_run_dir(root / "2026-09-01" / "daily"), root / "2026-08-31" / "daily")
            self.assertIsNone(previous_run_dir(root / "2026-08-30" / "daily"))

    def test_previous_run_dir_ignores_a_differently_named_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2026-08-31" / "canary").mkdir(parents=True)
            (root / "2026-09-01" / "daily").mkdir(parents=True)
            self.assertIsNone(previous_run_dir(root / "2026-09-01" / "daily"))


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
