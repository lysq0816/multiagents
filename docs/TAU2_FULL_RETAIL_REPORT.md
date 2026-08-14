# τ2 Retail 完整任务四轮评测报告

## 结论

2026-08-14，使用本地官方 τ2 1.0.1 Retail `base` split 完成全部 114 题、每题 4 轮评测，
共得到 456 条有效轨迹：

| 指标 | 结果 |
|---|---:|
| 任务 | 114/114 |
| 有效评分 | 456/456 |
| 通过轨迹 | 421 |
| 失败轨迹 | 35 |
| Pass¹ | 92.32% |
| Pass² | 87.43% |
| Pass³ | 83.33% |
| Pass⁴ | 79.82% |
| 基础设施错误 | 0（最终产物） |
| 缺失 / 意外 / 重复 task-trial | 0 / 0 / 0 |

Passᵏ 直接由 τ2 1.0.1 官方 `compute_metrics` 计算。官方实现先对每道题使用
`C(成功轮数, k) / C(总轮数, k)`，再对 114 道题取平均；这里没有用普通总通过率冒充
Pass²–Pass⁴。

## 每轮结果

| Trial | Seed | 通过 | 失败 | 通过率 |
|---:|---:|---:|---:|---:|
| 0 | 626729 | 108 | 6 | 94.74% |
| 1 | 373753 | 101 | 13 | 88.60% |
| 2 | 361454 | 103 | 11 | 90.35% |
| 3 | 1567 | 109 | 5 | 95.61% |
| 合计 | — | 421 | 35 | 92.32% |

每题四轮成功次数分布：

| 四轮成功次数 | 任务数 | 任务 ID |
|---:|---:|---|
| 0 | 2 | 38、105 |
| 1 | 1 | 59 |
| 2 | 4 | 64、66、98、100 |
| 3 | 16 | 3、5、22、34、41、44、63、68、69、76、79、89、91、101、103、104 |
| 4 | 91 | 其余 91 题 |

这说明单轮 `108/114` 只是 trial 0 的一次结果；四轮后更有代表性的 Pass¹ 是 92.32%。

## 运行口径

- 域：Retail；
- 任务：官方 `base` split 全部 114 题，命令不传 `--task-ids` 或 `--num-tasks`；
- 轮次：4；
- 客服实现：官方 `llm_agent`；
- 客服模型：`deepseek/deepseek-v4-flash`；
- 用户模拟器：官方 `user_simulator`，模型为 `deepseek/deepseek-v4-flash`；
- 自然语言断言裁判：官方评分流程，裁判模型为 `deepseek/deepseek-v4-flash`；
- 客服提示：τ2 1.0.1 默认官方提示，未启用项目的诊断增强提示；
- 工具、沙箱数据库、任务和评分流程：本地官方 τ2 1.0.1；
- 温度：0；全局 seed：300；每题最多 80 steps；超时 300 秒；
- 并发：扩轮初段为 1，checkpoint 恢复后为 3；模型、任务、seed、提示和评分口径未改变。

114 题中 40 题实际含自然语言断言，共 61 条；这些题会调用 DeepSeek 裁判，空断言列表
不会调用裁判模型。因此本结果应称为“官方任务、工具、提示与评分代码 + DeepSeek 客服、
用户和裁判”，不能称为官方默认模型配置。

## 检查点恢复与产物验收

运行过程中，DeepSeek 经 LiteLLM 偶发返回空 `content` 且无 `tool_calls`。trial 1 的任务 21、
trial 2 的任务 65 和 trial 3 的任务 23 曾留下基础设施错误；它们都发生在正常评分前，
不计作业务失败。使用官方相同 `save-to` 与 `--auto-resume` 后，检查点保留正常结果、删除
错误占位并只补失败项。任务 65 经过多次恢复才成功，最终产物没有基础设施错误。

该四轮运行是在已完成的单轮 checkpoint 上继续扩展。τ2 1.0.1 恢复时保留旧的
`info.num_trials=1`，尽管实际 `trial=0..3` 已完整存在。项目启动器现在只在同时满足以下条件后，
将复制产物的元数据规范化为 4：

1. 总数为 456；
2. 每个 `(task_id, trial)` 唯一；
3. 每条都有官方奖励；
4. 最终没有 `infrastructure_error`。

