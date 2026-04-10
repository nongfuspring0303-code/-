import os
import tempfile
import yaml

from scripts.ai_event_intel import NewsIngestion


def test_jin10_fetch_returns_empty_when_no_token():
    cfg = {
        "modules": {
            "NewsIngestion": {
                "params": {
                    "enable_jin10": True,
                    "jin10": {
                        "mcp_url": "https://mcp.jin10.com/mcp",
                        "token_env": "JIN10_MCP_TOKEN_TEST",
                    },
                    "sources": [],
                }
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(cfg, f)
        path = f.name

    try:
        if "JIN10_MCP_TOKEN_TEST" in os.environ:
            os.environ.pop("JIN10_MCP_TOKEN_TEST")
        ingestion = NewsIngestion(path)
        items = ingestion._fetch_jin10(timeout=1)
        assert items == []
    finally:
        os.unlink(path)
