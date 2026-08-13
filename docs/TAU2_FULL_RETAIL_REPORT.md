# τ2 Retail 完整任务单轮评测报告

## 结论

2026-08-13 使用本地官方 τ2 1.0.1 Retail `base` split 完成 114 个任务的单轮评测：

| 指标 | 结果 |
|---|---:|
| 任务 | 114/114 |
| 有效评分 | 114/114 |
| 通过 | 108 |
| 失败 | 6 |
| Pass¹ | 94.74% |
| 基础设施错误 | 0（最终结果） |
| 缺题 / 重复 | 0 / 0 |

失败任务 ID：`38`、`59`、`64`、`79`、`100`、`105`。

## 失败题归因

6 题的数据库奖励均为 0。任务 59 同时未通过自然语言断言；其余 5 题的自然语言部分
已通过，主要损失来自最终持久状态。

| 任务 | DB / NL | 证据支持的直接原因 | 类型 |
|---:|---:|---|---|
| 38 | 0 / 1 | 隐藏参考要求取消原因 `no longer needed`，用户模拟器却明确选择 `ordered by mistake`，客服按用户选择写入 | 用户模拟器/隐藏参考冲突 |
| 59 | 0 / 0 | 隐藏目标要求取消桌灯订单并修改另一订单地址；用户模拟器将条件明确绑到另一订单，客服因而取消错单且未改地址 | 多订单条件绑定错位，且模拟器/参考冲突 |
| 64 | 0 / 1 | 黑色和银色变体都满足显式属性，客服把两者都交给用户，用户选银色，隐藏参考固定为黑色 | 多候选变体的隐藏 tie-break 歧义 |
| 79 | 0 / 1 | 从另一订单得到的“同色=红色”约束丢失，最终换成黑色水瓶 | 跨订单指代/回退约束丢失 |
| 100 | 0 / 1 | 目标商品修改和退货均执行，但额外将整单付款方式从 PayPal 改为信用卡，造成多余持久变更 | 过度执行/差价支付语义混淆 |
| 105 | 0 / 1 | 明确要求 1.5 升燃气壶，客服写入 1 升变体 | 数值属性丢失 |

任务 105 的自然语言裁判将“两个请求商品都正确”判为真，但确定性 DB 对比捕捉到
1.5 → 1 的属性错误。这也说明不能只看 LLM 裁判。

优先改进顺序：

1. 写操作前维护结构化目标账本，固定订单、商品、数值属性、条件分支和跨订单指代；
2. 禁止无需求的额外写操作，区分“差价付款方式”与“整单更换付款方式”；
3. 对多个等价候选使用稳定的决胜规则，同时把隐藏参考歧义单独标注；
4. 任务 38 和 59 仍按官方结果计为失败，但不通过扭曲正常业务行为去迎合冲突的隐藏参考。

这 6 题的最终 `reward_basis` 是 DB 与 NL 断言；`action_match` 是诊断信息，不是这些题的
最终硬性评分项。

## 运行口径

- 域：Retail；
- 任务：官方 `base` split 全部 114 题，命令不传 `--task-ids` 或 `--num-tasks`；
- 轮次：1；
- 客服模型：`deepseek/deepseek-v4-flash`；
- 用户模拟器：`deepseek/deepseek-v4-flash`；
- 自然语言断言裁判：`deepseek/deepseek-v4-flash`；
- 客服提示：本地 τ2 1.0.1 默认官方提示，未启用项目的诊断增强提示；
- 工具、沙箱数据库、任务和评分流程：本地官方 τ2 1.0.1；
- 温度：0；并发：1；随机种子：300；每题最多 80 steps，超时 300 秒。

114 题中 40 题实际含自然语言断言（共 61 条），这些题会调用 DeepSeek 裁判；空断言列表
不会调用裁判模型。因此这是“官方任务/工具/评分代码 + DeepSeek 模型与裁判”的结果，
不是官方默认裁判模型配置。

## 基础设施错误与续跑

首轮任务 6 在用户模拟器首条消息时获得经 LiteLLM 标准化后的空 `content` 且无
`tool_calls`，自动尝试耗尽后记为 `infrastructure_error`。它发生在评分前，不计为模型
业务失败。任务 16 曾出现一次相同空响应，但官方自动重试成功，说明这是偶发的模型/
适配响应，不是任务 6 的固定数据错误。失败日志未保存原始 `reasoning_content`，所以不对上游
原始 JSON 作进一步断言。

使用官方 `--auto-resume` 和相同 `save-to` 续跑：检查点保留 113 个正常结果，删除错误
占位，只重跑任务 6。补测成功后得到 114 个唯一、全部有评分的结果。首轮原始文件单独
保留，没有用人工 JSON 拼接覆盖错误证据。

## 不能如何解读

这不是 τ2 所有领域的“总榜”结果，也不是官方强烈建议的 4+ trials 统计。官方允许单域提交，
但要求该域不漏题，并强烈建议每域至少 4 轮以提高统计可靠性。因此本报告只称为“完整
Retail base 单轮评测”。若要更接近提交级 Retail 结果，需运行 114 × 4 = 456 条轨迹；
若要完整 Overall，还需按官方当前提交说明评测其他域。

当前 LiteLLM 的 DeepSeek V4 Flash 价格映射未识别模型，因此结果中虽有已记录的数值，却没有
声明币种且不能当作真实账单；实际费用以 DeepSeek 控制台为准。

## 产物

- `artifacts/day2/llm_baseline_results_retail_base_full.json`：官方最终完整轨迹；
- `artifacts/day2/llm_baseline_summary_retail_base_full.json`：机器可读汇总；
- `artifacts/day2/llm_baseline_summary_retail_base_full.md`：简洁汇总；
- `artifacts/day2/llm_baseline_launch_retail_base_full.json`：最终续跑命令与验收状态；
- `artifacts/day2/llm_baseline_results_retail_base_full_initial_with_infra_error.json`：首轮错误证据；
- `artifacts/day2/llm_baseline_launch_retail_base_full_initial.json`：首轮启动记录。

## 复现命令

完整 Retail 单轮（会调用模型并产生费用）：

```powershell
uv run python scripts\run_tau2_llm_baseline.py `
  --all-base-tasks `
  --num-trials 1 `
  --save-to deepseek_retail_base_single `
  --artifact-label retail_base_single `
  --execute
```

完整 Retail 4 轮（会产生明显更多耗时与费用）：

```powershell
uv run python scripts\run_tau2_llm_baseline.py `
  --all-base-tasks `
  --num-trials 4 `
  --save-to deepseek_retail_base_4trials `
  --artifact-label retail_base_4trials `
  --execute
```

中断或有 `infrastructure_error` 时，使用完全相同的 `save-to`、模型、参数与轮次，加上
`--auto-resume`。不要换目录后手工拼接轨迹。
