# 第 6 天说明：独立审核与人工确认

## 一句话说明

第 5 天的候选方案现在必须先经过独立审核，再由人工批准、修改或拒绝。人工批准只会
产生一份绑定完整规划轨迹摘要的单次授权，不会自动调用取消、退货或换货写工具。

第 6 天全部逻辑仍是确定性程序，不调用 DeepSeek，也不产生模型费用。

## 完整安全链路

```text
第 5 天 PlanningWorkflowResult
  -> 独立审核员
       -> 规划门槛
       -> 实体一致性
       -> 动作顺序
       -> 事实引用
       -> 政策引用
       -> 写工具参数与来源事实
  -> 审核拒绝 / 等待人工决定
  -> 人工批准 / 修改 / 拒绝
       -> 批准：生成绑定摘要的授权，但不执行
       -> 修改：原审核失效，必须重新规划与审核
       -> 拒绝：无授权
  -> 未来执行器执行写操作（尚未实现）
  -> 执行前后快照差异校验
```

## 1. 独立审核检查什么

| 检查 | 主要内容 |
|---|---|
| `plan_gate` | 规划状态必须是 `ready_for_review`，并且没有冲突项 |
| `entity` | 工单、订单、动作、商品及来源 handoff 必须一致 |
| `action_order` | 序号从 1 连续递增；同一订单不能顺序执行多个互相失效的写动作 |
| `evidence` | 候选动作引用的事实和政策必须真实存在于来源 handoff |
| `policy` | 每类动作必须包含全部强制政策条款，来源结论必须为 `eligible` |
| `precondition` | 写工具参数必须完整，并与订单状态、商品、付款方式和取消理由来源一致 |

审核员没有读工具或写工具权限。它只能交叉检查已经存在的完整规划轨迹，避免“审核时
又查了一套不同数据”造成竞态。

## 2. 为什么补了 `payment.method_id`

官方 τ2 退货和换货工具接收的是具体 `payment_method_id`，例如
`credit_card_0000000`，而不是只有 `credit_card` 这一类型。前 5 天只有支付方式类型，
还不足以形成完整写工具参数。

现在退货和换货资格必须同时具备：

```text
payment.method_id
payment.method_type
payment.method_exists
```

候选动作只保存官方工具实际需要的参数：

```text
return:   item_ids + payment_method_id
exchange: item_ids + new_item_ids + payment_method_id
cancel:   reason
```

## 3. 批准、修改和拒绝

### 批准

审核全部通过后，人工可以批准。系统生成 `ExecutionAuthorization`，包含：

- 审核编号；
- 完整规划轨迹的 SHA-256 摘要；
- 被批准的完整候选动作；
- 预期订单状态变化；
- 批准人和时间；
- `single_use: true`。

但返回值仍明确写着：

```text
execution_authorized: true
can_execute_now: false
write_executed: false
```

含义是“允许未来受控执行器使用”，不是“本接口已经执行”。

### 修改

人工可以修改动作参数或商品清单，但修改后的动作：

```text
authorization: null
requires_re_review: true
execution_authorized: false
```

修改不会沿用旧审核，必须重新生成事实一致的计划并再次审核。

### 拒绝

拒绝不会产生任何执行授权，也不会调用写工具。

## 4. 防止旧审核或篡改结果被批准

人工决策请求必须同时提交完整规划结果和审核结果。系统会重新运行确定性审核，并比较
除时间戳之外的全部字段；如果摘要、动作、检查结果或引用被篡改，会返回错误，不能
批准。

规划摘要覆盖专业智能体 handoff 和最终计划，排除每次运行自动变化的时间戳，因此：

- 同一业务输入可得到稳定摘要；
- 任何事实、政策结论、候选参数或冲突状态变化都会改变摘要；
- 授权不能被移植到另一份计划。

## 5. 执行后状态校验

当前没有写执行器，但已经实现独立状态校验器。未来执行器提供执行前、执行后快照后，
校验结果有三种：

| 状态 | 含义 |
|---|---|
| `matched` | 快照发生变化，且状态和关键字段都符合预期 |
| `not_executed` | 前后快照完全相同，写操作没有发生 |
| `mismatch` | 数据发生变化，但结果与授权预期不一致 |

取消、退货和换货的预期状态分别为：

```text
cancel_order   -> cancelled
create_return  -> return requested
exchange_items -> exchange requested
```

校验器还会比较取消理由、退货商品/付款方式、换货原商品/新商品/付款方式。

## 6. API 和演示

新增接口：

```text
POST /api/v1/review/audit
POST /api/v1/review/decision
POST /api/v1/review/verify-state
```

运行演示：

```powershell
cd D:\llm项目\多智能体协作
uv run python scripts\run_day6_review_demo.py
```

完整结果：

```text
artifacts/day6/review_demo.json
```

演示输出：

```text
planning_status: ready_for_review
audit_status: awaiting_human_decision
6 audit checks: passed
human_decision: approve
execution_authorized: true
can_execute_now: false
write_executed: false
simulated_state_verification: matched
```

最后的 `matched` 使用脚本中明确标记的模拟执行后快照，只验证比较逻辑；没有真正修改
订单。演示报告同时记录：

```text
after_snapshot_is_simulated: true
model_calls: 0
write_tool_calls: 0
```

## 7. 如何验证

```powershell
uv run pytest -q -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
```

当前结果：

```text
65 passed
All checks passed!
```

新增测试覆盖：审核通过、非就绪计划、候选参数与订单 handoff 篡改、人工批准、修改、
拒绝、旧审核防护、无修改内容、状态匹配、未执行、状态不一致、审核员零工具权限和
OpenAPI 路径。

## 第 7 天衔接

第 7 天会把工单、智能体时间线、事实/政策证据、候选动作、审核检查以及批准/修改/拒绝
按钮放进轻量界面。写执行器仍不会因为增加界面而自动启用。
