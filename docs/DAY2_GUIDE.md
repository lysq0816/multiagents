# 第 2 天说明：τ-bench Retail 与单智能体基线

## 一句话说明

今天把项目接到了官方模拟电商后台，固定了 9 道售后“考试题”，验证了订单工具和评分器都能工作，并准备好了真实 AI 客服参加这 9 道题的运行入口。

工程链路烟雾测试为 `9/9`，DeepSeek 真实单智能体官方基线为 `8/9`。官方成绩是
唯一主成绩；任务 38 的提示增强重跑和本地等价性分析仅作为诊断，不计入通过率。

2026-08-13 又完成了 Retail `base` split 全部 114 题的单轮评测：108 通过、6 失败，
Pass¹ 为 94.74%，最终 0 基础设施错误、0 缺题、0 重复。详细口径和产物见
[TAU2_FULL_RETAIL_REPORT.md](TAU2_FULL_RETAIL_REPORT.md)。

## 今天具体做了什么

### 1. 接入官方环境

- 官方项目：τ2 1.0.1；
- 领域：Retail；
- 使用官方 `db.json`、`tasks.json`、`policy.md` 和 Retail 工具；
- 官方源码放在 `.external/tau2-bench-main`，项目代码不会修改它；
- `.external` 已加入 `.gitignore`，不会把整个第三方仓库提交进本项目。

### 2. 固定 9 道题

任务清单位于 `benchmarks/retail_day2_tasks.json`：

- 取消订单：3 个；
- 退货：3 个；
- 换货：3 个；
- 同时包含官方 train 和 test 任务；
- 每个任务只允许出现一个属于 MVP 范围的写操作。

适配器会自动检查任务 ID、数据划分、意图标签和官方写工具。如果官方数据变化导致清单不再符合约束，验证会直接失败，而不是悄悄换题。

### 3. 运行参考轨迹烟雾测试

烟雾测试把官方提供的参考动作放进真实 Retail 沙箱，检查：

1. 工具能否调用；
2. 消息和工具轨迹能否保存；
3. 最终数据库状态能否被官方评测器识别；
4. 延迟、调用次数、token 和成本字段能否落盘。

本次结果：

| 项目 | 结果 |
|---|---:|
| 任务数 | 9 |
| 最终数据库状态匹配 | 9/9 |
| 工具调用 | 12 次 |
| 模型调用 | 0 次 |
| token | 不适用 |
| 模型成本 | 0 |

任务 38 的参考轨迹先使用错误邮箱查询并得到 `User not found`，之后用姓名和邮编恢复，最终取消成功。这次错误被保留在轨迹里作为诊断信息；τ-bench 按最终数据库状态判定任务是否完成。

### 4. 准备真实单智能体基线

`scripts/run_tau2_llm_baseline.py` 已固定以下条件：

- 同一批 9 个任务；
- 官方 `llm_agent` 和 `user_simulator`；
- 默认使用官方 `llm_agent` 原始提示，不追加项目提示；
- 使用官方数据库、动作参数和自然语言断言评分结果；
- 温度为 0；
- 单并发；
- 固定随机种子 300；
- 保存详细对话、工具、延迟、token 和成本；
- 默认只 dry-run，必须显式传入 `--execute` 才会调用模型。

## 你现在怎么测试

在 PowerShell 中进入项目：

```powershell
cd D:\llm项目\多智能体协作
```

先跑快速单元测试：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

验证官方下载内容和固定任务：

```powershell
python scripts\validate_tau2_retail.py
```

运行不花模型费用的完整环境烟雾测试：

```powershell
python scripts\run_tau2_reference_smoke.py
```

只查看将要执行的真实模型命令：

```powershell
python scripts\run_tau2_llm_baseline.py
```

如果希望直接在本地代码里填写，打开
`src/after_sales_agents/local_secrets.py`，选择 DeepSeek 并把新生成的 Key 填在引号中：

```python
MODEL_PROVIDER = "deepseek"
OPENAI_API_KEY = "粘贴你的 DeepSeek API Key"
```

