"use strict";

const ORDER_ID = "#W9348897";

function fact(caseId, field, value, sourceType) {
  return {
    fact_id: `fact:${caseId}:${field}`,
    field,
    value,
    subject_id: ORDER_ID,
    source_type: sourceType,
    source_id: `ui:${caseId}:${field}`,
  };
}

function commonFacts(caseId) {
  return [
    fact(caseId, "user.authenticated", true, "tool"),
    fact(caseId, "action.details_presented", true, "agent"),
    fact(caseId, "user.confirmed", true, "user"),
  ];
}

const scenarios = {
  cancel: {
    caseId: "CASE-UI-CANCEL",
    intent: "未发货订单取消",
    orderStatus: "pending",
    userMessage: "这件商品还没发货，我不需要了。请取消订单 #W9348897。",
    agentMessage: "将取消整张订单并原路退款。取消理由为 no longer needed。是否确认？",
    confirmation: "确认。",
    expectedLabel: "pending · 待处理",
    request() {
      const caseId = this.caseId;
      return {
        reviews: [{
          analysis: {
            case_id: caseId,
            action_type: "cancel_order",
            order_id: ORDER_ID,
            provided_facts: [
              ...commonFacts(caseId),
              fact(caseId, "order.id_confirmed", true, "user"),
              fact(caseId, "cancel.reason", "no longer needed", "user"),
            ],
          },
          order_snapshot: {order_id: ORDER_ID, status: "pending"},
          product_snapshots: {},
        }],
      };
    },
  },
  return: {
    caseId: "CASE-UI-RETURN",
    intent: "已收货商品退货",
    orderStatus: "delivered",
    userMessage: "订单 #W9348897 已经收到，我要退掉 item-blue。",
    agentMessage: "将退回 item-blue，退款到原信用卡 credit_card_1。是否确认？",
    confirmation: "确认。",
    expectedLabel: "delivered · 已送达",
    request() {
      const caseId = this.caseId;
      return {
        reviews: [{
          analysis: {
            case_id: caseId,
            action_type: "create_return",
            order_id: ORDER_ID,
            provided_facts: [
              ...commonFacts(caseId),
              fact(caseId, "order.id_confirmed", true, "user"),
              fact(caseId, "request.item_ids", ["item-blue"], "user"),
              fact(caseId, "payment.method_id", "credit_card_1", "tool"),
              fact(caseId, "payment.method_exists", true, "tool"),
              fact(caseId, "payment.method_type", "credit_card", "tool"),
              fact(caseId, "payment.method_is_original", true, "tool"),
            ],
          },
          order_snapshot: {order_id: ORDER_ID, status: "delivered"},
          product_snapshots: {},
        }],
      };
    },
  },
  exchange: {
    caseId: "CASE-UI-EXCHANGE",
    intent: "已收货商品换货",
    orderStatus: "delivered",
    userMessage: "我想把订单 #W9348897 的红色款 item-red 换成蓝色款 item-blue。",
    agentMessage: "蓝色款有货，属于同一商品的不同选项；支付方式为 credit_card_1。是否确认换货？",
    confirmation: "确认。",
    expectedLabel: "delivered · 已送达",
    request() {
      const caseId = this.caseId;
      return {
        reviews: [{
          analysis: {
            case_id: caseId,
            action_type: "exchange_items",
            order_id: ORDER_ID,
            provided_facts: [
              ...commonFacts(caseId),
              fact(caseId, "payment.method_id", "credit_card_1", "tool"),
              fact(caseId, "payment.method_type", "credit_card", "tool"),
              fact(caseId, "payment.method_exists", true, "tool"),
              fact(caseId, "exchange.price_difference", "0.00", "tool"),
            ],
            exchange_targets: [{
              product_id: "product-1",
              current_item_id: "item-red",
              target_item_id: "item-blue",
              source_id: `ui:${caseId}:exchange-target`,
            }],
          },
          order_snapshot: {order_id: ORDER_ID, status: "delivered"},
          product_snapshots: {
            "product-1": {
              product_id: "product-1",
              variants: {
                "item-red": {available: true, options: {color: "red"}},
                "item-blue": {available: true, options: {color: "blue"}},
              },
            },
          },
        }],
      };
    },
  },
};

