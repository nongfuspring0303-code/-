"""
测试混合股票池功能（静态核心池 + 动态补充池）
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.opportunity_score import PremiumStockPool


def test_hybrid_pool_initialization():
    """测试混合股票池初始化"""
    print("\n=== 测试混合股票池初始化 ===")
    
    pool = PremiumStockPool()
    
    # 检查静态池
    static_count = len(pool._static_stocks_by_symbol)
    print(f"✓ 静态核心池股票数量: {static_count}")
    
    # 检查动态池
    dynamic_count = len(pool._dynamic_stocks_by_symbol)
    print(f"✓ 动态补充池股票数量: {dynamic_count}")
    
    # 检查合并后的总池
    total_count = len(pool._stocks_by_symbol)
    print(f"✓ 合并后总股票数量: {total_count}")
    
    # 验证合并逻辑
    expected_total = len({**pool._dynamic_stocks_by_symbol, **pool._static_stocks_by_symbol})
    assert total_count == expected_total, f"合并池数量不匹配: {total_count} != {expected_total}"
    print(f"✓ 合并逻辑验证通过")
    
    return pool


def test_stock_source_detection(pool: PremiumStockPool):
    """测试股票来源检测"""
    print("\n=== 测试股票来源检测 ===")
    
    # 测试静态池股票
    nvda = pool.get_stock("NVDA")
    if nvda:
        source = pool.get_stock_source("NVDA")
        print(f"✓ NVDA 来源: {source}")
        assert source == "static", f"NVDA 应该来自静态池，但检测到: {source}"
    
    # 测试动态池股票（假设 AAPL 在动态池中）
    aapl = pool.get_stock("AAPL")
    if aapl:
        source = pool.get_stock_source("AAPL")
        print(f"✓ AAPL 来源: {source}")
        if aapl.price_source == "dynamic_cache":
            assert source == "dynamic", f"AAPL 应该来自动态池，但检测到: {source}"
    
    # 测试不存在的股票
    unknown_source = pool.get_stock_source("UNKNOWN")
    print(f"✓ UNKNOWN 来源: {unknown_source}")
    assert unknown_source == "unknown", f"未知股票应该返回 'unknown'，但检测到: {unknown_source}"


def test_ai_recommendation_coverage(pool: PremiumStockPool):
    """测试 AI 推荐股票的覆盖情况"""
    print("\n=== 测试 AI 推荐股票覆盖 ===")
    
    # 模拟 AI 推荐的股票列表
    ai_recommendations = ["NVDA", "AAPL", "MSFT", "TSLA", "AMD", "INTC", "QCOM", "META", "GOOGL", "AMZN"]
    
    covered = 0
    static_covered = 0
    dynamic_covered = 0
    
    for symbol in ai_recommendations:
        stock = pool.get_stock(symbol)
        if stock:
            covered += 1
            source = pool.get_stock_source(symbol)
            if source == "static":
                static_covered += 1
            elif source == "dynamic":
                dynamic_covered += 1
            print(f"  ✓ {symbol}: {source}")
        else:
            print(f"  ✗ {symbol}: 未找到")
    
    coverage_rate = (covered / len(ai_recommendations)) * 100
    print(f"\n覆盖统计:")
    print(f"  总推荐数: {len(ai_recommendations)}")
    print(f"  已覆盖: {covered}")
    print(f"  覆盖率: {coverage_rate:.1f}%")
    print(f"  静态池覆盖: {static_covered}")
    print(f"  动态池覆盖: {dynamic_covered}")


def test_filter_candidates_with_hybrid_pool(pool: PremiumStockPool):
    """测试使用混合池过滤候选股票"""
    print("\n=== 测试混合池候选过滤 ===")
    
    # 模拟候选股票列表（包含静态和动态股票）
    candidates = [
        {"symbol": "NVDA"},  # 静态池
        {"symbol": "AAPL"},  # 可能是动态池
        {"symbol": "UNKNOWN"},  # 不存在
        {"symbol": "MSFT"},  # 静态池
        {"symbol": "INTC"},  # 可能是动态池
    ]
    
    filtered = pool.filter_candidates(candidates)
    
    print(f"输入候选数: {len(candidates)}")
    print(f"过滤后数量: {len(filtered)}")
    
    for stock in filtered:
        source = pool.get_stock_source(stock.symbol)
        print(f"  ✓ {stock.symbol}: {source}, ROE={stock.roe:.1f}%, 市值={stock.market_cap_billion:.0f}B")


def test_pool_statistics(pool: PremiumStockPool):
    """测试股票池统计信息"""
    print("\n=== 股票池统计信息 ===")
    
    print(f"总股票数: {len(pool._stocks_by_symbol)}")
    print(f"静态池: {len(pool._static_stocks_by_symbol)}")
    print(f"动态池: {len(pool._dynamic_stocks_by_symbol)}")
    
    # 统计不同价格来源的股票
    price_sources = {}
    for stock in pool._stocks_by_symbol.values():
        source = stock.price_source
        price_sources[source] = price_sources.get(source, 0) + 1
    
    print(f"\n价格来源分布:")
    for source, count in price_sources.items():
        print(f"  {source}: {count}")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("混合股票池功能测试")
    print("=" * 60)
    
    try:
        # 初始化混合股票池
        pool = test_hybrid_pool_initialization()
        
        # 测试股票来源检测
        test_stock_source_detection(pool)
        
        # 测试 AI 推荐覆盖
        test_ai_recommendation_coverage(pool)
        
        # 测试候选过滤
        test_filter_candidates_with_hybrid_pool(pool)
        
        # 统计信息
        test_pool_statistics(pool)
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()