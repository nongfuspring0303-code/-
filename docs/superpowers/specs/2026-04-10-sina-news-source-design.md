# Sina 直播 API 接入设计

## 目标

将新浪财经直播 API (`zhibo.sina.com.cn`) 作为主新闻源之一接入 NewsIngestion，补充现有 RSS 源，提供更低延迟的中文财经实时资讯。

## 背景

- 现有 RSS 源延迟较高（分钟级）
- 实测 Sina 直播 API 延迟低（秒级）， freshness_lag < 300s
- 需要与现有去重/归一化逻辑集成

## 设计

### 架构

```
NewsIngestion.execute()
    ├── 现有逻辑：遍历 RSS sources → _parse_rss / _parse_atom
    └── 新增：_fetch_sina() → 返回标准化 items
    └── 合并 → 去重 → 返回
```

### 字段映射

| Sina 字段 | 新闻对象字段 |
|-----------|-------------|
| `rich_text` | `headline` / `raw_text` |
| `docurl` | `source_url` |
| `create_time` | `timestamp` (转 ISO 8601) |
| `id` | `event_id` |
| `zhibo_id=152` | 固定财经直播 |

### 配置变更

在 `edt-modules-config.yaml` 的 `NewsIngestion.params` 中添加：

```yaml
enable_sina: true
sina:
  url: "http://zhibo.sina.com.cn/api/zhibo/feed"
  params:
    page: 1
    page_size: 20
    zhibo_id: 152
    dire: "f"
  headers:
    User-Agent: "Mozilla/5.0"
    Referer: "http://finance.sina.com.cn/7x24/"
```

### 优先级

- Sina 源优先于 RSS 源（延迟更低）
- 与 RSS 源一起跨源去重

## 实现计划

1. 在 `ai_event_intel.py` 添加 `_fetch_sina()` 方法
2. 修改 `execute()` 调用 `_fetch_sina()` 并合并结果
3. 添加单元测试验证字段映射
4. 更新配置示例

## 风险

- Sina API 可能返回非财经内容（需依赖下游 keyword 过滤）
- 无 API key，但为公开接口，风险可控