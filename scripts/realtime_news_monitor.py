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
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        self.api_url = api_url or "http://127.0.0.1:8787"
        self.last_news_signature = ""  # 用于检测新新闻
        self._load_news_module()
    
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
    
    def _process_news(self, news: Dict[str, Any]) -> bool:
        """处理单条新闻，返回是否触发成功"""
        if not self.event_capture:
            return False
        
        try:
            result = self.event_capture.run(news)
            captured = result.data.get("captured", False)
            
            if captured:
                logger.info(f"📰 新闻触发: {news.get('headline', '')[:50]}...")
                logger.info(f"   - 关键词匹配: {result.data.get('matched_keywords', [])}")
                logger.info(f"   - VIX放大: {result.data.get('vix_amplify', False)}")
                
                self._trigger_ab_pipeline(news)
                return True
            else:
                logger.debug(f"📰 新闻未触发: {news.get('headline', '')[:50]}...")
                return False
                
        except Exception as e:
            logger.error(f"处理新闻失败: {e}")
            return False
    
    def _trigger_ab_pipeline(self, news: Dict[str, Any]):
        """触发A/B计算流水线"""
        if not self.workflow:
            logger.warning("⚠️ Workflow未加载，跳过A/B计算")
            return
        
        try:
            logger.info("🔄 触发A/B计算...")
            
            payload = {
                "headline": news.get("headline"),
                "source": news.get("source_url"),
                "timestamp": news.get("timestamp"),
                "vix": news.get("metadata", {}).get("vix_level", 20),
                "vix_change_pct": 0,
                "spx_move_pct": 0,
                "sector_move_pct": 0,
                "sequence": 1,
            }
            
            result = self.workflow.run(payload)
            
            if "intel" in result and "analysis" in result:
                logger.info("✅ A/B计算完成")
                sectors = result.get("analysis", {}).get("conduction", {}).get("sector_impacts", [])
                opportunities = result.get("opportunities", [])
                logger.info(f"   - 板块数: {len(sectors)}")
                logger.info(f"   - 机会数: {len(opportunities)}")
                self._push_sectors_to_c(result)
            else:
                logger.warning(f"⚠️ A/B计算异常: {result}")
                
        except Exception as e:
            logger.error(f"A/B计算失败: {e}")
    
    def _push_sectors_to_c(self, result: Dict[str, Any]):
        """推送板块和机会到C模块"""
        if not self.api_url:
            return
        
        try:
            from datetime import datetime, timezone
            
            analysis = result.get("analysis", {})
            intel = result.get("intel", {})
            event_object = intel.get("event_object", {})
            ts = datetime.now(timezone.utc).isoformat()
            trace_id = event_object.get("event_id", "unknown")
            
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
                "trace_id": trace_id,
                "schema_version": "v1.0",
                "sectors": sectors,
                "conduction_chain": [],
                "timestamp": ts,
            }
            
            import urllib.request
            
            # 推送 sector-update
            endpoint = f"{self.api_url}/api/ingest/sector-update"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info(f"✅ 推送板块到C模块成功")
            
            # 推送 event-update
            event_data = {
                "trace_id": trace_id,
                "schema_version": "v1.0",
                "headline": event_object.get("headline", "A/B 实时计算事件"),
                "source": event_object.get("source_url", "A-Module"),
                "severity": event_object.get("severity", "E3"),
                "evidence_score": 0,
                "narrative_state": "Fact-Driven",
                "timestamp": ts,
            }
            
            endpoint = f"{self.api_url}/api/ingest/event-update"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(event_data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info(f"✅ 推送事件到C模块成功")
            
            # 推送 opportunity-update
            opportunities = analysis.get("opportunity_update", {}).get("opportunities", [])
            if opportunities:
                opp_data = {
                    "trace_id": trace_id,
                    "schema_version": "v1.0",
                    "opportunities": opportunities,
                    "timestamp": ts,
                }
                
                endpoint = f"{self.api_url}/api/ingest/opportunity-update"
                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(opp_data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ 推送机会到C模块成功")
                    
        except Exception as e:
            logger.error(f"推送失败: {e}")
    
    def _push_to_c_module(self, data: Dict[str, Any], api_url: str):
        """推送到C模块"""
        try:
            import urllib.request
            
            endpoint = f"{api_url}/api/ingest/sector-update"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
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
            logger.info("📭 未获取到新闻")
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


def main():
    parser = argparse.ArgumentParser(description="实时新闻监控")
    parser.add_argument(
        "--poll-interval", 
        type=int, 
        default=60,
        help="轮询间隔（秒），默认60秒"
    )
    parser.add_argument(
        "--api",
        type=str,
        default="http://127.0.0.1:8787",
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