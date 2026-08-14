# 开发日志

本文件记录每次实际开发操作。每条记录包含目标、完成内容、涉及文件、验证结果、遗留问题和下一步，避免只记录结论而无法追溯过程。

## 记录约定

- 日期使用北京时间；
- 只记录已经执行的改动，不把计划写成完成项；
- 测试失败和未解决问题也必须记录；
- 每次开发结束前更新本文件；
- Git 提交号仅在实际提交后填写。

---

## 2026-08-09｜项目迁移与第 1 天工程基础

### 本次目标

将空仓库移动到新的项目目录，固化开发计划，并完成不依赖模型 API 的领域基础与难度路由。

### 已完成

1. 将 Git 仓库从
   `C:\Users\16799\Documents\ChatGPT\多智能体协作`
   移动到 `D:\llm项目\多智能体协作`；
2. 编写 10 个工作日开发计划，确定取消订单、退货、换货三个 MVP 场景；
3. 初始化 Python、FastAPI、Pydantic 和 uv 工程配置；
4. 定义工单意图、业务动作、证据、候选操作、审批状态、审计事件和共享工单状态；
5. 实现确定性难度路由：
   - 信息不足进入澄清流程；
   - 普通任务进入单智能体流程；
   - 多意图、多订单、多写操作、政策冲突或资金与库存耦合时进入多智能体流程；
6. 实现低、中、高三级风险判定；
7. 实现写操作审批限制，未批准的取消、退货、换货和补发动作不可执行；
8. 增加 FastAPI 健康检查及路由预览接口；
9. 增加 7 个领域单元测试；
10. 在 README 中补充项目约束、运行命令和接口示例。

### 涉及文件

- `.gitignore`
- `README.md`
- `pyproject.toml`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DEVLOG.md`
- `src/after_sales_agents/__init__.py`
- `src/after_sales_agents/api.py`
- `src/after_sales_agents/domain/__init__.py`
- `src/after_sales_agents/domain/models.py`
- `src/after_sales_agents/domain/routing.py`
- `tests/test_routing.py`

### 验证结果

```text
python -m unittest discover -s tests -v
Ran 7 tests
OK
```

另外完成：

- Python 源码编译检查通过；
- FastAPI OpenAPI schema 生成通过；
- 已确认 `/health` 和 `/api/v1/routing/preview` 两个接口；
- `git diff --check` 通过。

### 技术决策

- 首版保持模型厂商无关；
- 是否启动多智能体由确定性规则控制；
- 智能体只提出操作计划，确定性工具执行器负责修改业务状态；
- 所有 consequential actions 必须经过明确审批；
- 关键评测使用最终数据库状态与规则，不以 LLM 自评为唯一依据。

### 遗留问题

- 尚未接入 τ-bench Retail；
- 尚未实现实际单智能体调用；
- 尚未安装项目隔离环境；
- 当前变更尚未提交 Git；
- 原项目路径当时因 Codex 进程占用残留空目录，不影响新仓库使用。

### 下一步

第 2 天接入 τ-bench Retail，固定取消、退货和换货任务子集，并生成第一份单智能体基线结果。

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-12｜首次发布到 GitHub

### 本次目标

将本地项目安全地初始化提交并推送到用户创建的 GitHub 仓库。

### 已完成

1. 确认仓库此前没有提交、远程地址和 Git 提交身份；
2. 对 136 个候选文件做体积与敏感字符串检查，总体积约 3.65 MB；
3. 确认 `local_secrets.py`、对应字节码、`.env`、虚拟环境和外部依赖均被 Git 忽略；
4. 暂存后再次检查，没有敏感路径进入索引；
5. 仅为当前仓库配置 GitHub 用户名和 GitHub 隐私提交邮箱；
6. 创建首次提交 `4f8fc6c`，提交说明为
   `Initial commit: retail after-sales multi-agent MVP`；
7. 将本地分支从 `master` 改为 `main`；
8. 配置远程仓库 `https://github.com/lysq0816/multiagents.git`；
9. 通过 Git Credential Manager 的用户授权完成首次推送；
10. 比较本地与远程提交哈希，确认 `origin/main` 与本地 `main` 完全一致。

### 安全结果

```text
tracked local_secrets.py: false
tracked local secret bytecode: false
tracked .env: false
API/GitHub token pattern matches before commit: 0
```

### 远程地址

`https://github.com/lysq0816/multiagents`

---

## 2026-08-10｜第 3 天：政策检索与事实绑定

### 本次目标

将官方 Retail 政策拆成稳定、可引用条款，实现确定性检索，并确保取消、退货和换货
资格结论同时引用来源事实和政策条款，禁止无来源判断与承诺。

### 已完成

1. 读取并核对官方 τ2 1.0.1 Retail `policy.md`；
2. 建立 `tau2-retail-1.0.1-mvp` 政策目录，拆分 14 条官方原文条款；
3. 为每条政策保存稳定编号、章节、原文、适用意图、适用动作和中英文标签；
4. 实现来源验证：14 条保存原文必须逐字存在于官方政策文件；
5. 实现确定性政策检索，支持查询文本、业务意图、动作和 `top_k`；
6. 定义 `SourceFact`，强制记录事实字段、值、主体、来源类型和来源编号；
7. 定义 `passed`、`failed`、`missing` 三种逐项要求状态；
8. 实现取消订单资格检查：身份验证、详情展示、明确确认、订单状态、订单号和理由；
9. 实现退货资格检查：身份验证、确认、已送达状态、商品清单和合法退款方式；
10. 实现换货资格检查：已送达状态、商品清单、库存、同产品不同选项、支付方式和
    礼品卡余额；
11. 结论统一返回 `eligible`、`ineligible` 或 `insufficient_facts`；
12. 每个结论保存全部 `fact_ids` 与 `policy_clause_ids`，缺事实时禁止猜测；
13. 新增 `BusinessCommitment` 引用约束，没有事实和政策来源的承诺无法通过模型校验；
14. 新增 `/api/v1/policy/search` 和 `/api/v1/policy/eligibility` 两个接口；
15. FastAPI 版本更新为 `0.2.0`；
16. 新增政策验证脚本，生成包含检索结果和完整取消资格轨迹的 Day 3 JSON 报告；
17. 新增 12 项政策测试，覆盖官方原文、中文检索、三类动作、缺失事实、非法退款
    方式、礼品卡余额不足、重复事实和无来源承诺；
18. 更新开发计划、README 和第 3 天使用说明。

### 涉及文件

- `policies/retail_policy_clauses.json`
- `src/after_sales_agents/policy/__init__.py`
- `src/after_sales_agents/policy/models.py`
- `src/after_sales_agents/policy/catalog.py`
- `src/after_sales_agents/policy/eligibility.py`
- `src/after_sales_agents/api.py`
- `scripts/validate_policy_grounding.py`
- `tests/test_policy.py`
- `artifacts/day3/policy_grounding_validation.json`
- `README.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DAY3_GUIDE.md`
- `docs/DEVLOG.md`

### 验证结果

```text
official policy clauses: 14/14 matched
sample search hits: 6
sample cancel decision: eligible
sample decision fact citations: 6
sample decision policy citations: 4
model calls: 0

uv run pytest -q -p no:cacheprovider
32 passed
```

### 技术决策

