# 官方 τ2 多智能体运行时报告

更新时间：2026-08-14

## 当前结论

项目已经实现可被 τ2 1.0.1 官方 runner 直接加载的自定义 Agent：
`after_sales_multiagent`。它在 7 个定向 Retail 能力任务上完成单轮试跑，官方 reward 与
最终数据库检查均为 `7/7`。这证明协议、角色协作、官方工具执行和评分链路已经接通，但
7 题不是完整榜单，暂时不能与 114 题 × 4 trials 的单智能体 Pass¹–Pass⁴ 比较。

## 运行架构

```text
UserMessage / ToolMessage
  -> DifficultyRouter
  -> 普通请求：Coordinator
  -> 复杂请求：Order/Constraint Specialist -> Coordinator
  -> 只读候选：直接返回官方 ToolCall 或文本
  -> 写候选：Policy Specialist -> Independent Auditor
       -> 未通过：Coordinator 修复或向用户澄清
       -> 通过且已有必要确认：返回官方 ToolCall
  -> τ2 Orchestrator 执行工具并更新官方 Retail 数据库
```

对外只有一个官方 `HalfDuplexAgent` 入口；对内是多次真实、相互独立的模型调用和结构化
handoff。用户模拟器、自然语言断言裁判、环境和工具执行器均为 τ2 外部组件，不计为项目
智能体。

该运行时主要复用现有 `DifficultyRouter` 和项目的治理原则。它没有把旧的
`SpecialistWorkflow`、`PlanningWorkflow`、`HumanApprovalGate` 或本地 sandbox 原样接入
τ2，因此准确名称是“项目新建的 τ2 多智能体运行时”，不是“旧业务工作流原样运行”。

## 工具与审批边界

- Agent 只生成官方 `AssistantMessage` 和 `ToolCall`；
- 真实读写都由 τ2 Orchestrator 执行，项目代码不直接调用官方环境工具；
- 遵循 Retail policy，每条消息至多一个工具调用，且文本与工具调用互斥；
- 写候选必须同时具备有效的政策结果和有效的独立审计结果；
- 需要用户确认时，缺少确认即关闭执行；
- 任一结构化 handoff 解析失败都不能单独放行写操作；
- 结果复制前校验 Agent 实现、Agent 模型、用户模拟器、用户模型和 Retail 域，避免误复用
  单智能体 checkpoint。

## DeepSeek 兼容性修复

真实 task 66 首次暴露了 DeepSeek 思考模式与 τ2 1.0.1 历史转换的兼容问题：官方
`generate()` 已把 provider 原始响应保存到 `AssistantMessage.raw_data`，但历史转换没有把
工具调用轮次的 `reasoning_content` 传回下一次请求，DeepSeek 因此返回 400。

项目 bootstrap 现在只在 DeepSeek 兼容开关开启时，从已经保存的原始响应恢复
`reasoning_content`；没有修改 `.external` 下的官方源码，也没有把 reasoning 当作用户可见
文本。DeepSeek 官方文档要求工具调用对话回传该字段：
[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)。

结构化的约束、政策和审计调用不需要长推理，因此使用
`extra_body={"thinking":{"type":"disabled"}}`；最终协调员仍保留思考。LiteLLM 1.81.11
会丢弃顶层的 disabled thinking，离线参数转换和真实请求均确认 `extra_body` 才会保留。

## task 66 试跑

| 阶段 | 结果 | 直接原因 |
|---|---|---|
| 初始兼容性诊断 | DeepSeek 400 | 工具调用历史缺少 `reasoning_content` 回放 |
| pilot v1 | timeout，457.04s | 正确政策/审计 JSON 的少数字段形状未通过严格解析，引发重复修复 |
| pilot v2 | reward 0，`user_stop`，56.33s | 用户确认的取消理由与隐藏参考固定值不同 |

pilot v2 中，用户模拟器明确选择 `ordered by mistake`，Agent 展示并确认后执行
`cancel_pending_order(#W3361211, reason="ordered by mistake")`；这是官方政策允许的理由，
政策专员和审计员均批准。隐藏参考却要求 `no longer needed`，所以 DB=0、NL=1。该轨迹仍按
官方 reward 记失败，但不应通过硬编码隐藏参考来扭曲正常客服行为。

## 7 项能力冒烟

运行身份：

- Agent：`after_sales_multiagent`；
- 架构：`difficulty_routed_multi_agent`；
- Agent / user simulator 模型：`deepseek/deepseek-v4-flash`，temperature=0；
- 任务：0、2、3、10、17、33、40；
- trials：1；seed：300。

