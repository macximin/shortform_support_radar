import datetime as dt
import unittest

from tools.collect_public_notices import (
    diff_receipts,
    extract_candidates,
    extract_period,
    extract_status,
    is_public_https_url,
    build_requests,
    strip_badges,
    validate_registry,
    with_query,
)

OBSERVED_ON = dt.date(2026, 9, 1)


class PublicNoticeCollectorTests(unittest.TestCase):
    def test_rejects_credentials_and_non_https(self):
        self.assertTrue(is_public_https_url("https://example.go.kr/notices"))
        self.assertFalse(is_public_https_url("http://example.go.kr/notices"))
        self.assertFalse(is_public_https_url("https://user:password@example.go.kr/notices"))

    def test_extracts_only_keyword_rows(self):
        page = """
        <table><tbody>
          <tr><td>1</td><td><a href='/notice/1'>2027 AI 콘텐츠 제작지원 공고</a></td><td>26.08.31 ~ 26.09.21</td></tr>
          <tr><td>2</td><td><a href='/notice/2'>콘텐츠산업 정책</a></td><td>26.08.01 ~ 26.08.10</td></tr>
          <tr><td>3</td><td><a href='mailto:hello@example.go.kr'>웹툰 지원 공고</a></td><td></td></tr>
        </tbody></table>
        """
        found = extract_candidates(page, "https://example.go.kr/list", observed_on=OBSERVED_ON)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["title"], "2027 AI 콘텐츠 제작지원 공고")
        self.assertEqual(found[0]["url"], "https://example.go.kr/notice/1")

    def test_row_carries_period_and_open_state(self):
        page = """
        <table><tbody>
          <tr><td><a href='/a'>웹툰 IP 제작지원 모집</a></td><td>2026-08-31 ~ 2026-09-21</td></tr>
          <tr><td><a href='/b'>숏폼 드라마 제작지원 공고</a></td><td>2026.05.01.~ 2026.05.30.</td></tr>
        </tbody></table>
        """
        found = {c["title"]: c for c in extract_candidates(page, "https://example.go.kr/list", observed_on=OBSERVED_ON)}
        live = found["웹툰 IP 제작지원 모집"]
        self.assertEqual((live["period_start"], live["period_end"]), ("2026-08-31", "2026-09-21"))
        self.assertTrue(live["open_on_observation"])
        closed = found["숏폼 드라마 제작지원 공고"]
        self.assertEqual(closed["period_end"], "2026-05-30")
        self.assertFalse(closed["open_on_observation"])

    def test_ignores_dateless_navigation_rows(self):
        page = """
        <ul class='footer'>
          <li><a href='/agency/1'>지역콘텐츠기업지원센터</a></li>
          <li><a href='/agency/2'>뉴콘텐츠기업지원센터</a></li>
          <li><a href='/agency/3'>수출 플러스 지원단</a></li>
        </ul>
        <table><tbody>
          <tr><td><a href='/notice/9'>2026 콘텐츠 제작지원 공고</a></td><td>2026-09-01 ~ 2026-09-30</td></tr>
        </tbody></table>
        """
        found = extract_candidates(page, "https://example.go.kr/list", observed_on=OBSERVED_ON)
        self.assertEqual([c["title"] for c in found], ["2026 콘텐츠 제작지원 공고"])

    def test_keeps_dateless_row_carrying_a_status_label(self):
        page = "<ul><li><a href='/n/1'>웹툰 IP 제작지원 상시모집 공고</a><span>상시</span></li></ul>"
        found = extract_candidates(page, "https://example.go.kr/list", observed_on=OBSERVED_ON)
        self.assertEqual(found[0]["status_label"], "상시")
        self.assertIsNone(found[0]["period_end"])
        self.assertIsNone(found[0]["open_on_observation"])

    def test_strips_list_badges_from_title(self):
        page = "<ul><li><a href='/n/1'><span>새글</span> 2026 웹툰 IP 제작지원 모집</a><span>2026-09-01 ~ 2026-09-30</span></li></ul>"
        found = extract_candidates(page, "https://example.go.kr/list", observed_on=OBSERVED_ON)
        self.assertEqual(found[0]["title"], "2026 웹툰 IP 제작지원 모집")

    def test_period_and_status_parsing(self):
        self.assertEqual(extract_period("접수기간 26.08.31 ~ 26.09.21"), ("2026-08-31", "2026-09-21"))
        self.assertEqual(extract_period("모집기간 2026.07.01.~ 2026.08.31."), ("2026-07-01", "2026-08-31"))
        self.assertEqual(extract_period("상시모집"), (None, None))
        self.assertEqual(extract_status("미국 모집중 2027 콘텐츠"), "모집중")
        self.assertIsNone(extract_status("일반 안내"))

    def test_strip_badges(self):
        self.assertEqual(strip_badges("새글 공지 2026 지원사업"), "2026 지원사업")
        self.assertEqual(strip_badges("2026 지원사업"), "2026 지원사업")

    def test_registry_needs_explicit_enabled_public_sources(self):
        registry = {
            "schema": "shortform-support-radar-source-registry/v1",
            "sources": [{"id": "one", "url": "https://example.go.kr", "enabled": True}],
        }
        self.assertEqual(validate_registry(registry), [])
        registry["sources"][0]["url"] = "http://example.go.kr"
        self.assertIn("source URL must be public HTTPS without credentials: one", validate_registry(registry))

    def test_registry_rejects_malformed_search_block(self):
        registry = {
            "schema": "shortform-support-radar-source-registry/v1",
            "sources": [
                {"id": "one", "url": "https://example.go.kr", "enabled": True, "search": {"param": "q", "queries": []}}
            ],
        }
        self.assertIn("search.queries must be a non-empty list of strings: one", validate_registry(registry))

    def test_search_source_builds_one_request_per_query(self):
        source = {
            "id": "one",
            "url": "https://example.go.kr/list.jsp",
            "search": {"param": "q", "extraParams": {"type": "01"}, "queries": ["웹툰", "콘텐츠"]},
        }
        requests = build_requests(source)
        self.assertEqual([q for q, _ in requests], ["웹툰", "콘텐츠"])
        self.assertIn("type=01", requests[0][1])
        self.assertEqual(build_requests({"id": "two", "url": "https://example.go.kr/list"}), [(None, "https://example.go.kr/list")])

    def test_with_query_preserves_existing_params(self):
        url = with_query("https://example.go.kr/list.do?menuNo=204104", {"page": "2"})
        self.assertIn("menuNo=204104", url)
        self.assertIn("page=2", url)

    def test_diff_reports_new_and_closed_candidates(self):
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
        report = diff_receipts(previous, current)
        self.assertEqual([c["title"] for c in report["appeared"]], ["C 공고"])
        self.assertEqual([c["title"] for c in report["disappeared"]], ["A 공고"])
        self.assertEqual(report["unchanged_count"], 1)


if __name__ == "__main__":
    unittest.main()