- 资格判断由确定性程序完成，不使用 LLM 自评；
- 项目保存官方原文摘录而不修改 `.external` 官方文件；
- `eligible` 仅允许进入规划，不等于批准或执行；
- 订单事实、用户确认和客服详情展示分别引用工具或消息来源；
- 缺少事实时返回 `insufficient_facts`，不得默认补全；
- 政策检索保留可解释评分原因，相同输入得到相同结果；
- 第 3 天不调用 DeepSeek，不产生模型费用。

### 遗留问题

- 当前事实由 API 请求或验证脚本提供，尚未由订单智能体自动采集；
- 当前政策检索是确定性标签和词项检索，尚未接入第 4 天政策智能体；
- 写操作仍不会执行，需等待审核与执行器阶段；
- 当前项目变更尚未提交 Git。

### 下一步

第 4 天实现订单智能体和政策智能体：订单智能体只产出带来源的 `SourceFact`，政策
智能体只检索条款并调用资格引擎，两者使用结构化消息交接并限制工具权限。

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-10｜第 4 天：订单与政策智能体

### 本次目标

实现订单智能体和政策智能体，使用不可混淆的结构化消息交接，并以最小权限限制
每位智能体可以调用的工具。

### 已完成

1. 定义 `OrderSpecialistRequest`、`OrderFactBundle` 和换货目标结构；
2. 实现只读订单智能体，通过工具读取订单状态并生成带来源 `SourceFact`；
3. 订单状态被设为工具专属事实，请求方直接提供会被拒绝；
4. 实现换货商品验证，读取商品变体并派生库存、同产品和不同选项事实；
5. 为派生事实增加 `derived_from_source_ids`，保留原始工具和用户消息链路；
6. 定义 `OrderToPolicyHandoff 1.0`，固定发送者为订单智能体、接收者为政策智能体；
7. 实现政策智能体，只能检索条款并调用第 3 天资格引擎；
8. 定义 `PolicyToPlannerHandoff 1.0`，固定发送者为政策智能体、接收者为规划器；
9. 实现 `ToolPermissionGuard` 和显式工具白名单；
10. 订单智能体只允许 `get_order_details`、`get_product_details`；
11. 政策智能体只允许 `policy_search`、`policy_eligibility`；
12. 两位智能体均禁止取消、退货和换货写工具，越权时抛出 `ToolPermissionDenied`；
13. 实现 `SpecialistWorkflow`，完成订单事实到政策结论的确定性编排；
14. 新增 `/api/v1/collaboration/review`，FastAPI 版本更新为 `0.3.0`；
15. 新增 9 项专业智能体测试，覆盖权限、伪造、篡改、缺失确认、取消与换货；
16. 新增不调用模型的双专家演示脚本和完整结构化轨迹；
17. 更新开发计划、README 和第 4 天使用说明。

### 涉及文件

- `src/after_sales_agents/agents/__init__.py`
- `src/after_sales_agents/agents/models.py`
- `src/after_sales_agents/agents/permissions.py`
- `src/after_sales_agents/agents/order_specialist.py`
- `src/after_sales_agents/agents/policy_specialist.py`
- `src/after_sales_agents/agents/workflow.py`
- `src/after_sales_agents/policy/models.py`
- `src/after_sales_agents/api.py`
- `tests/test_agents.py`
- `scripts/run_day4_collaboration_demo.py`
- `artifacts/day4/collaboration_demo.json`
- `README.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DAY4_GUIDE.md`
- `docs/DEVLOG.md`

### 验证结果

```text
uv run pytest -q -p no:cacheprovider
41 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
42 files already formatted
```

协作演示：

```text
order specialist allowed tools: get_order_details, get_product_details
policy specialist allowed tools: policy_search, policy_eligibility
order-to-policy handoff: valid
policy-to-planner handoff: valid
decision: eligible
write tool calls: 0
model calls: 0
```

### 技术决策

- 第 4 天先验证角色边界、结构化协议和工具权限，不引入 LLM 随机性；
- 权限检查位于工具入口，而不只依赖提示词；
- 订单智能体不能解释政策，政策智能体不能读取或修改订单；
- 结构化 handoff 使用固定 schema、角色和 `case_id`；
- `eligible` 只交给规划器，不授权执行写操作；
- 当前订单和商品工具使用快照沙箱，后续再接官方 τ2 只读适配器；
- 本次没有调用 DeepSeek，没有产生模型费用。

### 遗留问题

- 尚未实现第 5 天规划器和跨智能体冲突消解；
- 当前专业智能体为确定性组件，尚未接入可选 LLM 推理层；
- 当前只读工具使用请求提供的沙箱快照，尚未直接连接官方 τ2 工具；
- 所有写操作仍然不可执行；
- 当前项目变更尚未提交 Git。

### 下一步

第 5 天实现方案汇总、候选操作计划和订单/商品/金额/政策冲突检测；信息不足或冲突
时退回澄清流程，仍不允许规划器执行写工具。

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-10｜第 5 天：方案汇总与冲突消解

### 本次目标

汇总同一工单内的一份或多份专业智能体结论，生成可审计候选动作，并在订单、商品、
金额、政策或信息来源存在问题时阻断或退回澄清。

### 已完成

1. 扩展 `PolicyReviewBundle`，把订单号和完整来源事实传给规划器，并校验动作、事实
   引用和政策引用彼此一致；
2. 增加 `exchange.target_item_ids` 事实，由订单智能体根据用户目标请求派生并保存来源；
3. 将 handoff 编号扩展为工单、动作和订单组合，使一个工单可以同时汇总多类动作；
4. 定义 `ready_for_review`、`needs_clarification`、`blocked` 三种规划状态；
5. 定义候选动作、规划问题、冲突类型、严重程度、规划请求和工作流结果模型；
6. 实现确定性 `CandidateActionPlanner`，只接收结构化政策 handoff，不调用 LLM；
7. 实现订单状态矛盾检测；
8. 实现同一订单取消与退货/换货互斥检测；
9. 实现同一商品同时退货和换货的商品冲突检测；
10. 实现同一操作差价不一致的金额冲突检测；
11. 实现同一操作资格状态不一致的政策冲突检测；
12. 实现重复动作检测，并把重复动作和金额问题退回明确澄清；重复 handoff 会按出现
    顺序获得稳定后缀，不会在进入规划器前因编号相同而失败；
13. 将不同商品组合划分为不同操作范围，避免把同一订单的不同商品误判为重复动作；
14. 资格为 `eligible` 时生成带 `fact_ids` 和 `policy_clause_ids` 的候选动作；
15. 资格为 `insufficient_facts` 时不生成动作，返回缺失字段和澄清问题；
16. 资格为 `ineligible` 或存在硬冲突时把整组方案标记为 `blocked`；
17. 所有候选动作固定 `requires_approval=true`、`can_execute=false`；
18. 在权限白名单中显式设置规划器可用工具为空，读工具和写工具都不可调用；
19. 实现 `PlanningWorkflow`，串联多份第 4 天双专家结果与规划器；
20. 新增 `/api/v1/planning/review`，FastAPI 版本更新为 `0.4.0`；
21. 新增 9 项规划器测试，完整测试数从 41 增加到 50；
22. 新增第 5 天演示脚本，同时生成“可送审”和“冲突阻断”两种轨迹；
23. 生成 `artifacts/day5/planning_demo.json`，记录模型调用 0、写工具调用 0；
24. 因 handoff schema 扩展，重新生成第 4 天协作演示产物；
25. 更新开发计划、README 和第 5 天说明。

### 涉及文件

