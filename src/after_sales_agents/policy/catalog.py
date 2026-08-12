"""Load, validate, and retrieve project-owned citations to the official Retail policy."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

from after_sales_agents.policy.models import (
    PolicyCatalog,
    PolicyClause,
    PolicySearchHit,
    PolicySearchRequest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "policies" / "retail_policy_clauses.json"


def load_policy_catalog(path: Path | None = None) -> PolicyCatalog:
    if path is not None:
        payload = path.read_text(encoding="utf-8")
    elif DEFAULT_CATALOG_PATH.is_file():
        payload = DEFAULT_CATALOG_PATH.read_text(encoding="utf-8")
    else:
        payload = (
            files("after_sales_agents.policy")
            .joinpath("retail_policy_clauses.json")
            .read_text(encoding="utf-8")
        )
    return PolicyCatalog.model_validate_json(payload)


def validate_catalog_against_source(catalog: PolicyCatalog, policy_path: Path) -> list[str]:
    """Ensure every project clause remains a verbatim excerpt of the official file."""

    policy_text = policy_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    missing = [clause.clause_id for clause in catalog.clauses if clause.text not in policy_text]
    if missing:
        raise ValueError(f"policy excerpts not found in official source: {missing}")
    return [clause.clause_id for clause in catalog.clauses]


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _english_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


class PolicyRetriever:
    def __init__(self, catalog: PolicyCatalog | None = None) -> None:
        self.catalog = catalog or load_policy_catalog()

    def get_clause(self, clause_id: str) -> PolicyClause:
        for clause in self.catalog.clauses:
            if clause.clause_id == clause_id:
                return clause
        raise KeyError(f"unknown policy clause: {clause_id}")

    def search(self, request: PolicySearchRequest) -> list[PolicySearchHit]:
        query = _normalized(request.query)
        query_tokens = _english_tokens(query)
        hits: list[PolicySearchHit] = []

        for clause in self.catalog.clauses:
            reasons: list[str] = []
            score = 0.0

            if request.intents:
                matches = set(request.intents) & set(clause.applies_to_intents)
                if not matches:
                    continue
                score += 12.0 * len(matches)
                reasons.append("intent")

            if request.actions:
                matches = set(request.actions) & set(clause.applies_to_actions)
                if not matches:
                    continue
                score += 12.0 * len(matches)
                reasons.append("action")

            if query:
                tag_matches = [tag for tag in clause.tags if _normalized(tag) in query]
                if tag_matches:
                    score += 8.0 * len(tag_matches)
                    reasons.append("tag")

                searchable = " ".join([clause.title, clause.text, *clause.tags])
                overlap = query_tokens & _english_tokens(searchable)
                if overlap:
                    score += 2.0 * len(overlap)
                    reasons.append("text")

                if not tag_matches and not overlap and not request.intents and not request.actions:
                    continue

            if score > 0:
                hits.append(
                    PolicySearchHit(
                        score=score,
                        match_reasons=list(dict.fromkeys(reasons)),
                        clause=clause,
                    )
                )

        return sorted(hits, key=lambda hit: (-hit.score, hit.clause.clause_id))[: request.top_k]
