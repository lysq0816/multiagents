"""HTTP entry point for the after-sales workflow and operator workbench."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from after_sales_agents.agents import (
    CollaborationReviewRequest,
    SpecialistCollaborationResult,
    SpecialistWorkflow,
)
from after_sales_agents.domain.models import RoutingDecision, TicketIntake
from after_sales_agents.domain.routing import DifficultyRouter
from after_sales_agents.planning import (
    PlanningWorkflow,
    PlanningWorkflowRequest,
    PlanningWorkflowResult,
)
from after_sales_agents.policy import EligibilityEngine, PolicyRetriever
from after_sales_agents.policy.models import (
    EligibilityDecision,
    EligibilityRequest,
    PolicySearchHit,
    PolicySearchRequest,
)
from after_sales_agents.review import (
    AuditReviewRequest,
    AuditReviewResult,
    HumanApprovalGate,
    HumanDecisionRequest,
    HumanDecisionResult,
    IndependentAuditor,
    PostExecutionVerifier,
    StateVerificationRequest,
    StateVerificationResult,
)

app = FastAPI(
    title="电商售后多智能体协作系统",
    version="0.6.0",
    description="Difficulty-routed, policy-grounded specialist collaboration for retail support.",
)
router = DifficultyRouter()
policy_retriever = PolicyRetriever()
eligibility_engine = EligibilityEngine(policy_retriever)
specialist_workflow = SpecialistWorkflow()
planning_workflow = PlanningWorkflow()
independent_auditor = IndependentAuditor()
human_approval_gate = HumanApprovalGate()
post_execution_verifier = PostExecutionVerifier()
ui_directory = Path(__file__).resolve().parent / "ui"
app.mount(
    "/ui/assets",
    StaticFiles(directory=ui_directory / "assets"),
    name="ui-assets",
)


@app.get("/", include_in_schema=False)
def open_operator_workbench() -> RedirectResponse:
    return RedirectResponse(url="/ui", status_code=307)


@app.get("/ui", include_in_schema=False)
@app.get("/ui/", include_in_schema=False)
def operator_workbench() -> Response:
    return FileResponse(ui_directory / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/routing/preview", response_model=RoutingDecision)
def preview_routing(ticket: TicketIntake) -> RoutingDecision:
    return router.route(ticket)


@app.post("/api/v1/policy/search", response_model=list[PolicySearchHit])
def search_policy(request: PolicySearchRequest) -> list[PolicySearchHit]:
    return policy_retriever.search(request)


@app.post("/api/v1/policy/eligibility", response_model=EligibilityDecision)
def evaluate_eligibility(request: EligibilityRequest) -> EligibilityDecision:
    return eligibility_engine.evaluate(request)


@app.post(
    "/api/v1/collaboration/review",
    response_model=SpecialistCollaborationResult,
)
def review_with_specialists(
    request: CollaborationReviewRequest,
) -> SpecialistCollaborationResult:
    return specialist_workflow.review(request)


@app.post(
    "/api/v1/planning/review",
    response_model=PlanningWorkflowResult,
)
def review_candidate_plan(
    request: PlanningWorkflowRequest,
) -> PlanningWorkflowResult:
    return planning_workflow.review(request)


@app.post(
    "/api/v1/review/audit",
    response_model=AuditReviewResult,
)
def audit_candidate_plan(request: AuditReviewRequest) -> AuditReviewResult:
    return independent_auditor.review(request)


@app.post(
    "/api/v1/review/decision",
    response_model=HumanDecisionResult,
)
def decide_candidate_plan(request: HumanDecisionRequest) -> HumanDecisionResult:
    return human_approval_gate.decide(request)


@app.post(
    "/api/v1/review/verify-state",
    response_model=StateVerificationResult,
)
def verify_post_execution_state(
    request: StateVerificationRequest,
) -> StateVerificationResult:
    return post_execution_verifier.verify(request)