- `src/after_sales_agents/planning/__init__.py`
- `src/after_sales_agents/planning/models.py`
- `src/after_sales_agents/planning/planner.py`
- `src/after_sales_agents/planning/workflow.py`
- `src/after_sales_agents/agents/models.py`
- `src/after_sales_agents/agents/order_specialist.py`
- `src/after_sales_agents/agents/policy_specialist.py`
- `src/after_sales_agents/agents/permissions.py`
- `src/after_sales_agents/policy/models.py`
- `src/after_sales_agents/api.py`
- `tests/test_planning.py`
- `tests/test_agents.py`
- `scripts/run_day5_planning_demo.py`
- `artifacts/day5/planning_demo.json`
- `artifacts/day4/collaboration_demo.json`
- `README.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DAY5_GUIDE.md`
- `docs/DEVLOG.md`

### 验证结果

首次对新增代码运行 Ruff 时发现 3 个导入排序问题，使用 Ruff 自动整理后全部修复。

```text
uv run pytest -q -p no:cacheprovider
50 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
49 files already formatted
```

第 5 天演示摘要：

```text
ready scenario: ready_for_review
candidate actions: 1
ready can advance to review: true
ready can execute: false

conflict scenario: blocked
conflict types: order, order
conflict can advance to review: false
conflict can execute: false

model calls: 0
write tool calls: 0
```

### 技术决策

- 规划器是确定性汇总器，不依赖 LLM 自己判断冲突；
- 规划器没有工具权限，只能读取 handoff 中已经带来源的事实；
- `eligible` 不等于整组方案可送审，`ready_for_review` 也不等于批准或执行；
- 硬冲突优先级高于澄清问题，只要存在一个硬冲突，整组方案即为 `blocked`；
- 金额不一致和完全重复动作先要求澄清，不擅自选择某个值或重复执行；
- 即使方案被阻断，也保留已通过资格判断的候选动作，供后续人工定位冲突；
- 本次没有调用 DeepSeek，没有产生模型费用。

### 遗留问题

- 尚未实现第 6 天独立审核员及批准、修改、拒绝状态；
- 当前规划结果不能调用任何写工具，也不会改变订单状态；
- 当前订单和商品读取仍使用请求提供的沙箱快照；
- 当前项目变更尚未提交 Git。

### 下一步

第 6 天实现独立审核与人工确认：重新校验实体、动作顺序、政策前置条件和引用证据，
在写操作前提供批准、修改或拒绝门控，并保留完整审核记录。

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-12｜第 6 天：独立审核与人工确认

### 本次目标

在第 5 天候选方案后增加独立确定性审核和人工决策门控，确保实体、动作顺序、事实与
政策引用及写工具参数一致；批准不自动执行，修改必须重审，并能够比较执行前后状态。

### 已完成

1. 核对官方 τ2 1.0.1 取消、退货和换货工具签名及执行后的订单字段；
2. 发现退货和换货工具需要具体 `payment_method_id`，而现有事实只有支付方式类型；
3. 新增 `payment.method_id` 来源事实，退货和换货资格判断必须确认具体 ID 存在；
4. 调整候选退货参数为 `item_ids + payment_method_id`；
5. 调整候选换货参数为官方签名 `item_ids + new_item_ids + payment_method_id`；
6. 为每个候选动作增加从 1 开始的连续 `sequence`；
7. 定义审核检查类型、检查状态、审核状态、人工决定、批准状态和状态校验状态；
8. 实现 `IndependentAuditor`，只读取完整 `PlanningWorkflowResult`，不调用模型或工具；
9. 实现规划门槛检查：只有 `ready_for_review`、无冲突且有候选动作的计划才能审核；
10. 实现实体检查：工单、订单、动作、商品及来源 handoff 必须一致；
11. 实现动作顺序检查：序号必须连续唯一，同一订单不能被多个顺序写动作重复修改；
12. 实现证据检查：动作引用的每个事实和政策条款必须存在于来源 handoff；
13. 实现政策检查：来源结论必须为 `eligible`，且各动作引用全部强制政策条款；
14. 实现前置条件检查：动作参数名、参数值、订单状态、商品清单、换货目标、付款方式
    和取消理由必须与来源事实一致；
15. 定义取消、退货和换货的预期状态及关键字段变化；
16. 实现稳定规划摘要：SHA-256 覆盖专家 handoff 与计划内容，排除自动变化的时间戳；
17. 实现 `HumanApprovalGate`，人工决策前重新运行审核并拒绝旧审核或篡改审核；
18. 支持批准：生成绑定审核、摘要、动作、预期状态和批准人的单次执行授权；
19. 批准结果显式区分 `execution_authorized=true` 与
    `can_execute_now=false/write_executed=false`，本阶段不执行写工具；
20. 支持修改：输出修改后的动作，但清空授权并要求重新规划和审核；
21. 支持拒绝：不生成授权，不允许执行；
22. 审核员权限显式设为空，读工具和写工具都不可调用；
23. 实现 `PostExecutionVerifier`，比较授权预期与执行前后订单快照；
24. 状态校验支持 `matched`、`not_executed`、`mismatch` 三种结果；
25. 新增审核、人工决策和状态校验三个 API，FastAPI 版本更新为 `0.5.0`；
26. 新增 15 项审核测试，完整测试数从 50 增加到 65；
27. 新增第 6 天演示脚本，走通规划、审核、人工批准和模拟状态校验；
28. 演示产物明确标记模拟后快照、模型调用 0、写工具调用 0；
29. 按新增支付方式 ID 重新生成第 5 天演示产物；
30. 更新开发计划、README 和第 6 天说明。

### 涉及文件

- `src/after_sales_agents/review/__init__.py`
- `src/after_sales_agents/review/models.py`
- `src/after_sales_agents/review/auditor.py`
- `src/after_sales_agents/review/approval.py`
- `src/after_sales_agents/review/verification.py`
- `src/after_sales_agents/policy/models.py`
- `src/after_sales_agents/policy/eligibility.py`
- `src/after_sales_agents/planning/models.py`
- `src/after_sales_agents/planning/planner.py`
- `src/after_sales_agents/agents/permissions.py`
- `src/after_sales_agents/api.py`
- `tests/test_review.py`
- `tests/test_policy.py`
- `tests/test_agents.py`
- `tests/test_planning.py`
- `scripts/run_day5_planning_demo.py`
- `scripts/run_day6_review_demo.py`
- `artifacts/day5/planning_demo.json`
- `artifacts/day6/review_demo.json`
- `README.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DAY6_GUIDE.md`
- `docs/DEVLOG.md`

### 验证结果

新增审核代码首轮 Ruff 检查发现 3 个非业务问题：两个导入顺序和一个未使用导入，
自动整理后全部修复。

首轮完整测试：

```text
uv run pytest -q -p no:cacheprovider
64 passed
```

终检前继续增加授权内部一致性、订单/政策 handoff 交叉一致性、订单状态工具来源和
篡改订单 handoff 测试；最终结果：

```text
uv run pytest -q -p no:cacheprovider
65 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
57 files already formatted
```

第 6 天演示摘要：

```text
planning status: ready_for_review
audit status: awaiting_human_decision
plan_gate: passed
entity: passed
action_order: passed
evidence: passed
policy: passed
precondition: passed
human decision: approve
execution authorized: true
can execute now: false
write executed: false
simulated state verification: matched
model calls: 0
write tool calls: 0
```

