# EDT-AI协同开发与集成协议（Git版）

## 1. AI 助手执行协议（AI System Prompt Extension）

如果你是协助开发此项目的 AI，在执行任何任务前必须内化以下准则：

1. **先读契约，后动代码**：在任何修改前，必须主动检索并阅读 `schemas/` 和 `module-registry.yaml`，严禁产生不符合契约的字段。
2. **门禁驱动型开发**：编写代码前先运行基准测试。在提交 PR 前，必须将最新的 `pytest` 和 `healthcheck` 输出结果（截取关键状态）贴入 PR 描述中。
3. **状态闭环**：在合入分支或完成 PR 后，必须主动询问或执行更新 `TASK_PLAN.md` 的操作，标记任务 `[done]`。
4. **禁止幻觉变量**：若需引用其他模块变量，必须通过读取 `module-registry.yaml` 确认，禁止猜测路径。
5. **首次接手预检**：严格执行本文件“第 15 章”的 5 分钟预检清单。

---

## 2. 环境就绪清单（GitHub 登录与配置说明）

在执行任何 Git 操作前，必须确保本机的 AI 工具具备推送/拉取权限。

### 2.1 身份验证（三选一）
*   **推荐：GitHub CLI (gh)**：
    运行 `gh auth login` 并选择 `SSH` 或 `HTTPS` 登录。登录后运行 `gh auth status` 确认。
*   **SSH Key（最稳定）**：
    运行 `ssh -T git@github.com`。若返回 `Hi [username]!` 则权限正常。若未配置，需运行 `ssh-keygen` 并将公钥添加到 GitHub Settings。
*   **个人访问令牌 (PAT)**：
    若使用 HTTPS 且没有 gh CLI，请准备好 PAT，并确保已运行 `git config --global credential.helper osxkeychain`。

### 2.2 Git 用户标识（必做）
确保提交记录能准确追溯到人，请在终端运行：
```bash
git config --global user.name "你的真实姓名或ID"
git config --global user.email "你的GitHub注册邮箱"
```

### 2.3 远程仓库校验
运行 `git remote -v`。确保 `origin` 指向正确的团队协作仓库地址。若无远程，需执行 `git remote add origin <url>`。

---

## 3. 目标
... (后续章节以此类推)

## 3. 单一真源规则

1. Git 仓库主目录是唯一真源。
2. 禁止用“交接包目录”覆盖主项目。
3. 历史材料只放 `archive/`，不参与运行入口。
4. 进入阶段三后，任务执行口径以 `阶段三任务分工说明.md` 为准。
5. 若阶段三任务分工说明与历史任务清单存在冲突，以阶段三任务分工说明为准。

## 4. Git 分支模型（强制）

分支角色：
1. `main`：可发布分支，只接受 `integration` 合并。
2. `integration`：每日集成分支，统一联调。
3. `feature/A-*`、`feature/B-*`、`feature/C-*`：个人任务分支。

命名规范：
```bash
feature/A-<task-id>-<short-name>
feature/B-<task-id>-<short-name>
feature/C-<task-id>-<short-name>
```

阶段三命名示例：
```bash
feature/A-A1-sector-mapping
feature/B-B1-premium-pool
feature/C-C2-visualization
```

## 5. 开发启动流程（每人每天）

```bash
git checkout integration
git pull origin integration
git checkout -B feature/<owner-task>
```

提交规范：
1. 小步提交，单次提交只做一类变更。
2. 提交信息包含任务号（如 `T4.2`）。

示例：
```bash
git add <files>
git commit -m "T4.2: make risk gate thresholds config-driven"
```

## 6. 契约冻结与四联动规则

每个 Sprint 先冻结：
1. `schemas/*.json`
2. `module-registry.yaml`

接口字段变更必须同次提交更新：
1. `schemas/*.json`
2. `tests/*`
3. `module-registry.yaml`
4. 文档（README 或计划文档）

缺任意一项，PR 驳回。

阶段三补充（实时联动场景）：
1. 涉及 `event_update` / `sector_update` / `opportunity_update` 任一消息字段变更时，执行五联动：
   - `schemas/*.json`
   - `tests/*`
   - `module-registry.yaml`
   - 文档（README 或计划文档）
   - 前端消费契约说明（`canvas/` 或对应联动文档）
2. 若字段变更未同步前端消费契约，禁止合并。

