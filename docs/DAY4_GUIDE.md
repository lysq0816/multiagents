# 第 4 天说明：订单智能体与政策智能体

## 一句话说明

现在一个售后请求会先交给只读的订单智能体收集订单和商品事实，再通过固定结构交给
政策智能体检索条款、判断资格。两位智能体都没有取消、退货或换货写权限。

第 4 天使用确定性智能体组件验证协作协议，不调用模型，也不产生 API 费用。

## 协作流程

```text
协作请求
  -> 权限守卫
  -> 订单智能体
       -> get_order_details
       -> 按需 get_product_details
       -> 生成带来源 SourceFact
  -> OrderToPolicyHandoff 1.0
  -> 政策智能体
       -> policy_search
       -> policy_eligibility
       -> 生成带引用资格结论
  -> PolicyToPlannerHandoff 1.0
  -> 第 5 天规划器
```

## 1. 订单智能体

订单智能体只负责读取和整理事实：

- 订单状态必须来自 `get_order_details`，不能由请求方直接填写；
- 换货目标的库存、产品归属和选项差异来自 `get_product_details`；
- 用户确认、取消理由等事实保留原始消息来源；
- 聚合事实保存 `derived_from_source_ids`，可以追溯到原始工具调用或用户消息。

它不会检索政策，也不能调用任何写工具。

## 2. 政策智能体

政策智能体接收订单智能体的结构化事实后：

1. 根据动作检索第 3 天建立的政策条款；
2. 调用确定性资格引擎；
3. 输出每项 `passed`、`failed` 或 `missing`；
4. 把结论及其 `fact_ids`、`policy_clause_ids` 交给后续规划器。

它不能读取订单数据库，也不能调用写工具。

## 3. 最小工具权限

| 智能体 | 允许工具 |
|---|---|
| 订单智能体 | `get_order_details`、`get_product_details` |
| 政策智能体 | `policy_search`、`policy_eligibility` |

明确禁止两者调用：

- `cancel_pending_order`；
- `return_delivered_order_items`；
- `exchange_delivered_order_items`。

越权请求会抛出 `ToolPermissionDenied`，不会尝试执行。

## 4. 结构化交接

订单到政策的消息固定为：

```text
schema_version: 1.0
handoff_type: order_facts
sender: order_specialist
recipient: policy_specialist
payload: OrderFactBundle
```

政策到规划器的消息固定为：

```text
schema_version: 1.0
handoff_type: policy_decision
sender: policy_specialist
recipient: planner
payload: PolicyReviewBundle
```

发送者、接收者、`case_id` 或 payload 不匹配时无法通过 Pydantic 校验，因此不能用
自由文本冒充另一位智能体的结果。

## 5. API 和演示

接口：

```text
POST /api/v1/collaboration/review
```

当前接口接收一个沙箱订单快照、可选商品快照和带来源的用户事实，然后返回两份完整
handoff。它不会执行写操作。

运行演示：

```powershell
cd D:\llm项目\多智能体协作
uv run python scripts\run_day4_collaboration_demo.py
```

输出：

```text
artifacts/day4/collaboration_demo.json
```

本次演示结果：

```text
order specialist tools: get_order_details
policy specialist tools: policy_search, policy_eligibility
decision: eligible
write tool calls: 0
model calls: 0
```

## 6. 如何验证

```powershell
uv run pytest -q -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
```

当前结果：

```text
41 passed
```

测试覆盖：工具越权、订单状态伪造、handoff 角色篡改、缺少用户确认、取消资格和换货
商品事实派生。

## 第 5 天衔接

第 5 天的规划器只接收 `PolicyToPlannerHandoff`，汇总候选动作并检测订单、商品、金额
和政策冲突。即使资格为 `eligible`，规划器仍不能直接执行写工具。