### 技术决策

- 审核员使用独立确定性实现，不复用规划器的“最终结论”作为唯一依据；
- 审核输入包含完整专家轨迹，候选动作不能只靠自带引用字符串通过审核；
- 授权绑定完整规划摘要，不能移植到另一份事实、政策或候选动作；
- 人工修改不继承原审核授权，必须重审；
- 本阶段只生成未来执行器可消费的授权，不提供写工具执行入口；
- 状态校验器要求前后快照发生变化，避免把原本已是目标状态误报为执行成功；
- 演示中的执行后快照明确为模拟数据，不表示真实订单被修改；
- 本次没有调用 DeepSeek，没有产生模型费用。

### 遗留问题

- 尚未实现消费单次授权的幂等写执行器；
- 尚未实现第 7 天人工审批界面和持久化审核记录；
- 当前订单和商品读取仍使用请求提供的沙箱快照；
- 当前项目变更尚未提交 Git。

### 下一步

第 7 天实现轻量业务界面：展示工单、协作时间线、事实和政策证据、候选动作、审核检查，
并提供批准、修改和拒绝操作；界面不直接绕过授权调用写工具。

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-12｜第 7 天：轻量业务工作台

### 本次目标

把工单对话、专业智能体协作、证据、候选动作、独立审核和人工决定放在一个可直接启动
的页面里，同时保持“批准不等于执行”的安全边界。

### 已完成

1. 在 FastAPI 中挂载 `/ui` 和本地静态资源，根路径 `/` 跳转到工作台；
2. 实现取消、退货、换货三个内置演示场景；
3. 展示工单对话、订单/政策智能体时间线、事实来源和政策条款；
4. 展示候选动作参数、风险、规划问题和六类独立审核检查；
5. 支持批准、修改、拒绝三个决定；修改后必须重审，拒绝不产生授权；
6. 批准只签发单次授权，页面明确显示 `can_execute_now=false` 和
   `write_executed=false`；
7. 状态差异使用明确标记的模拟快照，不调用订单写工具；
8. UI 不使用 npm、CDN、外部字体、`httpx` 或 `TestClient`；
9. API 版本由 `0.5.0` 更新到 `0.6.0`，旧版本测试改为最低兼容断言；
10. 新增第 7 天说明与 5 项 ASGI/静态资源/写边界测试。

### 涉及文件

- `src/after_sales_agents/api.py`
- `src/after_sales_agents/ui/index.html`
- `src/after_sales_agents/ui/assets/app.css`
- `src/after_sales_agents/ui/assets/app.js`
- `tests/test_ui.py`
- `docs/DAY7_GUIDE.md`

### 验证结果

```text
第 7 天专项测试：5 passed
JavaScript 语法：passed
界面文件 Ruff：All checks passed
```

### 技术决策与边界

- 页面渲染真实后端规划/审核响应，不在前端复制政策判定；
- `/ui` 不加入业务 OpenAPI；
- 界面不暴露第 9 天沙箱执行器，防止把演示授权误当成真实订单执行；
- 本次没有模型调用或真实业务写操作。

---

## 2026-08-12｜第 8 天：四架构离线实验矩阵

### 本次目标

用同一批固定故障注入场景比较单智能体、固定多智能体、难度路由多智能体和带独立审核
的路由多智能体，并保留完整逐次记录。

### 已完成

1. 固定 30 个离线任务：取消、退货、换货各 10 个；
2. 覆盖正常流程、信息缺失、政策冲突、库存冲突、多订单、证据/参数错配和重复动作；
3. 每个任务在 4 种架构下重复 3 次，共生成 360 条运行记录；
4. 记录成功率、处置正确率、政策违规、未授权写、人工转接、逻辑角色/工具调用、
   确定性延迟代理和一致性；
5. 模型调用为 0，token 与模型成本保持 `null`，真实和未授权写均为 0；
6. 报告增加生成时间、任务清单 SHA-256 和实验代码版本；
7. 生成 JSON 全量报告和 Markdown 汇总报告；
8. 新增 9 项任务平衡、矩阵完整性、确定性、零写和报告测试。

### 结果

```text
single_agent:                    success 50%, policy violations 24
fixed_multi_agent:               success 80%, policy violations 18
routed_multi_agent:              success 80%, policy violations 18
routed_multi_agent_with_audit:   success 100%, policy violations 0
all architectures:               consistency 100%
```

### 解释边界

这些数字是手工定义控制流在本地确定性故障注入任务上的结果，不是实际 LLM 质量成绩、
不是官方 τ2 成绩，也不能单独证明多智能体在真实业务上必然提升。“延迟”是操作预算代理
值，不是墙钟耗时。实验运行器根本不暴露写工具。

### 涉及文件

- `benchmarks/retail_day8_tasks.json`
- `src/after_sales_agents/benchmark/experiment_models.py`
- `src/after_sales_agents/benchmark/experiment_matrix.py`
- `scripts/run_day8_experiment.py`
- `tests/test_experiment_matrix.py`
- `docs/DAY8_GUIDE.md`
- `artifacts/day8/experiment_report.json`
- `artifacts/day8/experiment_report.md`

---

## 2026-08-12｜第 9 天：可靠性、安全与成本优化

### 本次目标

为已审核链路增加明确的超时/重试边界、只读缓存、通信裁剪、注入与冒用防护、成本台账，
并在纯内存沙箱中验证单次授权和幂等执行语义。

### 已完成

1. 只读操作支持有上限的超时、重试和退避，记录每次尝试；
2. 写操作只尝试一次，不自动重试；
3. 写线程超过调用方截止时间后必须先结束，再返回超时并回滚，避免后台迟到写；
4. 只读 TTL 缓存采用防御性深拷贝并支持按主体失效；
5. 通信裁剪优先保留事实和政策证据；
6. 检测忽略指令、身份冒用、绕过审批和强制写工具四类提示注入；
7. 使用 HMAC-SHA256 绑定发送者、接收者、工单号和载荷；
8. 按工单类型统计模型/工具/缓存调用、重试、token 和估算成本；
9. 沙箱执行器要求可信授权注册、摘要匹配、单次消费和幂等键；
10. 成功写入后做状态核验；核验失败、普通异常或超时均回滚；
11. 同一请求幂等重放不增加物理写，同一授权换幂等键被拒绝；
12. 新增可靠性演示、JSON 产物和最终 19 项专项测试。

### 验证结果

```text
第 9 天专项测试：19 passed
模型调用：0
估算模型成本：0
真实系统连接：false
成功写：仅内存沙箱 1 次并验证提交
注入失败写：只尝试 1 次并回滚
```

### 生产边界

- 当前锁、授权消费和幂等表均为单进程内存实现；
- 生产接入仍需要数据库唯一约束、持久幂等表、跨进程事务和服务端截止时间；
- HMAC 演示密钥是固定测试值，生产必须改为密钥管理服务；
- `sandbox_only` 被模型约束为只能是 `true`，没有真实电商适配器或凭证。

### 涉及文件

- `src/after_sales_agents/reliability/`
- `tests/test_reliability.py`
- `scripts/run_day9_reliability_demo.py`
- `docs/DAY9_GUIDE.md`
- `artifacts/day9/reliability_demo.json`

---

## 2026-08-12｜第 10 天：部署、演示与最终交付

### 本次目标

提供统一演示、5 个稳定业务工单、离线发布自检和 Docker 交付配置，并统一 README、
10 天计划、分日说明、版本与日志。

