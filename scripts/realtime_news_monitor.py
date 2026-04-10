#!/usr/bin/env python3
"""
Real-time News Monitor for EDT Project
实时新闻监控 - 检测到新闻后立即触发A/B计算并推送

功能：
1. 持续轮询新闻源
2. 检测新新闻后立即触发EventCapture
3. 触发后立即运行A/B计算并推送到C模块
4. 支持配置轮询间隔
"""

import argparse
import asyncio
import hashlib
import json
import os
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

try:
    from googletrans import Translator
except Exception:  # 非官方库，可能不可用
    Translator = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _default_config_path() -> str:
    return str(ROOT / "configs" / "edt-modules-config.yaml")


class RealtimeNewsMonitor:
    def __init__(self, config_path: Optional[str] = None, poll_interval: int = 60, api_url: Optional[str] = None):
        self.config_path = config_path or _default_config_path()
        self.poll_interval = poll_interval
        api_port = os.getenv("EDT_API_PORT", "18787")
        self.api_url = api_url or f"http://127.0.0.1:{api_port}"
        if api_url and api_port not in str(api_url):
            logger.warning("⚠️ api_url port mismatch: env=%s api_url=%s", api_port, api_url)
        self.node_role = self._load_node_role()
        self.master_api = self._load_master_api()
        self.last_news_signature = ""  # 用于检测新新闻
        self.translator = Translator() if Translator else None
        if not self.translator:
            logger.warning("⚠️ googletrans 不可用，中文翻译将跳过")
        self._load_news_module()

    def _load_node_role(self) -> str:
        env_role = os.getenv("EDT_NODE_ROLE", "").strip().lower()
        if env_role:
            return env_role
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                payload = yaml.safe_load(f) or {}
            runtime = payload.get("runtime", {}) if isinstance(payload, dict) else {}
            role = str(runtime.get("node_role", "master")).strip().lower()
            return role or "master"
        except Exception:
            return "master"

    def _load_master_api(self) -> str:
        env_master = os.getenv("EDT_MASTER_API", "").strip()
        if env_master:
            return env_master
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                payload = yaml.safe_load(f) or {}
            runtime = payload.get("runtime", {}) if isinstance(payload, dict) else {}
            master = str(runtime.get("master_api", "")).strip()
            return master
        except Exception:
            return ""

    def _can_publish_main_chain(self) -> bool:
        return self.node_role != "worker"

    def _forward_to_master(self, payload: Dict[str, Any], endpoint_suffix: str) -> bool:
        if not self.master_api:
            logger.warning("⚠️ worker 未配置 master_api，无法转发主链")
            return False
        try:
            import urllib.request
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            endpoint = f"{self.master_api}{endpoint_suffix}"
            req = urllib.request.Request(endpoint, data=data, headers=self._c_ingest_headers(), method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 202)
        except Exception as e:
            logger.warning("⚠️ 转发 master 失败: %s", e)
            return False
    
    def _load_news_module(self):
        try:
            from intel_modules import EventCapture
            from data_adapter import DataAdapter
            from full_workflow_runner import FullWorkflowRunner
            self.event_capture = EventCapture(self.config_path)
            self.data_adapter = DataAdapter()
            self.workflow = FullWorkflowRunner()
            logger.info("✅ 模块加载成功")
        except ImportError as e:
            logger.warning(f"⚠️ 模块导入失败: {e}")
            self.event_capture = None
            self.data_adapter = None
            self.workflow = None
    
    def _fetch_latest_news(self) -> List[Dict[str, Any]]:
        if not self.data_adapter:
            return []
        
        try:
            result = self.data_adapter.fetch_news()
            return [result] if result else []
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return []
    
    def _get_news_signature(self, news: Dict[str, Any]) -> str:
        """生成新闻签名用于检测重复"""
        headline = news.get("headline", "")
        timestamp = news.get("timestamp", "")
        return f"{headline}|{timestamp}"

    def _translate_headline(self, headline: str) -> Optional[str]:
        """翻译标题为中文（非官方库，失败即跳过）"""
        if not headline or not self.translator:
            return None
        try:
            result = self.translator.translate(headline, dest="zh-cn")
            return result.text if result else None
        except Exception as e:
            logger.warning(f"⚠️ 翻译失败: {e}")
            return None

    def _c_ingest_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-EDT-Token": os.getenv("EDT_API_TOKEN", os.getenv("EDT_WS_TOKEN", "edt-local-dev-token")),
        }
    
    def _process_news(self, news: Dict[str, Any]) -> bool:
        """处理单条新闻，返回是否触发成功"""
        if not self.event_capture:
            return False

        metadata = news.get("metadata", {})
        source_type = str(news.get("source_type", "")).lower()
        if (
            metadata.get("is_test_data")
            or bool(news.get("is_test_data"))
            or source_type in {"fallback", "failed"}
        ):
            logger.warning(
                "⚠️ 跳过非实盘新闻，避免触发下游: source_type=%s metadata.is_test_data=%s is_test_data=%s",
                source_type or "unknown",
                bool(metadata.get("is_test_data")),
                bool(news.get("is_test_data")),
            )
            return False

        # 新闻展示与触发解耦：先推送预览，再补充AI语义结果
        self._push_news_preview(news)
        
        try:
            result = self.event_capture.run(news)
            captured = result.data.get("captured", False)
            self._push_news_preview(
                news,
                ai_verdict=result.data.get("ai_verdict", ""),
                ai_confidence=result.data.get("ai_confidence", 0),
                ai_reason=result.data.get("ai_reason", ""),
            )
            
            if captured:
                logger.info(f"📰 新闻触发: {news.get('headline', '')[:50]}...")
                logger.info(f"   - 关键词匹配: {result.data.get('matched_keywords', [])}")
                logger.info(f"   - VIX放大: {result.data.get('vix_amplify', False)}")
                
                self._trigger_ab_pipeline(news, publish_event_update=False)
                return True
            else:
                logger.debug(f"📰 新闻未触发: {news.get('headline', '')[:50]}...")
                return False
                
        except Exception as e:
            logger.error(f"处理新闻失败: {e}")
            return False
    
    def _trigger_ab_pipeline(self, news: Dict[str, Any], publish_event_update: bool = True):
        """触发A/B计算流水线"""
        if not self.workflow:
            logger.warning("⚠️ Workflow未加载，跳过A/B计算")
            return
        
        try:
            logger.info("🔄 触发A/B计算...")
            market = self.data_adapter.fetch_market_data() if self.data_adapter else {}

            def _num_or_default(value, default=0):
                try:
                    if value is None:
                        return default
                    return float(value)
                except (TypeError, ValueError):
                    return default
            
            payload = {
                "headline": news.get("headline"),
                "source": news.get("source_url"),
                "timestamp": news.get("timestamp"),
                "vix": _num_or_default(market.get("vix_level"), None),
                "vix_change_pct": _num_or_default(market.get("vix_change_pct"), None),
                "spx_move_pct": _num_or_default(market.get("spx_change_pct"), None),
                "sector_move_pct": _num_or_default(market.get("etf_volatility", {}).get("change_pct"), None),
                "sequence": 1,
            }
            
            result = self.workflow.run(payload)
            
            if "intel" in result and "analysis" in result:
                logger.info("✅ A/B计算完成")
                sectors = result.get("analysis", {}).get("conduction", {}).get("sector_impacts", [])
                opportunities = result.get("opportunities", [])
                logger.info(f"   - 板块数: {len(sectors)}")
                logger.info(f"   - 机会数: {len(opportunities)}")
                self._push_sectors_to_c(result, news=news, publish_event_update=publish_event_update)
            else:
                logger.warning(f"⚠️ A/B计算异常: {result}")
                
        except Exception as e:
            logger.error(f"A/B计算失败: {e}")
    
    def _push_sectors_to_c(self, result: Dict[str, Any], news: Optional[Dict[str, Any]] = None, publish_event_update: bool = True):
        """推送板块和机会到C模块"""
        if not self.api_url:
            return
        if not self._can_publish_main_chain():
            logger.info("⏭️ 当前节点为 worker，转发主链至 master")
            payload = result.get("analysis", {})
            if payload:
                self._forward_to_master(payload, "/api/ingest/sector-update")
            return
        
        try:
            from datetime import datetime, timezone
            
            analysis = result.get("analysis", {})
            intel = result.get("intel", {})
            event_object = intel.get("event_object", {})
            ai_verdict = intel.get("ai_verdict", "")
            ai_confidence = intel.get("ai_confidence", 0)
            ai_reason = intel.get("ai_reason", "")
            ts = datetime.now(timezone.utc).isoformat()
            trace_id = str(result.get("trace_id") or event_object.get("event_id", "unknown"))
            if not trace_id.startswith(("TRC-", "REQ-", "BATCH-", "evt_")):
                trace_id = f"TRC-{trace_id}"
            request_id = str(result.get("request_id") or trace_id)
            batch_id = str(result.get("batch_id") or f"BATCH-{request_id}")
            
            sectors = []
            for item in analysis.get("conduction", {}).get("sector_impacts", []):
                direction_raw = str(item.get("direction", "WATCH")).lower()
                if direction_raw in {"benefit", "long"}:
                    direction = "LONG"
                elif direction_raw in {"hurt", "short"}:
                    direction = "SHORT"
                else:
                    direction = "WATCH"
                    
                sectors.append({
                    "name": item.get("sector", "未知板块"),
                    "direction": direction,
                    "impact_score": round(min(1.0, max(0.0, float(analysis.get("conduction", {}).get("confidence", 0)) / 100.0)), 2),
                    "confidence": round(min(1.0, max(0.0, float(analysis.get("conduction", {}).get("confidence", 0)) / 100.0)), 2),
                })
            
            data = {
                "type": "sector_update",
                "trace_id": trace_id,
                "request_id": request_id,
                "batch_id": batch_id,
                "schema_version": "v1.0",
                "sectors": sectors,
                "conduction_chain": [],
                "timestamp": ts,
            }
            
            import urllib.request
            
            # 推送 sector-update
            if not self._can_publish_main_chain():
                self._forward_to_master(data, "/api/ingest/sector-update")
            else:
                endpoint = f"{self.api_url}/api/ingest/sector-update"
                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(data).encode("utf-8"),
                    headers=self._c_ingest_headers(),
                    method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ 推送板块到C模块成功")
            
            if publish_event_update:
                # 推送 event-update
                headline = event_object.get("headline", "A/B 实时计算事件")
                headline_cn = event_object.get("headline_cn") or self._translate_headline(headline)
                event_data = {
                    "type": "event_update",
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "batch_id": batch_id,
                    "schema_version": "v1.0",
                    "headline": headline,
                    "headline_cn": headline_cn,
                    "source": event_object.get("source_url", "A-Module"),
                    "source_type": (news or {}).get("source_type", event_object.get("source_type", "")),
                    "source_mode": (news or {}).get("source_mode", event_object.get("source_mode", "")),
                    "severity": event_object.get("severity", "E3"),
                    "evidence_score": 0,
                    "narrative_state": "Fact-Driven",
                    "news_timestamp": (
                        event_object.get("news_timestamp")
                        or event_object.get("published_at")
                        or event_object.get("detected_at")
                        or event_object.get("timestamp")
                    ),
                    "timestamp": ts,
                    "ai_verdict": ai_verdict,
                    "ai_confidence": ai_confidence,
                    "ai_reason": ai_reason,
                }

                if not self._can_publish_main_chain():
                    self._forward_to_master(event_data, "/api/ingest/event-update")
                else:
                    endpoint = f"{self.api_url}/api/ingest/event-update"
                    req = urllib.request.Request(
                        endpoint,
                        data=json.dumps(event_data).encode("utf-8"),
                        headers=self._c_ingest_headers(),
                        method="POST"
                    )

                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status == 200:
                            logger.info(f"✅ 推送事件到C模块成功")
            
            # 推送 opportunity-update
            opportunities = analysis.get("opportunity_update", {}).get("opportunities", [])
            if opportunities:
                opp_data = {
                    "type": "opportunity_update",
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "batch_id": batch_id,
                    "schema_version": "v1.0",
                    "opportunities": opportunities,
                    "timestamp": ts,
                }
                
                if not self._can_publish_main_chain():
                    self._forward_to_master(opp_data, "/api/ingest/opportunity-update")
                else:
                    endpoint = f"{self.api_url}/api/ingest/opportunity-update"
                    req = urllib.request.Request(
                        endpoint,
                        data=json.dumps(opp_data).encode("utf-8"),
                        headers=self._c_ingest_headers(),
                        method="POST"
                    )
                    
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status == 200:
                            logger.info(f"✅ 推送机会到C模块成功")
                    
        except Exception as e:
            logger.error(f"推送失败: {e}")

    def _push_news_preview(
        self,
        news: Dict[str, Any],
        ai_verdict: str = "",
        ai_confidence: float = 0,
        ai_reason: str = "",
    ) -> None:
        """Push lightweight event-update so UI can always display real news."""
        if not self.api_url:
            return

        trace_seed = str(news.get("event_id") or self._get_news_signature(news))
        trace_hash = hashlib.sha1(trace_seed.encode("utf-8", errors="ignore")).hexdigest()[:12]
        trace_id = f"evt_live_{trace_hash}"

        payload = {
            "type": "event_update",
            "trace_id": trace_id,
            "schema_version": "v1.0",
            "headline": news.get("headline", ""),
            "headline_cn": news.get("headline_cn") or self._translate_headline(news.get("headline", "")),
            "source": news.get("source_url", ""),
            "source_type": news.get("source_type", ""),
            "source_mode": news.get("source_mode", ""),
            "severity": "E1",
            "evidence_score": 0,
            "narrative_state": "News-Only",
            "news_timestamp": news.get("timestamp"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ai_verdict": ai_verdict,
            "ai_confidence": ai_confidence,
            "ai_reason": ai_reason,
        }

        try:
            import urllib.request

            if not self._can_publish_main_chain():
                self._forward_to_master(payload, "/api/ingest/event-update")
                return

            endpoint = f"{self.api_url}/api/ingest/event-update"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=self._c_ingest_headers(),
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info("✅ 推送新闻预览到C模块成功")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"⚠️ 推送新闻预览失败: {exc}")

    def _push_to_c_module(self, data: Dict[str, Any], api_url: str):
        """推送到C模块"""
        if not self._can_publish_main_chain():
            logger.info("⏭️ 当前节点为 worker，转发主链至 master")
            self._forward_to_master(data, "/api/ingest/sector-update")
            return
        try:
            import urllib.request
            
            endpoint = f"{api_url}/api/ingest/sector-update"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(data).encode("utf-8"),
                headers=self._c_ingest_headers(),
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info(f"✅ 推送成功: {endpoint}")
                else:
                    logger.warning(f"⚠️ 推送失败: {resp.status}")
                    
        except Exception as e:
            logger.error(f"推送失败: {e}")
    
    def run_once(self) -> bool:
        """运行一次检查"""
        news_list = self._fetch_latest_news()
        
        if not news_list:
            logger.warning("📭 新闻摄取为空，已跳过下游触发")
            return False
        
        latest_news = news_list[0]
        signature = self._get_news_signature(latest_news)
        
        if signature == self.last_news_signature:
            logger.debug("📭 无新新闻")
            return False
        
        self.last_news_signature = signature
        return self._process_news(latest_news)
    
    def run_loop(self, max_iterations: Optional[int] = None):
        """持续运行"""
        logger.info(f"🚀 启动实时新闻监控 (轮询间隔: {self.poll_interval}秒)")
        
        iterations = 0
        while True:
            try:
                triggered = self.run_once()
                if triggered:
                    logger.info("⏸️ 等待下一轮...")
            except KeyboardInterrupt:
                logger.info("🛑 用户中断")
                break
            except Exception as e:
                logger.error(f"循环异常: {e}")
            
            iterations += 1
            if max_iterations and iterations >= max_iterations:
                logger.info(f"达到最大迭代次数: {max_iterations}")
                break
            
            time.sleep(self.poll_interval)

    async def run_loop_async(self):
        """异步版本的持续运行"""
        logger.info(f"🚀 启动实时新闻监控 (轮询间隔: {self.poll_interval}秒)")
        
        while True:
            try:
                triggered = self.run_once()
                if triggered:
                    logger.info("⏸️ 等待下一轮...")
            except KeyboardInterrupt:
                logger.info("🛑 用户中断")
                break
            except Exception as e:
                logger.error(f"循环异常: {e}")
            
            await asyncio.sleep(self.poll_interval)


def main():
    parser = argparse.ArgumentParser(description="实时新闻监控")
    parser.add_argument(
        "--poll-interval", 
        type=int, 
        default=60,
        help="轮询间隔（秒），默认60秒"
    )
    default_api = f"http://127.0.0.1:{os.getenv('EDT_API_PORT', '18787')}"
    parser.add_argument(
        "--api",
        type=str,
        default=default_api,
        help="C模块API地址"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="最大迭代次数（用于测试）"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="仅运行一次检查"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="测试模式：只打印新闻，不触发A/B计算"
    )
    
    args = parser.parse_args()
    
    test_mode = getattr(args, 'test', False)
    monitor = RealtimeNewsMonitor(poll_interval=args.poll_interval, api_url=args.api)
    
    if args.once:
        monitor.run_once()
    else:
        monitor.run_loop(max_iterations=args.max_iterations)


if __name__ == "__main__":
    main()
