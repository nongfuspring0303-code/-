# 环境隔离规范（dev / prod）

## 1. 角色定义
- **dev**：允许 mock / fallback（需标记 is_test_data）
- **prod**：严格禁止 fallback / mock；必须启用鉴权

## 2. 必要环境变量
- `EDT_RUNTIME_ROLE`：dev | prod
- `EDT_NODE_ROLE`：master | worker
- `EDT_MASTER_API`：worker 转发目标（如 http://<master_ip>:18787）
- `EDT_API_TOKEN` / `EDT_WS_TOKEN`：prod 必填

## 3. 端口统一
- WS：`EDT_WS_PORT`（默认 18765）
- API：`EDT_API_PORT`（默认 18787）
- WEB：`EDT_WEB_PORT`（默认 18080）

## 4. 生产严格策略
- fallback：严格禁止（无数据即失败）
- mock：禁止
- 鉴权：必须配置 token