### 已完成

1. 新增 Dockerfile、Compose、健康检查和 `.dockerignore`；
2. 容器上下文排除本地密钥、环境文件、实验产物、外部官方仓库、测试与缓存；
3. 新增 5 个稳定业务演示：取消、退货、换货、缺少确认、同商品退换货冲突；
4. 新增统一离线入口，依次运行第 4、5、6、8、9、10 天共 6 个演示；
5. 统一演示结果 `6/6`，模型调用和真实业务写调用均为 0；
6. 新增发布自检：全量测试、Ruff、格式、OpenAPI、14 条政策、UI、实验矩阵、
   6 个演示脚本和容器文件；
7. 项目包、应用与锁文件版本统一为 `0.6.0`；
8. 更新 README、开发计划和第 10 天说明；
9. 独立只读审计验证 wheel 可构建且包含 UI 静态资源，未发现明文 Key 模式；
10. 针对独立审计建议收紧 `sandbox_only`、慢写超时回滚和实验报告溯源字段。
11. 收尾敏感信息扫描发现被忽略的 `local_secrets.pyc` 仍含可恢复的本地 Key 痕迹；
    删除该可再生缓存，并让凭证加载器导入本地密钥模块时禁止生成字节码；
12. 修复 Wheel 最初只包含 UI、不包含政策 JSON 的问题：将 14 条政策作为包资源打入
    Wheel，并为源码目录和已安装包提供双路径加载；
13. 统一演示子进程强制 UTF-8，修复 Windows 捕获输出中的中文乱码；
14. 临时构建 `after_sales_mas-0.6.0-py3-none-any.whl`，确认包含 UI 与政策 JSON，且不含
    `local_secrets` 文件。

### 首次发布自检失败与处理

第一次运行 `scripts/verify_release.py` 时，业务和测试检查均通过，但自检整体为失败：

```text
pytest: 103 passed
ruff check: passed
ruff format --check: failed (scripts/verify_release.py 仅格式问题)
```

随后用 Ruff 格式化该脚本，并保留失败过程记录；最终自检在本节写完后重新运行并覆盖
失败报告。

### 最终验收结果

最终整合中还捕获并修复了一次类型导入回归：把 `sandbox_only` 收紧为
`Literal[True]` 后漏导入 `Literal`，导致统一演示短暂为 `5/6`、全量测试 7 项失败。
补充导入并先跑 19 项可靠性专项后，再次运行统一入口和发布自检：

```text
统一离线演示：6/6
全量测试：105 passed
Ruff check：All checks passed
Ruff format --check：passed
release_verification：passed true
API version：0.6.0
required API paths：present
policy clauses：14
model calls：0
real business write calls：0
```

最终报告已覆盖写入 `artifacts/day10/release_verification.json`，其中 Docker 运行时仍明确
标记为未验证。

### Docker 验证边界

当前开发机没有 Docker CLI，因此没有实际执行 `docker compose config/build/up`，不能声称
镜像已在本机成功构建。Dockerfile、Compose 结构和密钥排除由自动化测试覆盖；交付到
Docker 可用主机后仍需补跑实际构建与启动。

### 涉及文件

- `Dockerfile`
- `compose.yaml`
- `.dockerignore`
- `scripts/run_all_demos.py`
- `scripts/run_delivery_scenarios.py`
- `scripts/verify_release.py`
- `tests/test_demo_registry.py`
- `tests/test_delivery_scenarios.py`
- `tests/test_release.py`
- `docs/DAY10_GUIDE.md`
- `artifacts/day10/all_demos.json`
- `artifacts/day10/delivery_scenarios.json`
- `artifacts/day10/release_verification.json`
- `README.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DEVLOG.md`

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-10｜任务 38 失败诊断、计算器约束与双评分修复

### 本次目标

解释任务 38 的失败原因，在不修改官方 τ2 1.0.1 源码和不覆盖官方成绩的前提下，
修复金额计算工具调用，并建立可审计的本地业务兼容评分。

### 已完成

1. 核对原始任务 38 场景、标准动作、完整消息轨迹、工具响应和奖励明细；
2. 确认原始轨迹的两个失败点：
   - 模型直接心算最低选项总价，没有调用 `calculate`；
   - 模拟用户选择 `ordered by mistake`，而唯一标准答案为 `no longer needed`；
3. 确认两种取消理由都在 Retail 政策允许范围内，且任务场景本身没有指定理由；
4. 在项目启动适配层中增加 `auditable_money_calculation_v1` 指令配置，要求所有金额
   加减、合计和额度比较先调用 `calculate`；
5. 通过环境变量向官方 `llm_agent` 追加指令，未修改 `.external` 中的官方源码；
6. 新增本地业务评分器和命令行入口，官方奖励始终作为独立字段原样保存；
7. 为取消理由兼容、缺少计算器、场景明确指定理由和加数重排分别增加测试；
8. 用旧轨迹做反例验证：取消成功但没有计算器调用，官方分 `0`、业务分 `0`；
9. 只对任务 `38` 执行一次 DeepSeek 付费重跑，未重跑其余 8 个任务；
10. 重跑轨迹正常以 `USER_STOP` 结束，耗时 `55.25` 秒，实际执行了：
    `calculate("466.75 + 288.82 + 135.24 + 46.66 + 193.38")`，工具返回
    `1130.85`，随后成功取消订单；
11. 调查重跑仍被官方判为 `0` 的原因：官方标准表达式把最后两项写成
    `193.38 + 46.66`，模型写成 `46.66 + 193.38`；τ2 1.0.1 使用参数精确匹配，
    不识别加法交换律；取消理由也仍与唯一标准答案不同；
12. 将本地计算兼容限制为：加数多重集合完全相同、真实计算器调用成功、返回总价
    正确。该规则不接受心算、缺项、多项或失败的工具响应；
13. 用新轨迹做正例验证：官方奖励保持 `0`，本地业务奖励为 `1`，六项业务检查
    全部通过；
14. 生成任务级报告和双口径汇总，固定 9 任务的官方成绩保持 `8/9`，本地业务兼容
    口径为 `9/9`；
15. 更新 README 和第 2 天说明，补充运行方式、评分边界和产物位置。

### 涉及文件

- `scripts/run_tau2_llm_baseline.py`
- `scripts/tau2_with_model_overrides.py`
- `scripts/evaluate_business_result.py`
- `src/after_sales_agents/benchmark/business_evaluator.py`
- `tests/test_business_evaluator.py`
- `README.md`
- `docs/DAY2_GUIDE.md`
- `docs/DEVLOG.md`
- `artifacts/day2/llm_baseline_launch_task38_business_fix.json`
- `artifacts/day2/llm_baseline_results_task38_business_fix.json`
- `artifacts/day2/business_evaluation_task_38_before_fix.json`
- `artifacts/day2/business_evaluation_task_38.json`
- `artifacts/day2/business_compatibility_summary.json`

### 验证结果

```text
uv run pytest -q -p no:cacheprovider
18 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
24 files already formatted
```

任务 38 重跑结果：

```text
termination: USER_STOP
official reward: 0.0
official DB: 0.0
official NL assertions: 1.0
local business reward: 1.0
calculate tool result: 1130.85
cancel tool status: cancelled
```

### 技术决策