规范化只修正描述性元数据，不改变消息、工具调用、数据库状态或奖励。修正后的产物可由
τ2 官方 `Results.load()` 和 `compute_metrics()` 直接得到 Pass¹–Pass⁴。

## Trial 0 历史失败诊断

trial 0 的失败任务为 38、59、64、79、100、105。该分析只解释第一轮，不代表四轮中只有
这 6 道题出现过失败。

| 任务 | DB / NL | 证据支持的直接原因 | 类型 |
|---:|---:|---|---|
| 38 | 0 / 1 | 隐藏参考要求取消原因 `no longer needed`，用户模拟器却明确选择 `ordered by mistake`，客服按用户选择写入 | 用户模拟器 / 隐藏参考冲突 |
| 59 | 0 / 0 | 隐藏目标要求取消桌灯订单并修改另一订单地址；用户模拟器把条件绑定到另一订单，客服因而取消错单且未改地址 | 多订单条件绑定错位，且模拟器 / 参考冲突 |
| 64 | 0 / 1 | 黑色和银色变体都满足显式属性，用户选择银色，隐藏参考固定为黑色 | 多候选变体的隐藏 tie-break 歧义 |
| 79 | 0 / 1 | 从另一订单得到的“同色=红色”约束丢失，最终换成黑色水瓶 | 跨订单指代 / 回退约束丢失 |
| 100 | 0 / 1 | 目标商品修改和退货均执行，但额外把整单付款方式从 PayPal 改为信用卡 | 过度执行 / 差价支付语义混淆 |
| 105 | 0 / 1 | 明确要求 1.5 升燃气壶，客服写入 1 升变体 | 数值属性丢失 |

任务 105 的自然语言裁判产生了假阳性，但确定性 DB 对比捕获了错误。上述任务最终仍按
官方精确奖励统计；本地等价性诊断和 `action_match` 不会覆盖官方成绩。

## 不能如何解读

- 这是完整 Retail 单域四轮结果，达到官方强烈建议的每域 4+ trials 下限，但不是 τ2
  全领域 Overall；
- 这是官方 `llm_agent` 单智能体基线，不是本项目自定义多智能体工作流的 τ2 成绩；
- 421/456 是通过轨迹数，35 是失败轨迹数，不等于 35 道唯一失败题；
- 不能写“运行过程从未出现基础设施错误”，只能写“最终产物为 0，过程错误已由官方
  checkpoint 补测”；
- LiteLLM 没有正确识别 DeepSeek V4 Flash 的价格映射，结果文件也未声明币种；真实费用
  以 DeepSeek 控制台为准。

官方提交说明要求使用完整任务、`base` split，并强烈建议每域至少 4 轮；单域可单独统计。
参见 [τ2 leaderboard submission guide](https://github.com/sierra-research/tau2-bench/blob/main/docs/leaderboard-submission.md)。

## 产物

- `artifacts/day2/llm_baseline_results_retail_base_4trials.json`：456 条官方完整轨迹，
  `info.num_trials=4`；
- `artifacts/day2/llm_baseline_summary_retail_base_4trials.json`：机器可读汇总；
- `artifacts/day2/llm_baseline_summary_retail_base_4trials.md`：简洁汇总；
- `artifacts/day2/llm_baseline_launch_retail_base_4trials.json`：最终命令、覆盖验收和元数据
  规范化记录；
- `artifacts/day2/llm_baseline_launch_retail_base_4trials_dry_run.json`：执行前 456 条 dry-run；
- `artifacts/day2/llm_baseline_results_retail_base_full.json`：历史单轮最终轨迹；
- `artifacts/day2/llm_baseline_results_retail_base_full_initial_with_infra_error.json`：历史单轮
  首次基础设施错误证据。

## 复现命令

使用新的 `save-to` 完整运行 Retail 四轮，会调用模型并产生明显费用：

```powershell
uv run python scripts\run_tau2_llm_baseline.py `
  --all-base-tasks `
  --num-trials 4 `
  --max-concurrency 3 `
  --save-to deepseek_retail_base_4trials_new `
  --artifact-label retail_base_4trials_new `
  --execute
```

中断或存在 `infrastructure_error` 时，保持 `save-to`、模型、参数和轮次完全相同，再加
`--auto-resume`。不要换目录后手工拼接轨迹。