## 7. 合并门禁（PR 前必跑）

```bash
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py
```

规则：
1. 任一命令失败，禁止发起合并。
2. 健康检查非 `OVERALL: GREEN`，禁止合并。

阶段三补充门禁：
3. 涉及联动链路变更（新闻/板块/机会池）时，必须附“联动冒烟证据”：
   - 同一 `trace_id` 的 `event_update -> sector_update -> opportunity_update` 样例输出
   - 或等效的联动截图/回放记录
4. 未提供联动冒烟证据的 PR 不得合并。

## 8. PR 与合并流程

### 8.1 feature -> integration

1. 发起 PR 到 `integration`。
2. 跨模块改动必须 @对应模块 owner 审核。
3. 至少 1 人通过 + 门禁全绿才可合并。

### 8.2 integration -> main

1. 每日或里程碑时由负责人发起。
2. 必须附两份证据：
   - `pytest` 结果
   - `logs/system_health_report.json`（GREEN）

### 8.3 阶段三跨层联调附加规则

1. 若 PR 影响 A/B/C 任一层且涉及实时消息契约，必须 @C 主审。
2. PR 描述需包含契约 diff 说明：字段新增/删除/语义变更。
3. 合并前必须完成一次 A->B->C 联调回放并附结论（通过/失败与原因）。

## 9. 冲突处理规则（只在 integration 解决）

禁止在 `main` 直接解冲突。统一流程：

```bash
git checkout integration
git pull origin integration
git merge --no-ff feature/<owner-task>
# 解决冲突后
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py
git add <resolved-files>
git commit
```

## 10. 空壳禁止规则

1. 禁止 placeholder schema 合入 `integration/main`。
2. 禁止 `cases: []` 的空 YAML 测试合入 `integration/main`。
3. 临时占位只允许存在于个人分支。

## 11. 回滚与应急

### 11.1 integration 回滚

```bash
git checkout integration
git log --oneline -n 20
git revert <bad_commit_sha>
git push origin integration
```

### 11.2 main 回滚

```bash
git checkout main
git pull origin main
git revert <bad_commit_sha>
git push origin main
```

说明：禁止 `git reset --hard` 处理共享分支事故。

## 12. 集成节奏

1. 每天固定一次 `feature -> integration` 集成（建议收工前）。
2. 每次集成后立即跑门禁。
3. 问题当天清零，不留到交付日。

## 13. 交付判定（唯一口径）

交付是否通过只看：
1. `python3 -m pytest -q` 通过记录。
2. `logs/system_health_report.json` 且 `overall_status = GREEN`。

阶段三交付附加指标（指挥中心联动）：
3. 新闻到板块渲染延迟 <= 1s。
4. 板块到机会池刷新延迟 <= 1s。
5. 利好/利空场景决策差异化率 >= 80%。
6. 高风险拦截率 = 100%，AI 故障降级正确率 = 100%。
7. `trace_id` 贯穿率 = 100%，可按 `trace_id` 回放全链路。

无证据，不交付。

## 14. 标准PR模板（AI可直接填充）

标题格式：

```text
[<owner>] <task-id>: <short change summary>
```

正文模板：

```text
## 变更摘要
- 

## 影响范围
- files:
- modules:
- schemas:

## 验证证据
- python3 -m pytest -q:
- PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py:
- 联动冒烟证据（trace_id 串联）:
- （如涉及前端）三栏联动截图/回放:

## 实时契约影响（阶段三）
- event_update:
- sector_update:
- opportunity_update:
- 兼容性说明（向后兼容/破坏性变更）:

## 风险与回滚
- 风险：
- 回滚点（commit sha）：
- 回滚命令：git revert <sha>
```

## 15. 首次接手5分钟清单（AI执行顺序）

```bash
git checkout integration
git pull origin integration
git checkout -B feature/<owner-task>
# AI 必须先运行以下两条命令确认环境健康，基准失败禁止开发
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py
# AI 必须检索并阅读以下文件以对齐上下文
# 1. schemas/*.json
# 2. module-registry.yaml
# 3. TASK_PLAN.md (获取当前任务进度和变量命名习惯)
```

执行规则：
1. 若 `pytest` 或 `healthcheck` 失败，先修复再开发。
2. 开发完成后再次执行两条门禁命令再发 PR。
