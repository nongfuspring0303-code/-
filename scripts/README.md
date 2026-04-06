# 项目守卫 (Project Guard)

一个最小可运行的体检工具，用于检查项目问题并安全修复。

## 🎯 设计原则

- **最小可运行** - 只做必要的检查，不做复杂平台
- **保守安全** - 不确定时不修复，拿不准就标记为建议
- **高效准确** - 准确率优先于覆盖率

## 🚀 快速开始

### 安装依赖
```bash
# 只需要Python标准库和PyYAML
pip install PyYAML
```

### 运行检查
```bash
# 1. 干运行模式（只检查不修改）
python3 scripts/guard.py --mode dry-run

# 2. 安全修复模式（修复低风险问题）
python3 scripts/guard.py --mode fix-safe

# 3. 严格模式（有高风险问题就失败）
python3 scripts/guard.py --mode strict
```

### 命令行选项
```bash
python3 scripts/guard.py --help

选项:
  --mode {dry-run,fix-safe,strict}  运行模式 (默认: dry-run)
  --project-root PROJECT_ROOT        项目根目录 (默认: .)
  --output OUTPUT                    报告输出路径 (默认: logs/guard_report.json)
  --no-console                       不在控制台显示报告
```

## 📁 文件说明

```
scripts/
├── guard.py          # 主程序：scan->judge->fix_safe->validate->report
├── utils.py          # 工具函数：备份、恢复、验证
├── config.yaml       # 工具配置
├── rules.yaml        # 检查规则定义
├── policy_map.yaml   # 修复策略映射
└── README.md         # 本文件
```

## 🔍 检查范围（第一版）

### 1. 关键文件存在性检查
- `configs/edt-modules-config.yaml` - 核心模块配置
- `configs/sector_impact_mapping.yaml` - 板块影响映射
- `configs/premium_stock_pool.yaml` - 优质股票池
- `阶段三任务分工说明.md` - 项目分工文档
- `module-registry.yaml` - 模块注册表

### 2. 关键配置键完整性检查
- 必需模块配置（EventCapture, SourceRanker, SignalScorer）
- timeout配置检查
- enabled配置检查

### 3. 工作流关键链路检查
- retry机制Schema存在性
- fallback机制配置检查
- safe-stop机制检查

### 4. Schema文件存在性检查
- `event_update.yaml` - 事件更新Schema
- `sector_update.yaml` - 板块更新Schema
- `opportunity_update.yaml` - 机会更新Schema
- `risk_gatekeeper.json` - 风险门控Schema

### 5. 最小日志字段检查
- timestamp字段存在性
- status字段存在性
- 审计日志文件存在性

### 6. 敏感信息检查
- API密钥硬编码检测
- 密钥硬编码检测
- 密码硬编码检测
- 令牌硬编码检测

## 🚦 问题分级

### 红灯（阻断）
- 安全风险（敏感信息泄露）
- 关键文件缺失
- 关键链路缺失
- **不自动修复**

### 黄灯（建议）
- 最佳实践缺失
- 可优化项
- 非关键问题
- **不自动修复**

### 绿灯（低风险）
- 配置键缺失（有安全默认值）
- 日志字段缺失
- 文档路径错误
- **可自动修复**

## 🔧 自动修复策略

### 允许修复的问题
1. **配置键缺失** - 添加安全默认值
   - 模块配置缺失：添加enabled=true, timeout=30
   - timeout配置缺失：添加timeout=30

2. **日志字段缺失** - 提供修复建议
   - timestamp字段缺失：建议添加ISO8601格式时间戳
   - status字段缺失：建议添加状态字段

3. **日志文件缺失** - 创建初始文件
   - 创建`logs/execution_audit.jsonl`初始文件

### 禁止修复的问题
- 核心制度文件
- 工作流主逻辑
- 敏感配置
- 权限/认证逻辑
- 生产脚本
- 数据结构
- 数据库迁移文件

## ✅ 最小验证

修复后自动执行：
1. **程序可启动** - 尝试导入核心模块
2. **配置可读取** - 验证配置文件格式
3. **报告可输出** - 验证报告生成能力
4. **strict模式验证** - 验证红灯问题会导致失败

## 📊 报告格式

### JSON报告 (`logs/guard_report.json`)
```json
{
  "timestamp": "2026-04-06T10:45:00Z",
  "overall_status": "PASS|WARN|FAIL",
  "statistics": {
    "red": 0,
    "yellow": 2,
    "green": 1,
    "fixed": 1
  },
  "issues_by_level": {...},
  "fixes_applied": [...],
  "unfixed_high_risk": [...],
  "validation": {
    "program_startup": true,
    "config_readable": true,
    "report_output": true,
    "strict_mode_fails_on_red": true
  },
  "integration_test": "not_run",
  "conclusion": "一句话结论"
}
```

### 人类可读报告 (`logs/guard_report.txt`)
```
============================================================
项目守卫报告 - 2026-04-06T10:45:00Z
============================================================

📊 总体状态: WARN
   红灯: 0 | 黄灯: 2 | 绿灯: 1
   已修复: 1

✅ 最小验证:
   program_startup: 通过
   config_readable: 通过
   report_output: 通过
   strict_mode_fails_on_red: 通过

💡 结论: 项目有 2 个建议改进项，1 个问题已自动修复
============================================================
```

## 🛡️ 安全机制

