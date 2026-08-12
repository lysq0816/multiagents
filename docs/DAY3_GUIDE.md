# 第 3 天说明：政策检索与事实绑定

## 一句话说明

现在系统不会直接凭模型回答“能不能取消、退货或换货”。它先检索带官方出处的政策
条款，再把用户消息和订单工具返回的事实逐项绑定到条款，最后由确定性程序输出
`eligible`、`ineligible` 或 `insufficient_facts`。

第 3 天全部功能不调用模型，也不会产生 API 费用。

## 调用逻辑

```text
用户请求
  -> 检索可引用政策条款
  -> 收集用户/工具/客服消息事实
  -> 按动作逐项检查政策要求
  -> 输出每项 passed / failed / missing
  -> 生成带 fact_ids 和 policy_clause_ids 的结论
```

`eligible` 只表示可以进入操作规划，不代表已经批准或执行。写操作仍必须经过后续
审核和执行器，这部分属于第 6 天范围。

## 1. 可引用政策条款

项目将官方 τ2 Retail policy 拆成 14 条 MVP 条款，保存在：

```text
policies/retail_policy_clauses.json
```

每条包含：

- 稳定条款编号，例如 `retail.cancel.pending_only`；
- 官方原文；
- 官方章节；
- 适用意图和动作；
- 中英文检索标签。

验证脚本会逐条确认保存的原文确实存在于官方
`.external/tau2-bench-main/data/tau2/domains/retail/policy.md`。任意一条对不上，
验证会直接失败。

当前覆盖：

- 通用身份验证、写操作确认和禁止编造；
- 取消订单的状态、理由和退款规则；
- 退货的状态、商品清单、退款方式和结果；
- 换货的状态、同产品可用变体、差价支付和结果。

## 2. 政策检索

接口：

```text
POST /api/v1/policy/search
```

示例：

```json
{
  "query": "取消理由有哪些",
  "intents": ["cancel_order"],
  "actions": ["cancel_order"],
  "top_k": 5
}
```

检索是确定性的，按意图、动作、中英文标签和文本词项评分。相同输入会得到相同排序，
不会让模型临时编造条款。

## 3. 事实绑定资格判断

接口：

```text
POST /api/v1/policy/eligibility
```

每个事实必须包含：

- `fact_id`：稳定引用编号；
- `field`：结构化字段，例如 `order.status`；
- `value`：事实值；
- `subject_id`：对应用户或订单；
- `source_type`：`user`、`tool` 或 `agent`；
- `source_id`：具体消息或工具调用编号。

取消订单会检查：

1. 用户已经验证身份；
2. 客服已经展示操作详情；
3. 用户明确确认；
4. 订单状态为 `pending`；
5. 用户确认了订单号；
6. 理由是 `no longer needed` 或 `ordered by mistake`。

退货和换货具有各自的状态、商品、退款方式、库存、同产品变体和礼品卡余额要求。

结果中的每个检查都有这种结构：

```json
{
  "requirement_id": "cancel.pending_status",
  "status": "passed",
  "fact_ids": ["fact:status"],
  "policy_clause_ids": ["retail.cancel.pending_only"]
}
```

这样可以直接回答：“这个结论用了哪个订单事实，依据官方哪一条政策。”

## 4. 禁止无来源结论和承诺

- 已通过或不符合资格的结论必须至少引用一个事实和一个政策条款；
- 缺少事实时只能返回 `insufficient_facts`，不能猜测资格；
- `BusinessCommitment` 在模型层要求同时提供事实编号和政策条款编号；
- 没有引用的退款时效、资格承诺或执行承诺无法通过数据校验。

## 5. 如何验证

在 PowerShell 中：

```powershell
cd D:\llm项目\多智能体协作
uv run python scripts\validate_policy_grounding.py
uv run pytest -q -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
```

本次结果：

```text
official policy clauses: 14/14 matched
sample cancel decision: eligible
sample model calls: 0
tests: 32 passed
```

验证报告位于：

```text
artifacts/day3/policy_grounding_validation.json
```

## 第 4 天衔接

第 4 天会让订单智能体只负责生成 `SourceFact`，政策智能体只负责检索条款和调用资格
引擎。两个智能体不能直接执行取消、退货或换货，也不能输出没有引用的业务承诺。
