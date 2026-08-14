# 官方 τ2 多智能体运行时报告

更新时间：2026-08-15

## 当前结论

项目已经实现可被 τ2 1.0.1 官方 runner 直接加载的自定义 Agent：
`after_sales_multiagent`，并已完成 Retail `base` 全部 114 题 × 4 trials。最终产物包含
456 个唯一 `(task_id, trial)`，354 条通过、102 条失败，0 缺失、0 重复、0 未评分、
0 基础设施错误。τ2 1.0.1 官方 `compute_metrics` 给出的 Pass¹–Pass⁴ 为
`77.6316% / 66.9591% / 60.0877% / 55.2632%`。

此前 7 个定向 Retail 任务的单轮 `7/7` 继续作为能力冒烟：它证明协议、角色协作、官方
工具执行和评分链路接通，但正式成绩只采用完整 456 条产物。

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

## 正式 114 × 4 评测

运行配置：

- 域与任务：Retail `base`，114 题，每题 4 trials；
- Agent：`after_sales_multiagent`；
- Agent、用户模拟器和自然语言断言裁判：`deepseek/deepseek-v4-flash`；
- temperature：0；seed：300；最大并发：3；
- 单次模型请求超时：120 秒；
- 任务、数据库、Retail 工具、Orchestrator 和评分实现均使用 τ2 1.0.1 官方代码。

### 正式结果

| 指标 | 多智能体结果 |
|---|---:|
| 有效轨迹 | 456 / 456 |
| 通过 / 失败轨迹 | 354 / 102 |
| trial 0 | 89 / 114 |
| trial 1 | 86 / 114 |
| trial 2 | 88 / 114 |
| trial 3 | 91 / 114 |
| Pass¹ | 77.6316% |
| Pass² | 66.9591% |
| Pass³ | 60.0877% |
| Pass⁴ | 55.2632% |
| 最终基础设施错误 | 0 |

按每题四轮通过次数分组：63 题四轮全过，22 题通过三轮，14 题通过两轮，8 题通过一轮，
7 题四轮均未通过。最终 7 条 `timeout` 轨迹已有官方 reward=0，属于有效业务失败；它们不是
`infrastructure_error`，因此没有被续跑替换。456 条轨迹累计记录 9,674 次内部角色调用。

### 运行中止与恢复

| 版本 | 状态 | 暴露的问题与处理 |
|---|---|---|
| v1 | 早期中止 | 审查角色虚构不存在的工具名/参数，并把 DSML 标记或“已执行”声明当作正常回复；改为向审查角色提供官方工具 schema，并拒绝原始工具标记、虚假执行声明、未知工具和非法写批次。 |
| v2 | 11 条后中止 | 把合法的多个只读调用整体拦截，导致协调员重复尝试并进入循环；改为只执行首个读调用，其余读调用延后到后续轮次，写工具仍保持单调用审批。中止前未发生实际写操作。 |
| v3 | 0 条完成后中止 | provider 请求长时间不返回；启动器增加 `--model-request-timeout 120`，超时项进入可恢复的基础设施失败。 |
| v4 | 正式完成 | 首跑留下 3 条基础设施失败；对同一 `save-to` 连续执行 3 次官方 `--auto-resume`，只补失败项，最终 456 条完整且基础设施失败为 0。 |

上述恢复没有手工拼接轨迹，也没有修改 reward；每次续跑都复用相同任务、模型、seed、提示、
并发和 checkpoint 身份。审查修复还确保成功的身份查询已经完成认证，不把不存在的邮箱读取
误当作退换货前置条件。

### 与单智能体基线比较

| 官方指标 | `llm_agent` 单智能体 | `after_sales_multiagent` | 差值 |
|---|---:|---:|---:|
| Pass¹ | 92.3246% | 77.6316% | -14.69 个百分点 |
| Pass² | 87.4269% | 66.9591% | -20.47 个百分点 |
| Pass³ | 83.3333% | 60.0877% | -23.25 个百分点 |
| Pass⁴ | 79.8246% | 55.2632% | -24.56 个百分点 |

