# 电商售后多智能体协作系统

面向取消订单、退货与换货场景的难度路由多智能体 MVP。项目已完成 10 天开发计划：从官方 τ2 基线、政策与事实绑定、专业智能体协作和独立审核，一直到轻量工作台、四架构离线实验、可靠性沙箱及 Docker 交付配置。

## 当前进度

- [x] 固化 10 个工作日开发计划
- [x] 初始化 Python/FastAPI 工程骨架
- [x] 定义结构化工单状态与证据模型
- [x] 实现确定性难度路由、风险分级和审批判定
- [x] 添加领域单元测试
- [x] 接入官方 τ2 1.0.1 Retail 环境并固定 9 个核心任务
- [x] 完成参考轨迹烟雾测试与逐任务轨迹记录
- [x] 完成 DeepSeek V4 Flash 真实单智能体基线（兼容模式最终 8/9）
- [x] 后续基线默认使用官方 τ2 原始提示与官方精确评分（历史增强结果仅作诊断）
- [x] 完成第 3 天政策检索、事实绑定和有来源资格判断
- [x] 完成第 4 天订单/政策智能体、结构化交接和最小工具权限
- [x] 完成第 5 天候选方案汇总、冲突检测和澄清门控
- [x] 完成第 6 天独立审核、人工决策门控和状态差异校验
- [x] 完成第 7 天专业智能体与人工审批工作台
- [x] 完成第 8 天 30 任务 × 4 架构 × 3 次离线实验矩阵
- [x] 完成第 9 天超时/重试、幂等、缓存、注入防护与成本台账
- [x] 完成第 10 天 5 个稳定工单、统一演示、发布自检和容器配置

完整计划见 [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)，每次开发记录见
[docs/DEVLOG.md](docs/DEVLOG.md)。

第 2 天完成内容、结果含义和测试方式见
[docs/DAY2_GUIDE.md](docs/DAY2_GUIDE.md)。
官方 Retail `base` split 114 题单轮结果、续跑过程和提交口径见
[docs/TAU2_FULL_RETAIL_REPORT.md](docs/TAU2_FULL_RETAIL_REPORT.md)。

第 3 天政策条款、检索和事实绑定说明见
[docs/DAY3_GUIDE.md](docs/DAY3_GUIDE.md)。

第 4 天双专家协作、handoff 和权限说明见
[docs/DAY4_GUIDE.md](docs/DAY4_GUIDE.md)。

第 5 天候选方案、冲突类型和三种规划状态说明见
[docs/DAY5_GUIDE.md](docs/DAY5_GUIDE.md)。

第 6 天独立审核、批准/修改/拒绝和执行后校验说明见
[docs/DAY6_GUIDE.md](docs/DAY6_GUIDE.md)。

第 7 天工作台的启动、按钮含义和“模拟状态差异”说明见
[docs/DAY7_GUIDE.md](docs/DAY7_GUIDE.md)。

第 8 天离线实验方法、指标口径和解释边界见
[docs/DAY8_GUIDE.md](docs/DAY8_GUIDE.md)。

第 9 天可靠性、安全、沙箱执行和成本统计说明见
[docs/DAY9_GUIDE.md](docs/DAY9_GUIDE.md)。

第 10 天统一演示、发布自检和 Docker 交付说明见
[docs/DAY10_GUIDE.md](docs/DAY10_GUIDE.md)。

## 最快体验

```powershell
cd D:\llm项目\多智能体协作
uv sync --extra dev
uv run uvicorn after_sales_agents.api:app --app-dir src --reload
```

打开 `http://127.0.0.1:8000/ui`。页面内置取消、退货、换货三个场景，可以查看专业
智能体交接、事实与政策证据、候选动作、独立审核和人工决定。批准只签发单次授权；页面
没有真实写入口，状态差异明确使用模拟快照。

想一次验证全部确定性演示：

```powershell
uv run python scripts\run_all_demos.py
```

当前统一入口包含 6 个演示，运行结果为 `6/6`；模型调用和真实业务写调用均为 0。

## 第 8 天实验结果

固定故障注入任务集包含取消、退货、换货各 10 个。每个任务在四种架构下重复 3 次，
共 360 条确定性运行记录：

