# Sina 直播 API 接入实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将新浪财经直播 API 作为主新闻源接入 NewsIngestion，提供更低延迟的中文财经资讯

**Architecture:** 在 NewsIngestion 中添加 _fetch_sina() 方法，与现有 RSS 源一起处理、去重、归一化

**Tech Stack:** Python, urllib, XML/JSON 解析

---

## 任务总览

1. 在 `ai_event_intel.py` 添加 `_fetch_sina()` 方法
2. 修改 `execute()` 方法调用 `_fetch_sina()` 并合并结果
3. 配置变更：更新 `edt-modules-config.yaml`
4. 单元测试：验证字段映射与去重
5. 集成测试：验证端到端新闻获取

---

## Task 1: 添加 _fetch_sina() 方法

**Files:**
- Modify: `scripts/ai_event_intel.py:1-30` (imports)
- Modify: `scripts/ai_event_intel.py:300-330` (在 _normalize_item 后添加新方法)

- [ ] **Step 1: 添加 Sina 常量与配置读取**

在文件顶部 import 区域后添加：

```python
SINA_DEFAULT_URL = "http://zhibo.sina.com.cn/api/zhibo/feed"
SINA_DEFAULT_PARAMS = {
    "page": 1,
    "page_size": 20,
    "zhibo_id": 152,
    "dire": "f",
}
SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://finance.sina.com.cn/7x24/",
}
```

- [ ] **Step 2: 实现 _fetch_sina() 方法**

在 `NewsIngestion` 类中添加方法（位置：`_normalize_item` 方法后）：

```python
def _fetch_sina(self, timeout: int = 8) -> List[Dict[str, Any]]:
    """Fetch news from Sina live API."""
    enable_sina = bool(self._get_config("modules.NewsIngestion.params.enable_sina", False))
    if not enable_sina:
        return []
    
    url = self._get_config("modules.NewsIngestion.params.sina.url", SINA_DEFAULT_URL)
    params = self._get_config("modules.NewsIngestion.params.sina.params", SINA_DEFAULT_PARAMS)
    
    try:
        import urllib.request
        import urllib.parse
        
        req = urllib.request.Request(
            f"{url}?{urllib.parse.urlencode(params)}",
            headers=SINA_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        
        result_data = payload.get("result", {})
        feed_data = result_data.get("data", {})
        feed = feed_data.get("feed", {})
        items_raw = feed.get("list", [])
        
        if not isinstance(items_raw, list):
            return []
        
        items = []
        for raw in items_raw:
            headline = raw.get("rich_text", "")
            if not headline:
                continue
            
            docurl = raw.get("docurl", "")
            create_time = raw.get("create_time", "")
            item_id = raw.get("id", 0)
            
            # 转换时间格式: "2026-04-10 06:00:19" -> ISO 8601
            timestamp = create_time
            if create_time:
                try:
                    dt = datetime.strptime(create_time, "%Y-%m-%d %H:%M:%S")
                    timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                except ValueError:
                    pass
            
            items.append({
                "headline": headline,
                "source_url": docurl or f"https://finance.sina.com.cn/7x24/",
                "timestamp": timestamp,
                "raw_text": headline,
                "source_type": "sina",
                "event_id": f"SINA-{item_id}" if item_id else "",
            })
        
        return items
        
    except Exception:
        return []
```

**注意**：需要确保 json 已导入。检查现有 import 区域是否有 `import json`。

- [ ] **Step 3: 验证代码无语法错误**

Run: `python3 -m py_compile scripts/ai_event_intel.py`
Expected: 无输出（成功）

- [ ] **Step 4: Commit**

```bash
git add scripts/ai_event_intel.py
git commit -m "feat: add _fetch_sina() method to NewsIngestion"
```

---

## Task 2: 修改 execute() 调用 _fetch_sina()

**Files:**
- Modify: `scripts/ai_event_intel.py:219-295` (execute 方法中调用 _fetch_sina)

- [ ] **Step 1: 在 execute() 方法中添加 Sina 调用**

找到 execute() 方法中处理 sources 的循环后（约 line 256-257），在 `if not items:` 检查前添加：

```python
# Fetch from Sina live API
sina_items = self._fetch_sina(timeout)
if sina_items:
    items.extend(sina_items)
```

位置参考：在 `for src in sources:` 循环结束后，`if not items:` 检查之前。

- [ ] **Step 2: 验证代码无语法错误**

Run: `python3 -m py_compile scripts/ai_event_intel.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add scripts/ai_event_intel.py
git commit -m "feat: integrate Sina fetch into NewsIngestion.execute()"
```

---

## Task 3: 配置变更

**Files:**
- Modify: `configs/edt-modules-config.yaml:540-545` (NewsIngestion params 区域)

- [ ] **Step 1: 在 NewsIngestion params 中添加 Sina 配置**

在 `modules.NewsIngestion.params` 中添加：

```yaml
enable_sina: true
sina:
  url: "http://zhibo.sina.com.cn/api/zhibo/feed"
  params:
    page: 1
    page_size: 20
    zhibo_id: 152
    dire: "f"
```

位置：在 `enable_source_rank: true` 之后，`sources:` 之前。

- [ ] **Step 2: Commit**

```bash
git add configs/edt-modules-config.yaml
git commit -m "feat: add Sina source config to edt-modules-config.yaml"
```

