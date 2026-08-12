"""Treat all external text as data and authenticate agent-to-agent envelopes."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from copy import deepcopy
from typing import Any

from after_sales_agents.domain.models import AgentRole
from after_sales_agents.reliability.models import (
    SecurityAssessment,
    SecurityFinding,
    SignedHandoff,
)

_PATTERNS = {
    "instruction_override": re.compile(
        r"ignore\s+(all\s+)?(previous|prior|system)|忽略.{0,8}(之前|系统|开发者)",
        re.IGNORECASE,
    ),
    "identity_spoof": re.compile(
        r"(?:i\s+am|act\s+as|pretend\s+to\s+be).{0,24}(system|developer|auditor|admin)"
        r"|(?:我是|扮演|假装).{0,16}(系统|开发者|审核员|管理员)",
        re.IGNORECASE,
    ),
    "approval_bypass": re.compile(
        r"(?:without|skip|bypass).{0,20}(approval|confirmation|review)"
        r"|(?:无需|跳过|绕过).{0,16}(批准|确认|审核)",
        re.IGNORECASE,
    ),
    "tool_coercion": re.compile(
        r"(?:call|execute|run).{0,24}(cancel|return|exchange|write).{0,20}(tool|function)"
        r"|(?:调用|执行).{0,16}(取消|退货|换货|写).{0,12}(工具|函数)",
        re.IGNORECASE,
    ),
}


class UntrustedTextGuard:
    def assess(self, text: str) -> SecurityAssessment:
        normalized = text.strip()
        if not normalized:
            raise ValueError("untrusted text cannot be empty")
        findings = [
            SecurityFinding(
                code=code,
                description=f"Untrusted data matched the {code} pattern.",
            )
            for code, pattern in _PATTERNS.items()
            if pattern.search(normalized)
        ]
        return SecurityAssessment(
            findings=findings,
            safe_text=f"<untrusted_data>\n{normalized}\n</untrusted_data>",
        )


class HandoffAuthenticator:
    """HMAC-authenticate sender identity; payload text never decides who sent it."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 16:
            raise ValueError("handoff secret must contain at least 16 bytes")
        self._secret = secret

    def sign(
        self,
        *,
        sender: AgentRole,
        recipient: AgentRole,
        case_id: str,
        payload: dict[str, Any],
    ) -> SignedHandoff:
        signature = self._signature(sender, recipient, case_id, payload)
        return SignedHandoff(
            sender=sender,
            recipient=recipient,
            case_id=case_id,
            payload=deepcopy(payload),
            signature=signature,
        )

    def verify(
        self,
        handoff: SignedHandoff,
        *,
        expected_sender: AgentRole,
        expected_recipient: AgentRole,
        expected_case_id: str,
    ) -> bool:
        if (
            handoff.sender is not expected_sender
            or handoff.recipient is not expected_recipient
            or handoff.case_id != expected_case_id
        ):
            return False
        expected = self._signature(
            handoff.sender,
            handoff.recipient,
            handoff.case_id,
            handoff.payload,
        )
        return hmac.compare_digest(handoff.signature, expected)

    def _signature(
        self,
        sender: AgentRole,
        recipient: AgentRole,
        case_id: str,
        payload: dict[str, Any],
    ) -> str:
        canonical = json.dumps(
            {
                "sender": sender.value,
                "recipient": recipient.value,
                "case_id": case_id,
                "payload": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(self._secret, canonical, hashlib.sha256).hexdigest()