启动器会在内存中把该值映射为 LiteLLM 官方使用的 `DEEPSEEK_API_KEY`，不会把
Key 写入启动记录。当前基线模型为 `deepseek/deepseek-v4-flash`。

然后执行真实单智能体基线：

```powershell
python scripts\run_tau2_llm_baseline.py --execute
```

`local_secrets.py` 已被 Git 忽略，启动器只记录已配置的变量名，不会记录 Key 内容。
不要把该文件内容复制到日志或提交到其他仓库。

DeepSeek 可能在同一条回复里同时返回说明文字和工具调用。启动器默认采用兼容模式；
如需测量 τ2 严格通信协议，可额外传入 `--enforce-communication-protocol`。
启动适配层还会把 τ2 默认使用 OpenAI 的自然语言评分器切换到同一个 DeepSeek
模型，避免只在含自然语言断言的任务上报缺少 `OPENAI_API_KEY`。这里只替换裁判
模型提供商，不改变官方评分流程；如需连裁判模型也完全一致，需要配置官方默认的
OpenAI 模型凭证。

## DeepSeek 真实基线结果

最终将兼容模式首轮的 6 个正常任务，与评分器修复后恢复的 3 个自然语言断言任务
合并，得到同一固定任务集上的结果：

| 指标 | 结果 |
|---|---:|
| 任务数 | 9 |
| 通过 | 8 |
| 失败 | 1（任务 38） |
| 成功率 | 88.89% |
| 提示 token | 645,466 |
| 完成 token | 33,276 |
| 最终组合轨迹记录成本 | $0.02095387 |
| 最终组合轨迹耗时 | 314.88 秒 |

任务 38 的原始轨迹正确说明了相机是最贵商品且价格为 `$481.50`，也成功取消了
订单，但模拟用户选择的合法取消理由与隐藏参考状态不同，所以最终 DB 不匹配。

修复重跑后，模型调用了 `calculate` 并得到正确总价 `$1,130.85`，订单也正常取消。
官方 τ2 1.0.1 仍给出 `0`：最终 DB 按隐藏参考要求 `no longer needed`，对话中用户却明确
选择 `ordered by mistake`，客服按该选择写入。计算器表达式和 `action_match` 可作为诊断，
但该题的最终 `reward_basis` 是 DB 与 NL 断言，不能把加数顺序误称为硬性扣分原因。

这次重跑证明了金额工具约束有效，但它使用了额外提示，因此不属于官方同提示基线。
项目现已恢复为默认使用官方原始提示，并完全采用官方精确结果：任务 38 为 `0`，
固定基线为 `8/9`。加数重排保留为诊断证据，不再生成 `9/9` 主成绩。
记录成本无法由当前 LiteLLM 版本识别 DeepSeek V4 Flash，实际账单仍以 DeepSeek
控制台为准。

## 输出在哪里

- `artifacts/day2/task_subset_validation.json`：9 个任务的来源和校验结果；
- `artifacts/day2/reference_smoke_report.json`：烟雾测试汇总；
- `artifacts/day2/traces/task_*.json`：每个任务的消息、工具调用、响应、延迟和最终数据库哈希；
- `artifacts/day2/deepseek_baseline_summary.json`：最终 9 任务合并汇总；
- `artifacts/day2/business_compatibility_summary.json`：历史业务诊断说明，不是成绩汇总；
- `artifacts/day2/business_evaluation_task_38.json`：任务 38 的非官方逐项诊断；
- `artifacts/day2/business_evaluation_task_38_before_fix.json`：旧轨迹反例检查；
- `artifacts/day2/llm_baseline_results_task38_business_fix.json`：提示增强后的诊断轨迹；
- `artifacts/day2/llm_baseline_launch_official_parity.json`：官方原始提示模式 dry-run 记录；
- `artifacts/day2/llm_baseline_launch_*.json`：各运行批次的参数和状态；
- `artifacts/day2/llm_baseline_results_compatible.json`：DeepSeek 兼容模式结果；
- `artifacts/day2/llm_baseline_results_recovery_v2.json`：3 个评分恢复任务结果；
- `artifacts/day2/llm_baseline_results_strict.json`：严格通信模式诊断结果。