- 官方成绩与本地业务成绩始终并列展示，禁止用本地分覆盖或改写官方分；
- 只兼容可证明等价的加数重排，不做泛化的模糊工具参数匹配；
- 只有场景未指定取消理由时，才允许政策规定的两种合法理由；
- DeepSeek V4 Flash 尚未被当前 LiteLLM 成本表识别，轨迹中的 `$0.0000` 不代表
  实际免费，账单以 DeepSeek 控制台为准；
- 第三方官方源码保持只读，所有适配均位于本项目代码中。

### 遗留问题

- 任务 38 的官方严格奖励仍为 `0`，这是精确参数标准与对话中合法选择不唯一导致，
  不能把本地业务兼容分称为官方 τ2 分数；
- 当前项目变更仍未提交 Git。

### Git

- 分支：`master`
- 提交：尚未提交

## 2026-08-10：增加本地代码填写 API Key 的入口

### 已完成

1. 新增 `src/after_sales_agents/local_secrets.py`，供用户在本机代码中填写模型 Key；
2. 将该文件加入 `.gitignore`，避免凭证被 Git 跟踪；
3. 新增 `model_credentials.py`，启动时自动读取本地配置，同时保留环境变量优先级；
4. 修改真实 LLM 基线启动器，使本地配置自动传递给官方 τ2 子进程；
5. 更新第 2 天操作说明。启动记录仍只保存变量名，不保存 Key 内容。

### 安全说明

- 聊天中曾经暴露的旧 Key 未写入任何项目文件；
- 用户已在本机填写 `local_secrets.py`；助手仅检查非空状态，未读取或显示 Key 内容。

## 2026-08-10：本地 API Key 配置检查

### 已完成

1. 在不读取、不输出 Key 内容的前提下运行真实基线启动器 dry-run；
2. 启动器成功识别 `OPENAI_API_KEY`；
3. `artifacts/day2/llm_baseline_launch.json` 状态由 `prepared_missing_api_key` 更新为 `prepared`；
4. 本次检查未发起模型请求，因此未产生模型费用，也尚未验证 Key 的联网有效性。

## 2026-08-10：切换真实基线到 DeepSeek

### 已完成

1. 用户说明已填写的是 DeepSeek API Key 后，立即终止了错误使用 `gpt-4.1-mini` 的测试；
2. 检查并确认没有残留的 τ2 或 Python 基线进程；
3. 按 DeepSeek 与 LiteLLM 官方接口要求增加 `DEEPSEEK_API_KEY` 支持；
4. 将默认客服智能体和用户模拟器模型改为 `deepseek/deepseek-v4-flash`；
5. 增加本地旧填写槽到 DeepSeek 环境变量的内存映射，未读取或复制 Key 内容；
6. 增加 DeepSeek 凭证映射测试，并同步更新第 2 天操作说明。

### 首次执行情况

- DeepSeek `/models` 预检返回 HTTP 200，可用模型包含 `deepseek-v4-flash` 和 `deepseek-v4-pro`；
- 首次正式命令在模型调用前退出：τ2 发现旧的同名结果并尝试交互确认续跑，非交互终端触发 `EOFError`；
- 旧结果未删除或覆盖，默认输出目录改为独立的 `after_sales_day2_deepseek_v4_flash` 后重新执行。

### 严格通信模式结果与诊断

- 9 个任务全部执行完毕，平均奖励 `0.2222`，通过任务为 `75`、`88`；
- 7 个失败任务均以 `AGENT_ERROR` 结束；
- 逐条核对轨迹和 τ2 编排器源码后确认，失败原因是 DeepSeek 同时返回文本和工具调用，触发 τ2 的严格通信协议，并非 7 次业务工具执行失败；
- 保留严格模式结果，并增加默认关闭严格通信校验的 DeepSeek 兼容模式；两种结果使用独立目录和文件，不混合统计。

### 兼容模式首轮结果与评分器诊断

- 9 个任务中 6 个正常评估且全部通过，平均奖励 `1.0000`；
- 任务 `38`、`70`、`108` 被标记为基础设施错误，不纳入 τ2 的奖励统计；
- 三个任务恰好是固定子集中仅有的自然语言断言任务。检查官方源码确认 `NLAssertionsEvaluator` 硬编码使用 OpenAI `gpt-4.1`，因此在只有 DeepSeek Key 时评分失败；
- 新增 `tau2_with_model_overrides.py`，在不修改官方源码的情况下把自然语言评分器切换到 DeepSeek，并支持只重跑指定的固定任务；
- 启动器新增评分模型、任务子集和独立产物标签参数，准备只恢复这 3 个评分失败任务。

### 第一次评分器恢复尝试

- 任务 `38`、`70` 仍出现基础设施错误后主动终止批次，避免任务 `108` 重复等待和计费；
- 根因是导入 `tau2.config` 时，τ2 包初始化已将默认 OpenAI 模型绑定到评分器模块，之后仅修改配置常量不会影响已导入的评分器；
- 启动适配层调整为同时覆盖配置常量与评分器模块常量，官方源码仍保持未修改。

### 最终恢复与合并结果

- 覆盖验证：配置层与实际 `NLAssertionsEvaluator` 使用的评分模型均为 `deepseek/deepseek-v4-flash`；
- 恢复 v2 正常完成任务 `38`、`70`、`108`，不再出现 OpenAI Key 或评分基础设施错误；
- 任务 `70`、`108` 通过，任务 `38` 的两条自然语言断言通过，但预期业务动作未完成，最终奖励为 0；
- 将兼容模式首轮的 6 个正常结果与恢复 v2 的 3 个结果合并：通过 `8/9`，成功率 `88.89%`；
- 最终 9 条组合轨迹记录提示 token `645,466`、完成 token `33,276`、成本 `$0.02095387`、累计对话耗时 `314.88` 秒；
- 上述成本不包含严格模式、基础设施失败重试和 API 预检，完整账单以 DeepSeek 控制台为准；
- 单元测试 `14 passed`，Ruff 静态检查与格式检查通过；
- 生成 `artifacts/day2/deepseek_baseline_summary.json`，并同步更新 README、第 2 天说明和开发计划。

---

## 2026-08-09｜第 2 天：τ-bench Retail 与单智能体基线

### 本次目标

接入官方 τ-bench Retail 环境，固定取消、退货、换货任务子集，保存可审计轨迹，并生成第一份可复现的单智能体基线运行方案。

### 已完成

1. 获取并核对官方 `tau2-bench` 源码：
   - 路径：`.external/tau2-bench-main`；
   - 版本：`tau2 1.0.1`；
   - Retail 的 `tasks.json`、`split_tasks.json`、`db.json`、`policy.md`、环境和工具源码齐全；
2. 使用 `uv sync --no-dev` 创建官方项目隔离环境并安装 77 个核心包；
3. 使用官方 `tau2 check-data` 完成数据目录校验；
4. 新增 τ-bench 适配器，支持：
   - 自动发现 Git clone 或 GitHub ZIP 解压后的目录；
   - 校验官方版本和必需文件；
   - 读取 Retail 任务与 train/test/base 划分；
   - 校验固定任务的 ID、划分、意图和写工具；
5. 固定 9 个官方 Retail 任务：
   - 取消：任务 `38`、`88`、`90`；
   - 退货：任务 `73`、`83`、`108`；
   - 换货：任务 `70`、`75`、`80`；
   - 每类 3 个，同时覆盖 train 和 test；
