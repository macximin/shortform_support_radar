import unittest

from tools.collect_public_notices import extract_candidates, is_public_https_url, validate_registry


class PublicNoticeCollectorTests(unittest.TestCase):
    def test_rejects_credentials_and_non_https(self):
        self.assertTrue(is_public_https_url("https://example.go.kr/notices"))
        self.assertFalse(is_public_https_url("http://example.go.kr/notices"))
        self.assertFalse(is_public_https_url("https://user:password@example.go.kr/notices"))

    def test_extracts_only_keyword_links(self):
        page = """
        <a href='/notice/1'>2027 AI 콘텐츠 제작지원</a>
        <a href='/notice/2'>콘텐츠산업 정책</a>
        <a href='mailto:hello@example.go.kr'>웹툰 지원</a>
        """
        self.assertEqual(
            extract_candidates(page, "https://example.go.kr/list"),
            [{"title": "2027 AI 콘텐츠 제작지원", "url": "https://example.go.kr/notice/1"}],
        )

    def test_registry_needs_explicit_enabled_public_sources(self):
        registry = {
            "schema": "shortform-support-radar-source-registry/v1",
            "sources": [{"id": "one", "url": "https://example.go.kr", "enabled": True}],
        }
        self.assertEqual(validate_registry(registry), [])
        registry["sources"][0]["url"] = "http://example.go.kr"
        self.assertIn("source URL must be public HTTPS without credentials: one", validate_registry(registry))


if __name__ == "__main__":
    unittest.main()