| 架构 | 成功率 | 政策违规次数 | 平均逻辑智能体调用 | 一致性 |
|---|---:|---:|---:|---:|
| 单智能体 | 50% | 24 | 1.00 | 100% |
| 固定多智能体 | 80% | 18 | 3.00 | 100% |
| 难度路由多智能体 | 80% | 18 | 2.27 | 100% |
| 难度路由多智能体 + 独立审核 | 100% | 0 | 2.77 | 100% |

这些数字来自本项目的离线确定性控制流与故障注入，不是 LLM 质量成绩，也不是官方
τ2 成绩。实验未调用模型或真实写工具；“延迟”是操作预算代理值，不是墙钟延迟。完整
逐次结果见 `artifacts/day8/experiment_report.json`。

## 核心约束

- 普通查询优先走单智能体，只有复杂工单才启动专业智能体。
- 智能体之间传递结构化状态，不依赖不可审计的自由文本接力。
- 退款、取消、退货、换货和补发等写操作一律需要明确审批。
- 最终业务状态由确定性程序校验，不能只依赖模型自评。
- MVP 仅连接沙箱工具，不连接真实资金和库存系统。

## 本地验证

PowerShell：

```powershell
uv run pytest -q -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
uv run python -c "from after_sales_agents.api import app; print(app.title, app.version)"
```

验证官方 Retail 子集并运行不调用模型的环境烟雾测试：

```powershell
python scripts\validate_tau2_retail.py
python scripts\run_tau2_reference_smoke.py
```

验证 14 条政策引用和一份事实绑定示例（不调用模型）：

```powershell
uv run python scripts\validate_policy_grounding.py
uv run python scripts\run_day4_collaboration_demo.py
uv run python scripts\run_day5_planning_demo.py
uv run python scripts\run_day6_review_demo.py
uv run python scripts\run_day8_experiment.py
uv run python scripts\run_day9_reliability_demo.py
uv run python scripts\run_delivery_scenarios.py
```

生成真实单智能体基线命令（默认 dry-run，不产生 API 费用）：

```powershell
python scripts\run_tau2_llm_baseline.py
```

启动记录中的下面两个字段表示使用官方客服提示：

```json
{
  "agent_instruction_profile": "official_tau2",
  "official_agent_prompt": true
}
```

早期固定 9 题官方基准成绩为 `8/9`。2026-08-13 完成的 Retail `base`
全部 114 题单轮成绩为 `108/114`（Pass¹ `94.74%`），0 缺题、0 重复、0 基础设施
错误。这是完整 Retail 单轮成绩，不是τ2全领域 Overall，也不是官方强烈建议的
4+ trials 提交成绩。任务 38 的本地等价性分析不参与通过率计算。
如需查看历史诊断，可以显式运行：

```powershell
python scripts\evaluate_business_result.py artifacts\day2\llm_baseline_results_task38_business_fix.json --task-id 38
```

这份报告会标记为 `business_reward_is_diagnostic_only: true`。计算器强化提示同样不再
默认启用；只有显式传入
`--agent-instruction-profile auditable_money_calculation_v1` 才会进入诊断模式。

安装项目依赖后可启动 API：

```powershell
uv sync --extra dev
uv run uvicorn after_sales_agents.api:app --reload
```

Docker 主机也可以运行：

```powershell
docker compose up --build
```

当前开发机没有安装 Docker CLI，所以本轮只完成配置、密钥排除和自动化静态验证，尚未
在本机实际构建镜像。发布前可运行 `uv run python scripts\verify_release.py`；在 Docker
可用主机上还应补跑 `docker compose config` 和 `docker compose build`。

项目 Wheel 已在本机临时构建验证，包含 UI 和政策资源且不包含 `local_secrets`；这不等同
于 Docker 镜像已实际构建。

路由预览接口：

```text
POST /api/v1/routing/preview
POST /api/v1/policy/search
POST /api/v1/policy/eligibility
POST /api/v1/collaboration/review
POST /api/v1/planning/review
POST /api/v1/review/audit
POST /api/v1/review/decision
POST /api/v1/review/verify-state
```

示例请求：

```json
{
  "ticket_id": "ticket-001",
  "user_message": "我要退掉订单中的衬衫，同时换一双鞋",
  "intents": ["return_items", "exchange_items"],
  "order_ids": ["order-1001"],
  "requested_actions": ["create_return", "exchange_items"],
  "requires_money_movement": true,
  "requires_inventory_movement": true,
  "user_confirmed": false
}
```
