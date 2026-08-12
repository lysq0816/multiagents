# 第 5 天说明：方案汇总与冲突消解

## 一句话说明

规划器会把一个工单中的一份或多份政策结论汇总成候选动作；缺信息时要求澄清，
发现冲突时阻断。它没有任何工具权限，所以无论结果如何都不能修改订单。

第 5 天全部逻辑是确定性程序，不调用 DeepSeek，也不产生模型费用。

## 完整流程

```text
一个工单中的一份或多份售后请求
  -> 订单智能体读取订单/商品快照
  -> 政策智能体逐项判断资格
  -> PolicyToPlannerHandoff 1.0
  -> 规划器汇总
       -> 检查缺失事实
       -> 检查订单、商品、金额、政策和重复动作
       -> 生成有事实与政策引用的候选动作
  -> ready_for_review / needs_clarification / blocked
  -> 第 6 天独立审核
```

## 1. 三种规划结果

| 状态 | 含义 | 下一步 |
|---|---|---|
| `ready_for_review` | 资格通过且未发现冲突 | 只能送到第 6 天独立审核 |
| `needs_clarification` | 缺少事实，或金额/重复请求需要确认 | 回到用户或工具补充信息后重算 |
| `blocked` | 政策不允许，或存在硬冲突 | 不得送审或执行，需修改方案 |

最容易混淆的区别：

```text
eligible         = 单个政策智能体认为“具备进入规划的资格”
ready_for_review = 规划器确认整组动作之间没有冲突，可以进入独立审核
approved         = 第 6 天审核员明确批准；目前还没有实现
executed         = 写工具真正修改订单；目前绝不会发生
```

因此当前所有候选动作都固定为：

```text
requires_approval: true
can_execute: false
```

## 2. 当前检测的冲突

| 类型 | 示例 | 处理 |
|---|---|---|
| 订单冲突 | 同一订单同时被读取为 `pending` 和 `delivered` | `blocked` |
| 订单动作冲突 | 同一订单同时取消并退货或换货 | `blocked` |
| 商品冲突 | 同一商品既要退货又要换货 | `blocked` |
| 金额冲突 | 同一换货操作出现两个不同差价 | `needs_clarification` |
| 政策冲突 | 同一操作的资格结论互相矛盾 | `blocked` |
| 重复动作 | 同一订单、动作和商品被重复提交 | `needs_clarification`，询问是否合并 |

不同商品上的同类动作使用不同操作范围，不会仅因为都是退货或换货就被误判为重复。

## 3. 候选动作长什么样

一份可送审的取消计划包含：

```json
{
  "action_type": "cancel_order",
  "order_id": "#W9348897",
  "arguments": {
    "reason": "no longer needed"
  },
  "fact_ids": ["..."],
  "policy_clause_ids": ["..."],
  "requires_approval": true,
  "can_execute": false
}
```

换货计划还会保存当前商品 ID、目标商品 ID、支付方式和已知差价。所有计划必须同时
引用 `fact_ids` 和 `policy_clause_ids`；没有引用就无法通过模型校验。

## 4. 缺信息时怎么处理

如果政策智能体返回 `insufficient_facts`，规划器不会生成候选动作，而是返回明确字段，
例如：

```text
Please provide or verify the required field: user.confirmed.
```

这表示系统缺少“用户明确确认”的来源事实，不表示 API 或模型调用失败。

## 5. API 与本地演示

新增接口：

```text
POST /api/v1/planning/review
```

请求中的 `reviews` 可以包含同一个 `case_id` 下的一份或多份第 4 天协作请求。接口会
返回每份专家 handoff、最终候选计划、冲突项和澄清问题。

运行两个内置场景：

```powershell
cd D:\llm项目\多智能体协作
uv run python scripts\run_day5_planning_demo.py
```

控制台只打印最重要的摘要：

```text
ready_scenario: ready_for_review, candidate_count=1, can_execute=false
conflict_scenario: blocked, conflict_types=[order, order], can_execute=false
```

完整过程保存在：

```text
artifacts/day5/planning_demo.json
```

其中：

1. `ready_for_review` 是一笔状态为 `pending`、事实和政策均完整的取消请求；
2. `blocked_by_order_conflict` 故意把同一订单同时作为 `pending` 取消和 `delivered`
   退货，规划器检测到状态矛盾及互斥动作并阻断。

## 6. 如何验证

```powershell
uv run pytest -q -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
```

当前结果：

```text
50 passed
All checks passed!
```

新增测试覆盖：正常候选、缺少确认、政策拒绝、订单状态/动作冲突、退换货商品冲突、
换货金额冲突、政策结论冲突、规划器零工具权限和 OpenAPI 路径。

## 第 6 天衔接

第 6 天会增加独立审核员，检查候选动作的实体、顺序、证据与政策前置条件，并提供
批准、修改和拒绝状态。审核完成前，写工具仍然不会执行。
