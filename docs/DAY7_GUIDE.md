# 第 7 天说明：轻量业务界面

## 一句话说明

FastAPI 现在直接提供一个无需 Node、npm 或前端构建步骤的售后协作工作台。它把工单
对话、智能体交接、事实与政策依据、候选动作、独立审核和人工决策放在同一页面中。

页面只调用第 5、6 天已有的规划与审核接口；批准仅生成未来可用的单次授权，不会执行
取消、退货或换货。界面中的模型调用和写工具调用均为 0。

## 1. 启动与访问

```powershell
cd D:\llm项目\多智能体协作
uv run uvicorn after_sales_agents.api:app --app-dir src --reload
```

浏览器打开：

```text
http://127.0.0.1:8000/ui
```

访问根地址 `http://127.0.0.1:8000/` 也会跳转到 `/ui`。API 文档仍在：

```text
http://127.0.0.1:8000/docs
```

## 2. 页面能做什么

页面内置三个确定性示例：

| 场景 | 订单状态 | 候选动作 |
|---|---|---|
| 取消订单 | `pending` | `cancel_order` |
| 商品退货 | `delivered` | `create_return` |
| 商品换货 | `delivered` | `exchange_items` |

选择场景并点击“运行多智能体分析”后，页面依次展示：

1. 客户请求、动作细节和客户确认；
2. 订单智能体的只读工具调用；
3. 政策智能体的资格结论及政策引用；
4. 规划器生成的候选动作、参数、引用和风险；
5. 独立审核员的六类检查；
6. 人工批准、修改或拒绝结果；
7. 明确标记为“模拟快照”的状态差异校验。

所有事实都显示 `source_type` 和 `source_id`，政策显示条款编号、标题及正文。页面渲染
的是真实 API 响应，不在前端复制政策判断逻辑。

## 3. 人工按钮的准确含义

### 批准

批准会调用：

```text
POST /api/v1/review/decision
```

并生成一份绑定审核摘要的 `ExecutionAuthorization`。结果仍明确展示：

```text
execution_authorized: true
can_execute_now: false
write_executed: false
```

这表示“未来受控执行器可消费该授权”，不表示订单已经修改。页面没有执行按钮，也不
调用任何订单写工具。

### 修改

取消订单示例允许把政策许可的取消理由改为另一项。修改后旧审核立即失效，结果为
`modification_requires_review`，必须重新规划和审核；不会产生授权。

### 拒绝

拒绝结束当前审批，不产生授权，也不执行写操作。

## 4. 状态差异区为什么是模拟的

第 7 天仍未增加真实执行器。批准后，界面依据授权中的 `expected_state_changes` 构造一份
清楚标记为“模拟”的执行后快照，再调用现有状态校验接口演示比较结果。

因此页面显示 `matched` 只说明比较器可以识别这份模拟快照符合预期，不代表真实订单
发生过变化。

## 5. 技术实现

```text
src/after_sales_agents/ui/index.html
src/after_sales_agents/ui/assets/app.css
src/after_sales_agents/ui/assets/app.js
```

FastAPI 使用 `FileResponse` 提供页面，使用 `StaticFiles` 提供 CSS 和 JavaScript。资源都在
项目包内，无 CDN、无外部字体、无前端运行时依赖，也不需要修改 `pyproject.toml`。

页面调用的接口只有：

```text
POST /api/v1/planning/review
POST /api/v1/review/audit
POST /api/v1/review/decision
POST /api/v1/review/verify-state
```

`/ui` 和 `/ui/assets` 是展示路由，特意不加入业务 OpenAPI 路径，避免它们与 JSON API
混在一起。

## 6. 验证

```powershell
uv run pytest tests/test_ui.py -q -p no:cacheprovider
uv run ruff check src/after_sales_agents/api.py src/after_sales_agents/ui tests/test_ui.py
uv run ruff format --check src/after_sales_agents/api.py src/after_sales_agents/ui tests/test_ui.py
node --check src/after_sales_agents/ui/assets/app.js
```

新增测试不依赖 `httpx` 或 FastAPI `TestClient`，而是直接通过 ASGI 协议请求应用，所以没有
增加开发依赖。测试覆盖根路径跳转、HTML 页面、静态资源、关键业务区块、API 使用边界、
禁止写工具调用和 OpenAPI 隔离。

当前第 7 天专项结果：

```text
5 passed
Ruff: All checks passed
JavaScript syntax: passed
```