本次多智能体实现没有超过单智能体基线，而且随着要求连续通过的轮数增加，差距扩大。这个
结果支持继续简化协作链路、减少审查后修复循环，而不支持“多智能体天然更好”的结论。

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
- 7 题能力冒烟只做 1 trial，`7/7` 不能外推成正式 Retail 成绩；正式结论来自完整 456 条；
- 正式结果文件记录的 Agent 侧 prompt/completion tokens 为
  `68,203,319 / 3,407,738`，用户侧为 `3,878,262 / 732,714`；
- 结果文件记录 Agent 成本值合计 `5.4640150824`、用户侧 `0.3215102128`，但文件没有声明
  币种，因此这些值保持无单位，不把它们写成美元或真实账单；
- 单智能体基线使用官方原始 Agent 提示；自定义多智能体使用自己的角色提示和额外内部调用，
  因此比较的是两个本地端到端 Agent 实现，不是只改变“单/多智能体”一个变量的严格消融；
- 本次使用官方任务、工具、数据库、Orchestrator 和评分代码，但 Agent、用户模拟器与自然语言
  裁判均使用 DeepSeek。它是官方评测框架下的本地 Retail 单域比较，不是官方默认模型/裁判
  榜单，也不是 τ2 全领域 Overall。

## 已完成的离线验证

- 最终结果由 τ2 1.0.1 官方 `Results.load()` 成功读取；
- 官方 `tau2 submit verify-trajs` 的格式、任务和 trial 数量检查全部通过；
- 官方 `compute_metrics()` 输出 Pass¹–Pass⁴，与 354/456 奖励及任务通过次数分布一致；
- 覆盖检查为 456 个唯一任务/轮次组合，0 缺失、0 意外、0 重复、0 未评分、0 基础设施错误；
- 启动器请求超时转发、结果身份与完整性检查已有定向测试；
- 自定义名称出现在官方 CLI Agent choices；
- factory、state 和官方消息协议可实例化；
- 假协调员、政策专员和审计员能完成 ToolCall 往返；
- DeepSeek reasoning 回放、重复安装保护和 MultiToolMessage 转换兼容通过；
- 工具 schema 约束、虚假执行声明拦截、多读调用串行化和写审批 fail-closed 通过定向测试；
- 结果身份不匹配时拒绝复制。

## 产物

- `artifacts/day2/llm_baseline_results_multiagent_retail_base_4trials_v4.json`：正式 456 条轨迹；
- `artifacts/day2/llm_baseline_launch_multiagent_retail_base_4trials_v4.json`：最终启动与验收记录；
- `artifacts/day2/llm_baseline_launch_multiagent_retail_base_4trials_v4_dry_run.json`：正式命令预检记录；
- `artifacts/day2/llm_baseline_summary_multiagent_retail_base_4trials_v4.json`：机器可读汇总；
- `artifacts/day2/llm_baseline_summary_multiagent_retail_base_4trials_v4.md`：正式结果摘要；
- `artifacts/day2/llm_baseline_results_multiagent_capability7_v1.json`：7 条官方轨迹；
- `artifacts/day2/llm_baseline_launch_multiagent_capability7_v1.json`：启动与完整性检查；
- `artifacts/day2/llm_baseline_results_multiagent_task66_pilot_v1.json`：超时诊断；
- `artifacts/day2/llm_baseline_results_multiagent_task66_pilot_v2.json`：修复后的 task 66 轨迹；
- `artifacts/day2/llm_baseline_launch_multiagent_task66_*.json`：对应启动记录。

## 复现命令

正式运行命令：

```powershell
uv run python scripts\run_tau2_llm_baseline.py `
  --agent-implementation after_sales_multiagent `
  --all-base-tasks `
  --num-trials 4 `
  --max-concurrency 3 `
  --model-request-timeout 120 `
  --save-to after_sales_multiagent_retail_base_4trials_v4 `
  --artifact-label multiagent_retail_base_4trials_v4 `
  --enforce-communication-protocol `
  --execute
```

若出现可恢复基础设施错误，只对完全相同的命令增加 `--auto-resume`，继续使用同一个
`save-to`；不要改名或手工拼接结果。正式 v4 就是按这个方式完成补测。
