# 启动 SOP（统一入口）

## 本地开发（dev）
```bash
cp .env.example .env
export $(grep -v '^#' .env | xargs)
./run_local.sh
```

前端：`http://127.0.0.1:${EDT_WEB_PORT:-18080}/canvas/index.html`

## 生产（prod）
```bash
export EDT_RUNTIME_ROLE=prod
export EDT_API_TOKEN=***
export EDT_WS_TOKEN=***
export EDT_NODE_ROLE=master
./run_local.sh
```

## Worker 节点
```bash
export EDT_NODE_ROLE=worker
export EDT_MASTER_API=http://<master_ip>:18787
./run_local.sh
```
