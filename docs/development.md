# 开发说明

## 后端

```text
python -m venv .venv
.venv\\Scripts\\python -m pip install --index-url https://pypi.org/simple -e "backend[dev]"
.venv\\Scripts\\python -m pytest backend/tests
```

开发模式可设置 `DATABASE_URL=sqlite+pysqlite:///./miniswarm.db`，Redis 不可用时任务仍会保存，但不会被 Worker 领取。

## 前端

```text
cd frontend
npm install --registry=https://registry.npmjs.org
npm run typecheck
npm run build
```

## 迁移

生产环境只通过 Alembic 迁移数据库：

```text
alembic -c backend/alembic.ini upgrade head
```

