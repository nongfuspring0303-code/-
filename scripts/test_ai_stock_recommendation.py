#!/usr/bin/env python3
"""
测试AI股票推荐功能
"""
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ai_semantic_analyzer import SemanticAnalyzer
from scripts.conduction_mapper import ConductionMapper


def test_semantic_analyzer():
    """测试语义分析器的股票推荐功能"""
    print("=" * 60)
    print("测试 1: SemanticAnalyzer 股票推荐")
    print("=" * 60)
    
    analyzer = SemanticAnalyzer()
    
    # 测试用例 1: 降息新闻
    print("\n测试用例 1: 降息新闻")
    headline = "美联储宣布降息25个基点"
    result = analyzer.analyze(headline, "")
    print(f"事件类型: {result.get('event_type')}")
    print(f"情感: {result.get('sentiment')}")
    print(f"置信度: {result.get('confidence')}")
    print(f"推荐链: {result.get('recommended_chain')}")
    print(f"推荐股票: {result.get('recommended_stocks', [])}")
    
    # 测试用例 2: 财报新闻
    print("\n测试用例 2: 财报新闻")
    headline = "英伟达财报超预期，营收增长30%"
    result = analyzer.analyze(headline, "")
    print(f"事件类型: {result.get('event_type')}")
    print(f"情感: {result.get('sentiment')}")
    print(f"置信度: {result.get('confidence')}")
    print(f"推荐链: {result.get('recommended_chain')}")
    print(f"推荐股票: {result.get('recommended_stocks', [])}")
    
    # 测试用例 3: 关税新闻
    print("\n测试用例 3: 关税新闻")
    headline = "美国对中国加征关税"
    result = analyzer.analyze(headline, "")
    print(f"事件类型: {result.get('event_type')}")
    print(f"情感: {result.get('sentiment')}")
    print(f"置信度: {result.get('confidence')}")
    print(f"推荐链: {result.get('recommended_chain')}")
    print(f"推荐股票: {result.get('recommended_stocks', [])}")


def test_conduction_mapper_with_ai():
    """测试ConductionMapper的AI股票推荐合并功能"""
    print("\n" + "=" * 60)
    print("测试 2: ConductionMapper AI股票推荐合并")
    print("=" * 60)
    
    mapper = ConductionMapper()
    
    # 模拟股票池数据
    sector_data = [
        {
            "symbol": "NVDA",
            "name": "英伟达",
            "sector": "科技",
            "industry": "半导体",
            "roe_pct": 74.0,
            "market_cap_usd_billion": 2200,
            "liquidity_score": 0.95
        },
        {
            "symbol": "AAPL",
            "name": "苹果",
            "sector": "科技",
            "industry": "消费电子",
            "roe_pct": 160.0,
            "market_cap_usd_billion": 3000,
            "liquidity_score": 0.94
        },
        {
            "symbol": "MSFT",
            "name": "微软",
            "sector": "科技",
            "industry": "软件",
            "roe_pct": 39.0,
            "market_cap_usd_billion": 3000,
            "liquidity_score": 0.94
        },
        {
            "symbol": "CAT",
            "name": "卡特彼勒",
            "sector": "工业",
            "industry": "机械制造",
            "roe_pct": 42.0,
            "market_cap_usd_billion": 120,
            "liquidity_score": 0.88
        }
    ]
    
    # 测试用例 1: 降息新闻
    print("\n测试用例 1: 降息新闻（AI推荐 + 配置推荐）")
    input_data = {
        "event_id": "test-001",
        "category": "E",
        "headline": "美联储宣布降息25个基点，市场流动性宽松",
        "summary": "美联储宣布降息25个基点，将联邦基金利率目标区间下调至4.75%-5.00%",
        "severity": "E2",
        "lifecycle_state": "Active",
        "policy_intervention": "NONE",
        "sector_data": sector_data,
        "novelty_score": 0.8,
        "fatigue_final": 30.0,
        "schema_version": "v1.1"
    }
    
    from scripts.edt_module_base import ModuleInput
    result = mapper.execute(ModuleInput(raw_data=input_data))
    
    print(f"宏观因子: {result.data.get('macro_factors', [])}")
    print(f"板块影响: {result.data.get('sector_impacts', [])}")
    print(f"股票候选数量: {len(result.data.get('stock_candidates', []))}")
    print(f"AI增强: {result.data.get('ai_enhanced', False)}")
    print(f"AI推荐股票数: {result.data.get('ai_stocks_count', 0)}")
    print(f"配置推荐股票数: {result.data.get('config_stocks_count', 0)}")
    
    print("\n股票候选详情:")
    for stock in result.data.get('stock_candidates', []):
        source = stock.get('source', 'unknown')
        print(f"  - {stock.get('symbol')}: {stock.get('direction')} (来源: {source})")
        if source == 'ai':
            print(f"    AI置信度: {stock.get('ai_confidence', 0)}")
    
    # 测试用例 2: 财报新闻
    print("\n测试用例 2: 财报新闻（AI直接推荐NVDA）")
    input_data = {
        "event_id": "test-002",
        "category": "F",
        "headline": "英伟达财报超预期，营收增长30%，AI芯片需求旺盛",
        "summary": "英伟达公布财报，营收和净利润均超市场预期，数据中心业务增长强劲",
        "severity": "E3",
        "lifecycle_state": "Active",
        "policy_intervention": "NONE",
        "sector_data": sector_data,
        "novelty_score": 0.9,
        "fatigue_final": 20.0,
        "schema_version": "v1.1"
    }
    
    result = mapper.execute(ModuleInput(raw_data=input_data))
    
    print(f"股票候选数量: {len(result.data.get('stock_candidates', []))}")
    print(f"AI增强: {result.data.get('ai_enhanced', False)}")
    
    print("\n股票候选详情:")
    for stock in result.data.get('stock_candidates', []):
        source = stock.get('source', 'unknown')
        print(f"  - {stock.get('symbol')}: {stock.get('direction')} (来源: {source})")
        if source == 'ai':
            print(f"    AI置信度: {stock.get('ai_confidence', 0)}")


def main():
    """主测试函数"""
    print("开始测试AI股票推荐功能...")
    
    try:
        test_semantic_analyzer()
        test_conduction_mapper_with_ai()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())