const translations = {
  cancel_order: "取消订单",
  create_return: "创建退货",
  exchange_items: "创建换货",
  ready_for_review: "可进入审核",
  needs_clarification: "需要补充信息",
  blocked: "已阻断",
  awaiting_human_decision: "等待人工决定",
  rejected_by_auditor: "审核拒绝",
  passed: "通过",
  failed: "失败",
  approved: "已批准（未执行）",
  modification_requires_review: "修改后需重审",
  rejected: "已拒绝",
  matched: "符合预期",
  mismatch: "状态不一致",
  not_executed: "未执行",
};

const state = {
  scenario: "cancel",
  planning: null,
  audit: null,
  decision: null,
  authorization: null,
};

const byId = (id) => document.getElementById(id);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function valueText(value) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 0);
}

function humanTime(timestamp) {
  if (!timestamp) return "完成";
  return new Date(timestamp).toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit", second: "2-digit"});
}

function showToast(message, isError = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.className = `toast visible${isError ? " error" : ""}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { toast.className = "toast"; }, 3200);
}

async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return data;
}

function renderScenario() {
  const scenario = scenarios[state.scenario];
  byId("case-id").textContent = scenario.caseId;
  byId("intent-label").textContent = scenario.intent;
  byId("order-id").textContent = ORDER_ID;
  byId("order-status").textContent = scenario.expectedLabel;
  byId("plan-status").textContent = "待运行";
  byId("plan-status").className = "status-text idle";
  byId("risk-label").textContent = "等待事实与政策审查";
  byId("timeline-state").textContent = "尚未开始";
  byId("timeline-state").className = "tag muted";
  byId("audit-state").textContent = "等待规划";
  byId("audit-state").className = "tag muted";

  const conversation = byId("conversation");
  conversation.replaceChildren();
  [
    ["user", "客户", scenario.userMessage],
    ["agent", "客服智能体", scenario.agentMessage],
    ["user", "客户", scenario.confirmation],
  ].forEach(([role, actor, message]) => {
    const bubble = node("div", `message ${role}`);
    bubble.append(node("div", "message-meta", actor), node("div", "", message));
    conversation.append(bubble);
  });

  byId("timeline").replaceChildren();
  byId("candidate-actions").className = "empty-state";
  byId("candidate-actions").textContent = "运行分析后显示候选动作。";
  byId("planning-issues").replaceChildren();
  byId("audit-checks").innerHTML = '<div class="empty-state">候选动作生成后才能审核。</div>';
  byId("fact-evidence").innerHTML = '<div class="empty-state">等待智能体读取订单快照。</div>';
  byId("policy-evidence").innerHTML = '<div class="empty-state">等待政策智能体检索条款。</div>';
  byId("decision-result").textContent = "等待审核通过。";
  byId("state-diff").innerHTML = '<div class="empty-state">批准后可验证一份明确标记为模拟的状态快照。</div>';
  document.querySelectorAll("[data-decision]").forEach((button) => { button.disabled = true; });
  byId("verify-state").disabled = true;
  byId("modification-reason").disabled = state.scenario !== "cancel";
  state.planning = null;
  state.audit = null;
  state.decision = null;
  state.authorization = null;
}

function addTimelineStep(icon, title, description, timestamp) {
  const item = node("li");
  const copy = node("div", "timeline-copy");
  copy.append(node("strong", "", title), node("small", "", description));
  item.append(node("span", "timeline-icon", icon), copy, node("span", "timeline-time", humanTime(timestamp)));
  byId("timeline").append(item);
}

function renderPlanning(planning) {
  const plan = planning.plan;
  const status = translations[plan.status] || plan.status;
  byId("plan-status").textContent = status;
  byId("plan-status").className = `status-text ${plan.status === "ready_for_review" ? "ready" : plan.status === "blocked" ? "blocked" : "warning"}`;
  byId("risk-label").textContent = plan.status === "ready_for_review" ? "高风险写操作 · 强制人工门控" : `${plan.issues.length} 个问题待处理`;
  byId("timeline-state").textContent = "协作完成";
  byId("timeline-state").className = "tag";
  const specialist = planning.specialist_results[0];
  addTimelineStep("受", "工单受理", `结构化 ${scenarios[state.scenario].intent} 请求`, null);
  addTimelineStep("订", "订单智能体", `只读查询订单；记录 ${specialist.order_handoff.payload.tool_calls.length} 次工具调用`, specialist.order_handoff.created_at);
  addTimelineStep("策", "政策智能体", `资格结论：${specialist.policy_handoff.payload.decision.status}；引用 ${specialist.policy_handoff.payload.retrieved_policy.length} 条政策`, specialist.policy_handoff.created_at);
  addTimelineStep("规", "方案规划器", `生成 ${plan.candidate_actions.length} 个候选动作；can_execute=${plan.can_execute}`, null);

  const actionContainer = byId("candidate-actions");
  actionContainer.replaceChildren();
  actionContainer.className = "";
  if (!plan.candidate_actions.length) {
    actionContainer.className = "empty-state";
    actionContainer.textContent = "当前事实或政策结论不允许生成候选动作。";
  }
  plan.candidate_actions.forEach((action) => {
    const card = node("div", "candidate");
    const top = node("div", "candidate-top");
    const title = node("strong", "", `${action.sequence}. ${translations[action.action_type] || action.action_type}`);
    const id = node("code", "", action.plan_id);
    top.append(title, id);
    const grid = node("div", "argument-grid");
    const argumentsToShow = {
      order_id: action.order_id,
      ...action.arguments,
      item_ids: action.item_ids,
      target_item_ids: action.target_item_ids,
      requires_approval: action.requires_approval,
      can_execute: action.can_execute,
    };
    Object.entries(argumentsToShow).forEach(([key, value]) => {
      const entry = node("div", "argument");
      entry.append(node("span", "", key), node("code", "", valueText(value)));
      grid.append(entry);
    });
    card.append(top, grid);
    actionContainer.append(card);
  });

  const issues = byId("planning-issues");
  issues.replaceChildren();
  plan.issues.forEach((issue) => issues.append(node("div", "issue", `${issue.conflict_type}: ${issue.description}`)));

  const facts = new Map();
  const policies = new Map();
  planning.specialist_results.forEach((result) => {
    result.policy_handoff.payload.facts.forEach((item) => facts.set(item.fact_id, item));
    result.policy_handoff.payload.retrieved_policy.forEach((hit) => policies.set(hit.clause.clause_id, hit));
  });
  const factContainer = byId("fact-evidence");
  factContainer.replaceChildren();
  facts.forEach((item) => {
    const card = node("div", "evidence");
    card.append(
      node("strong", "", item.field),
      node("span", "", valueText(item.value)),
      node("small", "", `${item.source_type} · ${item.source_id}`),
    );
    factContainer.append(card);
  });
  const policyContainer = byId("policy-evidence");
  policyContainer.replaceChildren();
  policies.forEach((hit) => {
    const card = node("div", "evidence");
    card.append(
      node("strong", "", hit.clause.clause_id),
      node("span", "", hit.clause.title),
      node("small", "", hit.clause.text),
    );
    policyContainer.append(card);
  });
}

function renderAudit(audit) {
  byId("audit-state").textContent = translations[audit.status] || audit.status;
  byId("audit-state").className = `tag ${audit.can_request_human_decision ? "" : "warning"}`;
  addTimelineStep("审", "独立审核员", `${audit.checks.filter((check) => check.status === "passed").length}/${audit.checks.length} 项通过；can_execute=${audit.can_execute}`, audit.reviewed_at);
  const container = byId("audit-checks");
  container.replaceChildren();
  audit.checks.forEach((check) => {
    const card = node("div", "check");
    const head = node("div", "check-head");
    head.append(node("strong", "", check.check_type), node("span", check.status, translations[check.status] || check.status));
    card.append(head, node("small", "", check.description));
    container.append(card);
  });
  document.querySelectorAll("[data-decision]").forEach((button) => {
    const isModify = button.dataset.decision === "modify";
    button.disabled = !audit.can_request_human_decision || (isModify && state.scenario !== "cancel");
  });
  byId("decision-result").textContent = audit.can_request_human_decision
    ? "全部审核检查通过，等待人工决定。"
    : "独立审核未通过，人工审批已锁定。";
}

async function runWorkflow() {
  renderScenario();
  document.body.classList.add("busy");
  byId("run-workflow").textContent = "分析中…";
  try {
    const planning = await postJson("/api/v1/planning/review", scenarios[state.scenario].request());
    state.planning = planning;
    renderPlanning(planning);
    const audit = await postJson("/api/v1/review/audit", {planning});
    state.audit = audit;
    renderAudit(audit);
    showToast("多智能体分析与独立审核完成");
  } catch (error) {
    showToast(`运行失败：${error.message}`, true);
    byId("timeline-state").textContent = "运行失败";
    byId("timeline-state").className = "tag warning";
  } finally {
    document.body.classList.remove("busy");
    byId("run-workflow").textContent = "重新运行分析";
  }
}

function renderDecision(result) {
  const box = byId("decision-result");
  box.replaceChildren();
  box.append(
    node("strong", "", translations[result.status] || result.status),
    node("div", "", `execution_authorized=${result.execution_authorized}`),
    node("div", "", `can_execute_now=${result.can_execute_now}`),
    node("div", "", `write_executed=${result.write_executed}`),
  );
  document.querySelectorAll("[data-decision]").forEach((button) => { button.disabled = true; });
  if (result.authorization) {
    state.authorization = result.authorization;
    byId("verify-state").disabled = false;
    renderExpectedDiff(result.authorization);
    addTimelineStep("批", "人工批准", "已签发单次授权；未执行任何写工具", result.decided_at);
  } else if (result.requires_re_review) {
    addTimelineStep("改", "人工修改", "旧审核失效，修改后的动作必须重新审核", result.decided_at);
  } else {
    addTimelineStep("拒", "人工拒绝", "未生成授权，流程结束", result.decided_at);
  }
}

async function decide(decision) {
  if (!state.planning || !state.audit) return;
  const operator = byId("operator-name").value.trim();
  const reason = byId("decision-reason").value.trim();
  if (!operator || !reason) {
    showToast("请填写操作员和决定理由", true);
    return;
  }
  const payload = {planning: state.planning, review: state.audit, decision, decided_by: operator, reason, modifications: []};
  if (decision === "modify") {
    const action = state.audit.reviewed_actions[0];
    payload.modifications = [{
      plan_id: action.plan_id,
      arguments: {...action.arguments, reason: byId("modification-reason").value},
    }];
  }
  try {
    const result = await postJson("/api/v1/review/decision", payload);
    state.decision = result;
    renderDecision(result);
    showToast(`${translations[result.status] || result.status}；写工具调用仍为 0`);
  } catch (error) {
    showToast(`决策失败：${error.message}`, true);
  }
}

function simulatedSnapshots(authorization) {
  const before = {};
  const after = {};
  authorization.expected_state_changes.forEach((expected) => {
    before[expected.order_id] = {order_id: expected.order_id, status: scenarios[state.scenario].orderStatus};
    after[expected.order_id] = {order_id: expected.order_id, status: expected.expected_status, ...expected.expected_fields};
  });
  return {before, after};
}

function renderExpectedDiff(authorization, verification = null) {
  const {before, after} = simulatedSnapshots(authorization);
  const container = byId("state-diff");
  container.replaceChildren();
  authorization.expected_state_changes.forEach((expected) => {
    const fields = {status: expected.expected_status, ...expected.expected_fields};
    Object.entries(fields).forEach(([field, value]) => {
      const row = node("div", "diff-row");
      const left = node("div", "diff-side");
      left.append(node("span", "", `模拟执行前 · ${field}`), node("strong", "", valueText(before[expected.order_id][field])));
      const right = node("div", "diff-side");
      right.append(node("span", "", `模拟执行后 · ${field}`), node("strong", "", valueText(after[expected.order_id][field])));
      row.append(left, node("span", "diff-arrow", "→"), right);
      container.append(row);
    });
  });
  if (verification) {
    container.prepend(node("div", `tag ${verification.status === "matched" ? "" : "warning"}`, `校验：${translations[verification.status] || verification.status}`));
  }
}

async function verifyState() {
  if (!state.authorization) return;
  const snapshots = simulatedSnapshots(state.authorization);
  try {
    const result = await postJson("/api/v1/review/verify-state", {
      authorization: state.authorization,
      before_snapshots: snapshots.before,
      after_snapshots: snapshots.after,
    });
    renderExpectedDiff(state.authorization, result);
    addTimelineStep("验", "状态校验器", `模拟快照校验：${translations[result.status] || result.status}`, result.verified_at);
    byId("verify-state").disabled = true;
    showToast("模拟状态校验完成；没有真实订单被修改");
  } catch (error) {
    showToast(`校验失败：${error.message}`, true);
  }
}

document.querySelectorAll("[data-scenario]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-scenario]").forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    state.scenario = button.dataset.scenario;
    renderScenario();
  });
});
document.querySelectorAll("[data-decision]").forEach((button) => {
  button.addEventListener("click", () => decide(button.dataset.decision));
});
byId("run-workflow").addEventListener("click", runWorkflow);
byId("verify-state").addEventListener("click", verifyState);
renderScenario();
