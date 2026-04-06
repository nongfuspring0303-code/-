# 重大事件中期验收项目

## 项目定位
本项目用于构建与验证重大事件驱动相关模块的本地运行、监控展示、数据链路与协作治理能力。

当前仓库已经具备以下基础能力：
- 本地模块栈启动
- 前端监控面板展示
- 基础 CI 检查
- 协作治理文档
- Windows / Bash 双启动入口

---

## 仓库目标

本仓库当前主要关注以下几类问题：

1. 本地运行是否稳定
2. 前端监控与配置是否可用
3. CI 是否能拦住明显问题
4. 团队协作是否具备最基础治理能力
5. 关键环境变量、入口与排查方式是否文档化

---

## 项目结构（核心文件）

```text
.
├─ canvas/                       # 前端监控与配置页面
│  ├─ index.html
│  ├─ config.html
│  ├─ monitor.html
│  ├─ app.js
│  └─ runtime-config.js
├─ configs/                      # 配置文件
├─ logs/                         # 本地日志与运行产物（不提交真实运行数据）
├─ scripts/                      # 主要脚本
│  ├─ run_c_module_stack.py
│  ├─ system_healthcheck.py
│  ├─ verify_execution_no_pytest.py
│  └─ ...
├─ .github/workflows/ci.yml      # GitHub Actions 基础 CI
├─ requirements.txt              # Python 依赖
├─ .env.example                  # 环境变量模板
├─ run_local.sh                  # Bash 本地启动入口
├─ run_local.ps1                 # Windows PowerShell 本地启动入口
└─ CONTRIBUTING.md               # 协作与分支治理规则
