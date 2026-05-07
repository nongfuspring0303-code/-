# Local Daily Project Monitor Setup

## 概述
本系统提供了一个自动化的项目缺口扫描工具，用于每日检查代码契约与前端 DOM 的对齐状态。

## 使用方法
1. 确保已安装 Python 依赖：`pip install PyYAML`
2. 运行监控脚本：
   ```bash
   bash scripts/local_daily_project_monitor.sh
   ```
3. 查看结果：
   - 终端报告：`logs/project_gap_report.md`
   - JSON 数据：`logs/project_gap_report.json`
   - 运行日志：`logs/local_project_monitor.log`

## 安全性声明
- **只读运行**：脚本仅读取文件系统，严禁包含任何 `git commit`, `git push` 或 `gh pr create` 命令。
- **本地化**：所有产物保留在 `logs/` 目录，该目录已在 `.gitignore` 中排除。
