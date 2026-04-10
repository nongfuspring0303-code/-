#!/usr/bin/env python3
"""Tests for Sina news source integration."""

import pytest
from unittest.mock import patch, MagicMock
import json


class TestSinaFetch:
    """Test _fetch_sina method."""

    def test_fetch_sina_disabled_by_config(self):
        """Sina fetch returns empty when disabled."""
        import sys
        sys.path.insert(0, "scripts")
        from ai_event_intel import NewsIngestion

        with patch.object(NewsIngestion, "_get_config", return_value=False):
            ni = NewsIngestion()
            result = ni._fetch_sina(timeout=5)
            assert result == []

    def test_fetch_sina_parses_response(self):
        """Sina fetch correctly parses API response."""
        import sys
        sys.path.insert(0, "scripts")
        from ai_event_intel import NewsIngestion

        mock_response = {
            "result": {
                "data": {
                    "feed": {
                        "list": [
                            {
                                "id": 12345,
                                "rich_text": "测试新闻标题",
                                "docurl": "https://example.com/article",
                                "create_time": "2026-04-10 06:00:19"
                            }
                        ]
                    }
                }
            }
        }

        mock_payload = json.dumps(mock_response).encode("utf-8")

        def mock_get_config(self, path, default=None):
            if "enable_sina" in path:
                return True
            if "sina.url" in path:
                return "http://test.com"
            if "sina.params" in path:
                return {}
            return default

        with patch.object(NewsIngestion, "_get_config", mock_get_config):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_context = MagicMock()
                mock_context.__enter__ = MagicMock(return_value=mock_context)
                mock_context.__exit__ = MagicMock(return_value=False)
                mock_context.read.return_value = mock_payload
                mock_urlopen.return_value = mock_context

                ni = NewsIngestion()
                result = ni._fetch_sina(timeout=5)

                assert len(result) == 1
                assert result[0]["headline"] == "测试新闻标题"
                assert result[0]["source_type"] == "sina"
                assert result[0]["source_mode"] == "push"
                assert "SINA-12345" in result[0]["event_id"]


class TestSinaNormalization:
    """Test Sina item normalization via _normalize_item."""

    def test_normalize_sina_item(self):
        """Sina items normalize correctly through standard pipeline."""
        import sys
        sys.path.insert(0, "scripts")
        from ai_event_intel import NewsIngestion

        sina_item = {
            "headline": "新浪财经新闻",
            "source_url": "https://finance.sina.com.cn/article.html",
            "timestamp": "2026-04-10T06:00:19Z",
            "raw_text": "新浪财经新闻内容",
            "source_type": "sina",
            "event_id": "SINA-12345",
        }

        ni = NewsIngestion()
        normalized = ni._normalize_item(sina_item)

        assert normalized["headline"] == "新浪财经新闻"
        assert normalized["source_type"] == "sina"
        assert normalized["source_mode"] == "push"
        assert normalized["source_url"] == "https://finance.sina.com.cn/article.html"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
