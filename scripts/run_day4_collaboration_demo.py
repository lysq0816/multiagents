"""Run the deterministic Day 4 specialist handoff without model calls."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.agents.models import (
    CollaborationReviewRequest,
    OrderSpecialistRequest,
)
from after_sales_agents.agents.permissions import ToolPermissionGuard
from after_sales_agents.agents.workflow import SpecialistWorkflow
from after_sales_agents.domain.models import ActionType, AgentRole
from after_sales_agents.policy.models import (
    FactField,
    FactSourceType,
    SourceFact,
)


def _fact(
    fact_id: str,
    field: FactField,
    value: object,
    source_type: FactSourceType,
    source_id: str,
) -> SourceFact:
    return SourceFact(
        fact_id=fact_id,
        field=field,
        value=value,
        subject_id="#W9348897",
        source_type=source_type,
        source_id=source_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day4" / "collaboration_demo.json",
    )
    args = parser.parse_args()

    request = CollaborationReviewRequest(
        analysis=OrderSpecialistRequest(
            case_id="demo-cancel-1",
            action_type=ActionType.CANCEL_ORDER,
            order_id="#W9348897",
            provided_facts=[
                _fact(
                    "fact:authenticated",
                    FactField.USER_AUTHENTICATED,
                    True,
                    FactSourceType.TOOL,
                    "find_user_id_by_email:call-1",
                ),
                _fact(
                    "fact:details",
                    FactField.ACTION_DETAILS_PRESENTED,
                    True,
                    FactSourceType.AGENT,
                    "assistant-message:12",
                ),
                _fact(
                    "fact:confirmed",
                    FactField.USER_CONFIRMED,
                    True,
                    FactSourceType.USER,
                    "user-message:13",
                ),
                _fact(
                    "fact:order-id",
                    FactField.ORDER_ID_CONFIRMED,
                    True,
                    FactSourceType.USER,
                    "user-message:13",
                ),
                _fact(
                    "fact:reason",
                    FactField.CANCEL_REASON,
                    "no longer needed",
                    FactSourceType.USER,
                    "user-message:13",
                ),
            ],
        ),
        order_snapshot={"order_id": "#W9348897", "status": "pending"},
    )
    guard = ToolPermissionGuard()
    result = SpecialistWorkflow(guard).review(request)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_calls": 0,
        "write_tool_calls": 0,
        "tool_permissions": {
            role.value: sorted(tool.value for tool in guard.allowed_tools(role))
            for role in (AgentRole.ORDER_SPECIALIST, AgentRole.POLICY_SPECIALIST)
        },
        "result": result.model_dump(mode="json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