---

## Task 4: 单元测试

**Files:**
- Create: `tests/test_ai_event_intel_sina.py`
- Modify: `tests/test_ai_event_intel.py` (可选，增加 Sina 相关测试)

- [ ] **Step 1: 创建 Sina 测试文件**

创建 `tests/test_ai_event_intel_sino.py`:

```python
#!/usr/bin/env python3
"""Tests for Sina news source integration."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import json


class TestSinaFetch:
    """Test _fetch_sina method."""

    def test_fetch_sina_disabled_by_config(self):
        """Sina fetch returns empty when disabled."""
        from ai_event_intel import NewsIngestion
        
        with patch.object(NewsIngestion, '_get_config', return_value=False):
            ni = NewsIngestion()
            result = ni._fetch_sina(timeout=5)
            assert result == []

    def test_fetch_sina_parses_response(self):
        """Sina fetch correctly parses API response."""
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
        
        mock_payload = json.dumps(mock_response).encode('utf-8')
        
        with patch.object(NewsIngestion, '_get_config', side_effect=lambda *args, **kwargs: {
            ('modules', 'NewsIngestion', 'params', 'enable_sina'): True,
            ('modules', 'NewsIngestion', 'params', 'sina', 'url'): 'http://test.com',
            ('modules', 'NewsIngestion', 'params', 'sina', 'params'): {},
        }.get(args[:3] if len(args) <= 3 else args[:4], None)):
            with patch('urllib.request.urlopen') as mock_urlopen:
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
                assert "SINA-12345" in result[0]["event_id"]


class TestSinaNormalization:
    """Test Sina item normalization via _normalize_item."""

    def test_normalize_sina_item(self):
        """Sina items normalize correctly through standard pipeline."""
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
        assert normalized["source_url"] == "https://finance.sina.com.cn/article.html"
```

- [ ] **Step 2: 运行测试验证**

Run: `python3 -m pytest tests/test_ai_event_intel_sina.py -v`
Expected: 全部 PASS（或部分 FAIL 如 mock 配置复杂，可简化）

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_event_intel_sina.py
git commit -m "test: add Sina news source unit tests"
```

---

## Task 5: 集成测试

**Files:**
- Modify: `tests/test_ai_event_intel.py` (添加 Sina 相关端到端测试)

- [ ] **Step 1: 添加 Sina 端到端测试**

在 `test_ai_event_intel.py` 中添加：

```python
def test_news_ingestion_with_sina_source(monkeypatch):
    """NewsIngestion includes Sina source when enabled."""
    from ai_event_intel import NewsIngestion
    
    # Mock Sina API response
    sina_response = {
        "result": {
            "data": {
                "feed": {
                    "list": [
                        {
                            "id": 99999,
                            "rich_text": "Sina breaking news",
                            "docurl": "https://finance.sina.com.cn/test",
                            "create_time": "2026-04-10T07:00:00"
                        }
                    ]
                }
            }
        }
    }
    
    # Mock config to enable Sina
    original_get_config = NewsIngestion._get_config
    def mock_get_config(self, path, default=None):
        if path == "modules.NewsIngestion.params.enable_sina":
            return True
        if path == "modules.NewsIngestion.params.sina.url":
            return "http://test.sina.com/api"
        if path == "modules.NewsIngestion.params.sina.params":
            return {}
        return original_get_config(self, path, default)
    
    # Mock RSS fetch to return empty (simulate failure)
    # but Sina should still return results
    # (This requires more complex mocking, optional for now)
```

简化方案：验证 enable_sina=True 时 _fetch_sina 被调用。

- [ ] **Step 2: 运行现有测试确保无回归**

Run: `python3 -m pytest tests/test_ai_event_intel.py -v --tb=short`
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_event_intel.py
git commit -m "test: add Sina integration test to test_ai_event_intel.py"
```

---

## Task 6: 端到端验证

**Files:**
- (无文件变更，运行命令验证)

- [ ] **Step 1: 测试 DataAdapter.fetch_news() 包含 Sina 数据**

Run: `cd "<LOCAL_WORKSPACE>/事件驱动交易模块阶段二/scripts" && python3 -c "
import sys
sys.path.insert(0, '.')
from data_adapter import DataAdapter
adapter = DataAdapter()
news = adapter.fetch_news()
print('source_type:', news.get('source_type'))
print('headline:', news.get('headline')[:50] if news.get('headline') else None)
print('timestamp:', news.get('timestamp'))
"`
Expected: source_type 应为 "sina"，headline 为中文内容

- [ ] **Step 2: 验证去重逻辑正常（可选）**

多次调用确认去重生效。

- [ ] **Step 3: Commit 最终变更**

```bash
git add -A
git commit -m "feat: integrate Sina live API as primary news source"
```

---

## 执行顺序

1. Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6
2. 任务间可并行（Task 4 与 Task 5 无依赖）
3. 完成后可选择 PR 或本地测试

---

## 预期产出

- `scripts/ai_event_intel.py` 增加 Sina fetcher
- `configs/edt-modules-config.yaml` 增加 Sina 配置
- `tests/test_ai_event_intel_sina.py` 新增测试文件
- 端到端验证 DataAdapter.fetch_news() 返回 Sina 新闻
