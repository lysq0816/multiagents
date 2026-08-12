"""Validate Day 3 policy citations and emit an auditable example decision."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from after_sales_agents.benchmark.tau2_adapter import locate_tau2_root
from after_sales_agents.domain.models import ActionType, Intent
from after_sales_agents.policy.catalog import (
    PolicyRetriever,
    load_policy_catalog,
    validate_catalog_against_source,
)
from after_sales_agents.policy.eligibility import EligibilityEngine
from after_sales_agents.policy.models import (
    EligibilityRequest,
    FactField,
    FactSourceType,
    PolicySearchRequest,
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
    parser.add_argument("--tau2-root", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "day3" / "policy_grounding_validation.json",
    )
    args = parser.parse_args()

    catalog = load_policy_catalog()
    tau2_root = locate_tau2_root(args.tau2_root)
    official_policy = tau2_root / catalog.source_path
    validated_clause_ids = validate_catalog_against_source(catalog, official_policy)

    retriever = PolicyRetriever(catalog)
    search_hits = retriever.search(
        PolicySearchRequest(
            query="取消订单需要哪些条件",
            intents=[Intent.CANCEL_ORDER],
            actions=[ActionType.CANCEL_ORDER],
            top_k=10,
        )
    )
    facts = [
        _fact(
            "fact:authenticated",
            FactField.USER_AUTHENTICATED,
            True,
            FactSourceType.TOOL,
            "find_user_id_by_email:call-1",
        ),
        _fact(
            "fact:status",
            FactField.ORDER_STATUS,
            "pending",
            FactSourceType.TOOL,
            "get_order_details:call-2",
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
    ]
    decision = EligibilityEngine(retriever).evaluate(
        EligibilityRequest(action_type=ActionType.CANCEL_ORDER, facts=facts)
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_id": catalog.catalog_id,
        "official_policy": str(official_policy),
        "clause_count": len(catalog.clauses),
        "validated_clause_ids": validated_clause_ids,
        "search_hit_ids": [hit.clause.clause_id for hit in search_hits],
        "sample_decision": decision.model_dump(mode="json"),
        "model_calls": 0,
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