| Task | 覆盖能力 | Reward / DB | 写工具 | 角色调用 | Agent tokens | 墙钟 |
|---:|---|---:|---|---:|---:|---:|
| 0 | 换货 | 1 / 1 | `exchange_delivered_order_items` | 17 | 103,870 | 55.14s |
| 2 | 退货 | 1 / 1 | `return_delivered_order_items` | 32 | 259,793 | 128.03s |
| 3 | 修改订单商品 | 1 / 1 | `modify_pending_order_items` | 23 | 188,421 | 69.96s |
| 10 | 无写操作 | 1 / 1 | 无 | 13 | 65,812 | 41.51s |
| 17 | 修改订单地址 | 1 / 1 | `modify_pending_order_address` | 9 | 48,572 | 17.33s |
| 33 | 修改用户地址 | 1 / 1 | `modify_user_address` | 12 | 81,322 | 43.33s |
| 40 | 修改支付方式 | 1 / 1 | `modify_pending_order_payment` | 17 | 91,495 | 57.04s |
| 合计 | 7 项能力 | 7 / 7 | 6 类写动作 | 123 | 839,285 | 412.33s |

内部角色调用分布：协调员 84、订单/约束专员 15、政策专员 12、独立审计员 12。Agent 模型
生成时间合计 314.18 秒。task 2、3、40 各有 2 次审查后修复；task 10 有 1 次约束专员
handoff 解析失败，降级后仍完成任务。全部 78 条 Agent 输出都有 usage 记录。

官方 action aggregate 并非所有读取动作都完全匹配参考，例如 task 3 存在一次额外读取；
这里的 `7/7` 只表示每条轨迹的官方最终 reward 和 DB 检查为 1，不表示过程没有冗余。

## 成本与解释边界

- 所有内部角色当前使用同一个底层 DeepSeek 模型；这是多角色独立调用链，不是异构模型团队；
- Agent 与用户模拟器使用同一模型，存在相关性偏差；
- 7 题只做 1 trial，样本 100% 不能外推成完整 Retail 成绩；
- LiteLLM 没有该模型的价格映射，`cost_complete=false`，只能报告 token 和时间，不能推算美元；
- 单智能体基线使用官方原始 Agent 提示；自定义多智能体有自己的角色提示，因此比较的是两种
  Agent 实现，不是同一提示的消融；
- 只有完整 456 条结果满足 0 缺失、0 重复、0 未评分、0 基础设施错误后，才计算和比较
  Pass¹–Pass⁴。

## 已完成的零费用验证

- 项目相关单测：21 passed；
- 自定义名称出现在官方 CLI Agent choices；
- factory、state 和官方消息协议可实例化；
- 假协调员、政策专员和审计员能完成 ToolCall 往返；
- DeepSeek reasoning 回放、重复安装保护和 MultiToolMessage 转换兼容通过；
- 写审批解析失败时 fail-closed；
- 结果身份不匹配时拒绝复制。

## 产物

- `artifacts/day2/llm_baseline_results_multiagent_capability7_v1.json`：7 条官方轨迹；
- `artifacts/day2/llm_baseline_launch_multiagent_capability7_v1.json`：启动与完整性检查；
- `artifacts/day2/llm_baseline_results_multiagent_task66_pilot_v1.json`：超时诊断；
- `artifacts/day2/llm_baseline_results_multiagent_task66_pilot_v2.json`：修复后的 task 66 轨迹；
- `artifacts/day2/llm_baseline_launch_multiagent_task66_*.json`：对应启动记录。

## 下一步正式评测

将在全新 checkpoint 上运行完整 Retail `base` 114 题 × 4 trials：

```powershell
uv run python scripts\run_tau2_llm_baseline.py `
  --agent-implementation after_sales_multiagent `
  --all-base-tasks `
  --num-trials 4 `
  --max-concurrency 3 `
  --save-to after_sales_multiagent_retail_base_4trials_v1 `
  --artifact-label multiagent_retail_base_4trials_v1 `
  --enforce-communication-protocol `
  --execute
```

若出现可恢复基础设施错误，只使用完全相同的 `save-to` 和参数加 `--auto-resume`；不会手工
拼接轨迹。完成后使用 τ2 官方 `compute_metrics` 计算 Pass¹–Pass⁴，再与单智能体
`92.32% / 87.43% / 83.33% / 79.82%` 在相同任务与轮次下比较。