### 备份与恢复
- 修复前自动备份原文件（添加`.guard_backup`后缀）
- 修复失败时自动恢复
- 修复成功后可选清理备份

### 安全限制
- 最大修复文件数：10个
- 最大修复大小：10KB
- 禁止修复保护目录：`tests/`, `schemas/`, `configs/`
- 需要确认的修复：模块配置、日志文件创建

## 🧪 测试示例

### 1. dry-run 示例（只检查不修改）
```bash
$ python3 scripts/guard.py --mode dry-run

🔍 开始扫描项目...
⚖️  问题分级...
⏭️  干运行模式，跳过修复
✅ 最小验证...
📊 生成报告...

🚨 最上层一眼决策区
============================================================
最终状态: FAIL
是否允许继续推进: 不允许
红灯数量: 2
黄灯数量: 0
已自动修复数量: 0
一句话结论: 项目存在 2 个高风险问题，需要立即处理
============================================================

📋 详细报告
------------------------------------------------------------
📊 总体状态: FAIL
   红灯: 2 | 黄灯: 0 | 绿灯: 6
   已修复: 0

✅ 最小验证:
   program_startup: 通过
   config_readable: 通过
   report_output: 通过
   strict_mode_fails_on_red: 通过

🚨 高风险未修复项 (2 个):
   • 可能包含敏感信息: API密钥
   • 可能包含敏感信息: API密钥

💡 结论: 项目存在 2 个高风险问题，需要立即处理
============================================================
✅ 报告已保存: logs/guard_report.json
```

### 2. strict 示例（有红灯就失败）
```bash
$ python3 scripts/guard.py --mode strict

🔍 开始扫描项目...
⚖️  问题分级...
⏭️  干运行模式，跳过修复
✅ 最小验证...
📊 生成报告...

🚨 最上层一眼决策区
============================================================
最终状态: FAIL
是否允许继续推进: 不允许
红灯数量: 2
黄灯数量: 0
已自动修复数量: 0
一句话结论: 项目存在 2 个高风险问题，需要立即处理
============================================================

📋 详细报告
------------------------------------------------------------
📊 总体状态: FAIL
   红灯: 2 | 黄灯: 0 | 绿灯: 6
   已修复: 0

✅ 最小验证:
   program_startup: 通过
   config_readable: 通过
   report_output: 通过
   strict_mode_fails_on_red: 通过

🚨 高风险未修复项 (2 个):
   • 可能包含敏感信息: API密钥
   • 可能包含敏感信息: API密钥

💡 结论: 项目存在 2 个高风险问题，需要立即处理
============================================================
✅ 报告已保存: logs/guard_report.json

🚨 strict模式: 检测到高风险问题，退出码为1
$ echo $?
1
```

### 3. 其他运行模式
```bash
# 安全修复模式
python3 scripts/guard.py --mode fix-safe

# 指定项目目录
python3 scripts/guard.py --project-root /path/to/project --mode dry-run

# 自定义输出路径
python3 scripts/guard.py --output reports/my_report.json --no-console
```

### 2. 安全修复模式
```bash
python3 scripts/guard.py --mode fix-safe
```
自动修复低风险问题，并生成报告。

### 3. 严格模式
```bash
python3 scripts/guard.py --mode strict
```
有红灯问题时退出码为1，适合CI/CD集成。

### 4. 指定项目目录
```bash
python3 scripts/guard.py --project-root /path/to/project --mode dry-run
```

### 5. 自定义输出路径
```bash
python3 scripts/guard.py --output reports/my_report.json --no-console
```

## 🔄 集成到工作流

### CI/CD 集成
```yaml
# GitHub Actions 示例
- name: 项目体检
  run: python3 scripts/guard.py --mode strict
```

### 预提交钩子
```bash
#!/bin/bash
# .git/hooks/pre-commit
python3 scripts/guard.py --mode dry-run --no-console
if [ $? -ne 0 ]; then
  echo "❌ 项目检查失败，请先修复问题"
  exit 1
fi
```

### 定期检查
```bash
# 每天运行一次
0 9 * * * cd /path/to/project && python3 scripts/guard.py --mode fix-safe --no-console
```

## ⚠️ 当前版本限制

### 未覆盖的风险点
1. **运行时行为验证** - 只检查静态配置，不验证实际运行
2. **数据一致性检查** - 不验证数据库/缓存一致性
3. **性能基准测试** - 不检查性能指标

### 下一步最值得补的3条规则
1. **依赖版本兼容性检查** - 验证Python包版本兼容性
2. **API端点健康检查** - 验证Web服务可用性
3. **数据流完整性检查** - 验证A→B→C模块数据流

## 📝 版本历史

### v1.0 (2026-04-06)
- 初始版本：最小可运行体检工具
- 支持三种模式：dry-run, fix-safe, strict
- 6个核心检查类别
- 安全修复机制（备份+恢复）
- 最小验证和报告生成

## 📄 许可证

项目内部使用工具，遵循项目原有许可证。

## 🆘 故障排除

### 常见问题
1. **导入错误**：确保在项目根目录运行
2. **YAML解析错误**：检查配置文件格式
3. **权限错误**：确保对项目文件有读写权限

### 调试模式
```bash
# 查看详细日志
python3 -c "import guard; g = guard.ProjectGuard('.'); print(g.scan())"
```

### 清理备份文件
```bash
python3 -c "from utils import cleanup_backups; from pathlib import Path; print(f'清理了 {cleanup_backups(Path(\".\"))} 个备份文件')"
```