6. 实现参考轨迹烟雾测试：
   - 在真实 Retail 沙箱执行官方参考动作；
   - 保存用户场景、消息、工具参数、工具响应、错误、延迟和最终 DB 哈希；
   - 使用官方 `EnvironmentEvaluator` 比较最终数据库状态；
7. 为 9 个任务各保存一份 JSON 轨迹，并生成汇总报告；
8. 实现真实 LLM 单智能体基线启动器：
   - 固定同一批 9 个任务；
   - 使用官方 `llm_agent` 与 `user_simulator`；
   - 固定温度 0、随机种子 300、单并发和运行上限；
   - 默认 dry-run，只有显式传入 `--execute` 才会调用模型；
   - 检查 API Key 是否存在，但不读取或记录 Key 内容；
9. 增加 4 个适配器测试，总测试数由 7 个增加到 11 个；
10. 创建本项目 `.venv`，安装 pytest 和 Ruff，并生成 `uv.lock`；
11. 编写第 2 天通俗说明、测试步骤和结果解释。

### 涉及文件

- `.gitignore`
- `README.md`
- `uv.lock`
- `benchmarks/retail_day2_tasks.json`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DAY2_GUIDE.md`
- `docs/DEVLOG.md`
- `scripts/validate_tau2_retail.py`
- `scripts/run_tau2_reference_smoke.py`
- `scripts/run_tau2_llm_baseline.py`
- `src/after_sales_agents/benchmark/__init__.py`
- `src/after_sales_agents/benchmark/models.py`
- `src/after_sales_agents/benchmark/tau2_adapter.py`
- `src/after_sales_agents/benchmark/reference_smoke.py`
- `src/after_sales_agents/domain/models.py`
- `tests/test_tau2_adapter.py`
- `artifacts/day2/task_subset_validation.json`
- `artifacts/day2/reference_smoke_report.json`
- `artifacts/day2/llm_baseline_launch.json`
- `artifacts/day2/traces/task_*.json`

第三方源码和它的虚拟环境位于 `.external/`，已被 Git 忽略，没有修改官方源码。

### 验证结果

官方数据检查：

```text
tau2 check-data
✅ Data directory exists
You can now run tau2 commands.
```

固定任务校验：

```text
tau2 version: 1.0.1
task count: 9
cancel: 3
return: 3
exchange: 3
```

参考轨迹烟雾测试：

```text
final DB match: 9/9
environment pass rate: 1.0
tool calls: 12
model calls: 0
token: null
model cost: 0
```

代码质量：

```text
uv run pytest -q
11 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
18 files already formatted
```

另外完成：

- Python `compileall` 通过；
- FastAPI OpenAPI schema 生成通过；
- `/health` 和 `/api/v1/routing/preview` 仍然存在；
- 9 份轨迹与 3 份汇总/启动记录均可解析为 JSON。

### 过程中发现的问题与处理

1. 两次 `git clone` 均因当前网络无法连接 GitHub 失败；官方 ZIP 下载也长时间无响应。用户手动下载后继续接入；
2. 第一次运行 `tau2 check-data` 时，Windows GBK 终端无法输出 `✅`，触发 `UnicodeEncodeError`。设置 `PYTHONUTF8=1` 后校验通过；
3. 初选任务 `74` 还包含修改另一笔订单商品的写操作，超出首版单一售后动作边界，因此替换为任务 `38`，并加强适配器以识别全部 7 个官方 Retail 写工具；
4. 第一次烟雾结果为 `8/9`。调查轨迹后确认任务 `38` 的官方参考流程故意先用错误邮箱查询并失败，再用姓名和邮编恢复，最终 DB 已正确匹配。统计口径调整为与 τ-bench 一致的最终状态判断，同时保留工具错误作为诊断，重跑结果为 `9/9`；
5. Ruff 首轮发现 4 个 Python 3.12+ 现代化写法问题，修正后静态检查与格式检查均通过。

### 技术决策

- 官方仓库作为只读外部环境使用，项目通过适配器接入，不复制或修改官方业务实现；
- 固定任务清单独立于运行器，后续单智能体和多智能体必须使用同一批任务；
- 参考动作烟雾测试只证明环境、工具、轨迹和评测链路可用，明确标记为不可与真实 LLM 成绩比较；
- 正确性遵循 τ-bench 的最终数据库状态评测，参考动作中的可恢复查询错误只作为诊断；
- 真实模型运行默认 dry-run，避免意外产生模型费用；
- token 和成本字段始终保留；没有模型调用时使用 `null` 和 `0`，不伪造数值。

### 遗留问题

- 本地 `OPENAI_API_KEY` 已被启动器识别，但真实 `llm_agent + user_simulator` 基线尚未执行；
- `artifacts/day2/llm_baseline_launch.json` 状态已更新为 `prepared`；
- 当前所有项目变更仍未提交 Git。

### 下一步

1. 用户确认模型调用费用后运行：
   `python scripts\run_tau2_llm_baseline.py --execute`；
2. 保存真实模型的对话、工具调用、最终状态、延迟、token 和成本；
3. 开始第 3 天的政策检索与事实绑定开发。

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-13｜完整官方 Retail base 单轮评测

### 本次目标

不再只跑固定 9 题，而是使用官方 τ2 1.0.1 Retail `base` split 全部 114 题，
完成 DeepSeek V4 Flash 单轮基线并保存可审计轨迹。

### 已完成

1. 为 `run_tau2_llm_baseline.py` 增加 `--all-base-tasks`，全量时省略 `--task-ids`；
2. 为官方检查点增加 `--auto-resume` 透传；
3. 将完整性验收改为 `任务数 × num_trials`；
4. 要求每个 `(task_id, trial)` 唯一，无缺失、无 `infrastructure_error`、每条有官方奖励；
5. 新增离线汇总工具，分离有效失败、基础设施错误和未评分条目；
6. 运行完整 114 题，固定客服/用户/裁判模型、温度 0、并发 1、seed 300；
7. 首轮任务 6 因空模型响应留下基础设施错误，单独归档首轮证据；
8. 用官方同一 `save-to` 检查点续跑，保留 113 个正常条目并只补测任务 6；
9. 最终结果 114/114 有效，108 通过、6 失败，Pass¹ 94.74%；
10. 失败任务为 38、59、64、79、100、105；最终无缺题、重复或基础设施错误；
11. 生成 JSON/Markdown 汇总和完整中文报告；
12. 本次使用官方任务、工具、沙箱和评分代码，但自然语言裁判也使用 DeepSeek，
    所以明确不称为官方默认裁判配置。

### 结果边界

- 这是完整 Retail 单轮成绩，不是τ2全领域 Overall；
- 官方允许单域提交，但强烈建议每域至少 4 trials；
- 本次 1 trial 不足以计算更高的 Passᵏ，不冒充提交级稳定性结论；
- LiteLLM 没有正确识别 DeepSeek V4 Flash 价格映射，结果文件数值未声明币种，
  真实费用以 DeepSeek 控制台为准。

### 涉及文件

- `scripts/run_tau2_llm_baseline.py`
- `scripts/summarize_tau2_results.py`
- `tests/test_tau2_full_base_runner.py`
- `tests/test_tau2_results_summary.py`
- `docs/TAU2_FULL_RETAIL_REPORT.md`
- `docs/DAY2_GUIDE.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DEVLOG.md`
- `README.md`
- `artifacts/day2/llm_baseline_*_retail_base_full*`

---

## 2026-08-10｜恢复官方测试口径为默认逻辑

### 本次目标

将此前为了诊断任务 38 增加的提示增强和本地兼容分从主测试逻辑中移出，使后续
基线默认使用官方 τ2 客服提示和官方精确评分。

### 已完成

1. 将默认客服提示配置改为 `official_tau2`；
2. 启动子进程前主动清除可能从父进程继承的 `TAU2_AGENT_INSTRUCTION_SUFFIX`，
   防止历史提示覆盖污染官方基线；
3. 将 `auditable_money_calculation_v1` 改为必须显式选择的诊断配置；
4. 把运行配置抽取到 `tau2_runtime.py`，供启动器和测试共用；
5. 新增两项隔离测试：官方配置必须删除提示覆盖，诊断配置必须显式加入计算器提示；
6. 将本地业务结果标记为 `business_reward_is_diagnostic_only: true`，官方奖励作为
   `benchmark_reward`；
7. 删除文档中的“业务口径 9/9”主成绩表述，固定任务集只报告官方 `8/9`；
8. 保留历史增强轨迹和业务诊断文件作为根因证据，没有删除或覆盖旧产物；
9. 生成不调用 API 的官方对齐启动记录，确认：
   - `agent_instruction_profile: official_tau2`；
   - `official_agent_prompt: true`；
   - 状态为 `prepared`；
10. 本次只运行本地测试和 dry-run，没有调用 DeepSeek API，没有新增模型费用。

### 涉及文件

- `scripts/run_tau2_llm_baseline.py`
- `scripts/evaluate_business_result.py`
- `src/after_sales_agents/benchmark/tau2_runtime.py`
- `src/after_sales_agents/benchmark/business_evaluator.py`
- `tests/test_tau2_runner.py`
- `README.md`
- `docs/DAY2_GUIDE.md`
- `docs/DEVLOG.md`
- `artifacts/day2/business_compatibility_summary.json`
- `artifacts/day2/llm_baseline_launch_official_parity.json`

### 验证结果

```text
uv run pytest -q -p no:cacheprovider
20 passed

uv run ruff check .
All checks passed!

uv run ruff format --check .
26 files already formatted
```

### 当前统一口径

- 后续默认基线：官方客服提示、官方工具和数据库、官方精确评分；
- 自然语言评分器：流程不变，当前因凭证条件使用 DeepSeek 代替官方默认 OpenAI
  裁判；若要模型也完全一致，需要另配 OpenAI Key；
- 当时固定 9 题基准成绩：`8/9`；
- 任务 38 的本地业务值：仅诊断，不计入成绩；
- 历史提示增强运行：仅诊断，不与官方基线合并。

### Git

- 分支：`master`
- 提交：尚未提交

---

## 2026-08-14｜完整官方 Retail base 四轮评测

### 本次目标

在 2026-08-13 已完成的 114 题单轮基础上，继续运行到官方强烈建议的每题 4 trials，
补齐基础设施失败，使用 τ2 官方代码计算 Pass¹–Pass⁴，并保存可提交、可复核的完整产物。

### 已完成

1. 先生成不调用模型的四轮 dry-run，确认完整 Retail `base`、114 题、4 轮、预期 456 条，
   命令未传 `--task-ids`，客服提示为官方原始提示；
2. 在单轮 checkpoint 上新增目标轨迹 342 条；扩轮初段并发为 1，确认 checkpoint 可安全恢复后
   将 `--max-concurrency` 设为 3，模型、任务、seed、提示和评分口径未改变；
3. 为启动器增加 `--max-concurrency` 参数透传与单元测试；
4. 运行期间 trial 1 的任务 21、trial 2 的任务 65、trial 3 的任务 23 因空模型响应留下
   `infrastructure_error`；使用官方相同 `save-to` 与 `--auto-resume` 只补失败项，最终全部成功评分；
5. 最终覆盖 114 题 × 4 轮，共 456 个唯一 `(task_id, trial)`，0 缺失、0 意外、0 重复、
   0 未评分、0 基础设施错误；
6. 各轮结果：trial 0 为 108/114，trial 1 为 101/114，trial 2 为 103/114，trial 3 为
   109/114；总计 421 条通过、35 条失败；
7. 直接调用 τ2 1.0.1 官方 `compute_metrics`：Pass¹ 92.32%、Pass² 87.43%、Pass³
   83.33%、Pass⁴ 79.82%；
8. 发现官方从单轮 checkpoint 扩展时保留旧 `info.num_trials=1`，导致官方指标入口只显示
   Pass¹；启动器现在仅在 456 条全部验收通过后，把复制产物的描述性元数据规范化为 4，
   不修改任何轨迹或奖励；
9. 发现 τ2 1.0.1 在 Windows 的 `Results.load()` 未显式指定编码；复制产物继续使用 JSON
   ASCII 转义，避免 UTF-8 中文被系统 GBK 解码失败；
10. 重新生成 JSON/Markdown 汇总，覆盖率为 456/456，missing、unexpected、duplicate 均为 0；
11. 更新 README、第 2 天说明、开发计划和完整 Retail 报告，保留单轮结果为历史 trial 0；
12. 明确结果边界：这是官方 `llm_agent` 单智能体的 Retail 单域四轮基线，不是项目自定义
    多智能体成绩，也不是 τ2 全领域 Overall。

### 四轮结果

| 指标 | 结果 |
|---|---:|
| 有效轨迹 | 456/456 |
| 通过 / 失败轨迹 | 421 / 35 |
| Pass¹ | 92.32% |
| Pass² | 87.43% |
| Pass³ | 83.33% |
| Pass⁴ | 79.82% |
| 最终基础设施错误 | 0 |

### 涉及文件

- `scripts/run_tau2_llm_baseline.py`
- `tests/test_tau2_full_base_runner.py`
- `README.md`
- `docs/DAY2_GUIDE.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/DEVLOG.md`
- `docs/TAU2_FULL_RETAIL_REPORT.md`
- `artifacts/day2/llm_baseline_launch_retail_base_4trials*.json`
- `artifacts/day2/llm_baseline_results_retail_base_4trials.json`
- `artifacts/day2/llm_baseline_summary_retail_base_4trials.json`
- `artifacts/day2/llm_baseline_summary_retail_base_4trials.md`

### 验证结果

```text
uv run pytest tests\test_tau2_full_base_runner.py tests\test_tau2_results_summary.py tests\test_tau2_runner.py -q
13 passed

uv run ruff check scripts\run_tau2_llm_baseline.py tests\test_tau2_full_base_runner.py
All checks passed!

uv run ruff format --check scripts\run_tau2_llm_baseline.py tests\test_tau2_full_base_runner.py
2 files already formatted
```

规范化后的结果已由 τ2 官方 `Results.load()` 读取，并由官方 `compute_metrics()` 输出
Pass¹–Pass⁴；覆盖汇总为 456/456，最终基础设施错误为 0。

### 费用与解释边界

- 本轮调用了 DeepSeek 客服、用户模拟器和 40 道含自然语言断言任务的裁判，产生真实 API
  费用；LiteLLM 未正确识别该模型的价格映射，实际金额以 DeepSeek 控制台为准；
- 过程里出现过可恢复的空响应，不能写成“全程 0 基础设施错误”；最终交付产物为 0；
- 35 是失败轨迹数，不是 35 道唯一失败题；
- 本项目多智能体主链路尚未实现 τ2 `Agent` 适配器，不能把本结果用于证明多智能体提升。
