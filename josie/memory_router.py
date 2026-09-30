"""Josie Memory Relevance Router.

Routes ordinary user tasks to relevant approved canonical knowledge categories for priming.
Precedence:
1. Explicit structured categories (priming_categories / categories)
2. Task class / route metadata (task_class / operation)
3. Changed path prefixes (ARCH_PATH_PREFIXES, AUTHORITY_PATH_PREFIXES)
4. Automatic Memory Relevance Router (deterministic rules + qualified local model fallback)
5. Empty categories (fail-closed)
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Any, Sequence

from josie.candidate_claims import ALLOWED_CLAIM_CATEGORIES

ROUTER_VERSION = "1.0.0"
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_CONFIDENCE_THRESHOLD = 0.70


@dataclass(frozen=True)
class MemoryRelevance:
    """Structured relevance evaluation for task-to-memory priming."""

    memory_needed: bool
    categories: tuple[str, ...]
    confidence: float
    reason: str
    router_version: str = ROUTER_VERSION

    def __post_init__(self) -> None:
        conf = float(self.confidence)
        if not (0.0 <= conf <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence!r}")
        clean_cats: list[str] = []
        for cat in self.categories:
            c = str(cat).strip().lower()
            if c in ALLOWED_CLAIM_CATEGORIES and c not in clean_cats:
                clean_cats.append(c)
        object.__setattr__(self, "categories", tuple(clean_cats))
        # Enforce fail-closed threshold invariant: confidence < 0.70 cannot prime memory
        if conf < DEFAULT_CONFIDENCE_THRESHOLD or not self.categories or not self.memory_needed:
            object.__setattr__(self, "memory_needed", False)
            object.__setattr__(self, "categories", ())

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_needed": self.memory_needed,
            "categories": list(self.categories),
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "router_version": self.router_version,
        }


# Generic imperative coding commands that require NO personal or project memory
_GENERIC_CODE_TASK_PATTERN = re.compile(
    r"^\s*(?:write|create|implement|code|generate|build|refactor|fix|debug|test|run|update|delete|remove|sort|reverse|calculate|find)\s+"
    r"(?:a|an|the)?\s*"
    r"(?:python|javascript|typescript|bash|sh|c|cpp|rust|go|java|sql)?\s*"
    r"(?:function|script|program|class|method|module|algorithm|unit\s+test|code|regex|loop|string|array|list|number|factorial|fibonacci|parser)\b",
    re.IGNORECASE,
)

# Prohibition prefixes in coding tasks that specify negative boundaries (e.g. "Do not touch supervisor...")
_NEGATIVE_PROSE_PREFIX_PATTERN = re.compile(
    r"^\s*(?:do\s+not\s+touch|never\s+touch|avoid\s+touching|leave\s+untouched)\b",
    re.IGNORECASE,
)

# Conversational ambiguity expressions that lack category context
_AMBIGUOUS_CONVERSATION_PATTERN = re.compile(
    r"^\s*(?:tell\s+me\s+about\s+that\s+thing|what\s+we\s+(?:talked|discussed)\s+about|that\s+thing\s+we\s+discussed|remember\s+what\s+we\s+talked\s+about)\b",
    re.IGNORECASE,
)


def _route_deterministic(task: str) -> MemoryRelevance | None:
    """Evaluate deterministic lexical and semantic rules for obvious category matches."""
    clean = task.strip()
    if not clean:
        return MemoryRelevance(
            memory_needed=False,
            categories=(),
            confidence=1.0,
            reason="empty task text",
            router_version=ROUTER_VERSION,
        )

    text_lower = clean.lower()
    text_no_quotes = re.sub(r"['\"][^'\"]*['\"]", "", text_lower)

    # 1. Check for negative prose constraint or generic programming task
    if _NEGATIVE_PROSE_PREFIX_PATTERN.search(clean) and any(
        kw in text_lower for kw in ("summarize", "result.txt", "allowed changes", "edit", "file")
    ):
        return MemoryRelevance(
            memory_needed=False,
            categories=(),
            confidence=0.95,
            reason="negative constraint in coding directive; no memory inquiry",
            router_version=ROUTER_VERSION,
        )

    if _GENERIC_CODE_TASK_PATTERN.search(clean) and not any(
        kw in text_no_quotes
        for kw in (
            "certif", "credential", "qualification", "hardware do i", "my background",
            "server experience", "did we decide", "who is josie", "what do i prefer",
        )
    ):
        return MemoryRelevance(
            memory_needed=False,
            categories=(),
            confidence=0.98,
            reason="generic programming task does not require personal or project memory",
            router_version=ROUTER_VERSION,
        )

    # 2. Check for conversational ambiguity lacking category context
    if _AMBIGUOUS_CONVERSATION_PATTERN.search(clean) and not any(
        kw in text_no_quotes
        for kw in (
            "certif", "hardware", "gpu", "server", "prefer", "budget", "decide",
            "decision", "architecture", "procedure", "destructive", "identity",
        )
    ):
        return MemoryRelevance(
            memory_needed=False,
            categories=(),
            confidence=0.40,
            reason="conversational ambiguity without memory category context fails closed",
            router_version=ROUTER_VERSION,
        )

    matched_cats: list[str] = []
    reasons: list[str] = []

    # Category: profile
    # Matches technical credentials, certifications, qualifications, background, server experience
    has_cert = bool(re.search(r"\b(?:certif(?:ication|ications|ied)?|credential(?:s)?|qualification(?:s)?)\b", text_no_quotes))
    has_server_exp = bool(re.search(r"\b(?:server|commercial\s+server|technical)\s+(?:experience|background)\b", text_no_quotes))
    has_personal_bg = bool(re.search(r"\b(?:my|do\s+i\s+have\s+(?:any)?)\s+(?:background|experience|credentials|qualifications|certifications)\b", text_no_quotes))
    has_suitability = bool(re.search(r"\b(?:suited|better\s+suited)\s+(?:to|for)\s+(?:work|working|run|operate|manage)\b", text_no_quotes))
    is_cert_inquiry = has_cert and any(kw in text_no_quotes for kw in ("do i", "i have", "my", "who is", "dustin", "what", "which", "server", "experience", "technical", "relevant", "josie"))

    if is_cert_inquiry or has_server_exp or has_personal_bg or has_suitability:
        matched_cats.append("profile")
        reasons.append("task inquires about user certifications, credentials, background, or server experience")

    # Category: hardware
    # Matches physical hardware, components, GPUs, storage, parts on hand, inventory
    has_hw_inquiry = bool(re.search(r"\b(?:what\s+hardware|hardware\s+do\s+i|hardware\s+setup|hardware\s+inventory)\b", text_no_quotes))
    has_hw_ownership = bool(re.search(r"\b(?:hardware\s+do\s+i\s+already\s+own|hardware\s+(?:i|we)\s+(?:own|have)\s+for\s+josie)\b", text_no_quotes))
    has_hw_terms = bool(re.search(r"\b(?:gpu|gpus|rtx|3090|4090|cpu|cpus|nvme|hdds?|ssds?|vram|parts\s+on\s+hand|server\s+parts)\b", text_no_quotes))
    if has_hw_inquiry or has_hw_ownership or (has_hw_terms and any(q in text_no_quotes for q in ("what", "which", "own", "have", "setup", "parts"))):
        matched_cats.append("hardware")
        reasons.append("task inquires about hardware equipment, components, or inventory")

    # Category: preference
    # Matches user goals, preferences, hardware strategies, budgets
    has_preference = bool(re.search(r"\b(?:what\s+do\s+i\s+prefer|what\s+kind\s+of\s+.*prefer|preference(?:s)?|preferred\s+strategy|my\s+preference(?:s)?)\b", text_no_quotes))
    has_goal_budget = bool(re.search(r"\b(?:cheapest\s+hardware|hardware\s+strategy|budget\s+strategy|cost\s+target)\b", text_no_quotes))
    if has_preference or has_goal_budget:
        matched_cats.append("preference")
        reasons.append("task inquires about user preferences, goals, or strategy")

    # Category: decision
    # Matches explicit architectural or project decisions previously agreed upon
    has_decision = bool(re.search(r"\b(?:what\s+did\s+we\s+decide|what\s+was\s+decided|our\s+decision(?:s)?|agreed\s+upon|decision\s+about)\b", text_no_quotes))
    if has_decision:
        matched_cats.append("decision")
        reasons.append("task inquires about past decisions or agreements")

    # Category: architecture
    # Matches worker architecture, supervisor system design, architectural invariants, tool boundaries
    has_arch = bool(re.search(r"\b(?:worker\s+architecture|supervisor\s+architecture|system\s+design|architectural\s+rules?|goose\s+and\s+opencode|opencode\s+and\s+goose|josie'?s\s+architecture|system\s+architecture)\b", text_no_quotes))
    if has_arch:
        matched_cats.append("architecture")
        reasons.append("task inquires about system or worker architecture")

    # Category: procedure
    # Matches workflows, runbooks, how to handle actions
    has_procedure = bool(re.search(r"\b(?:how\s+(?:do\s+we|should\s+(?:we|it)|to)\s+(?:handle|run|execute|perform|operate)|procedure(?:s)?|runbook(?:s)?|workflow(?:s)?)\b", text_no_quotes))
    if has_procedure:
        matched_cats.append("procedure")
        reasons.append("task inquires about operational procedure or handling")

    # Category: constraint
    # Matches safety boundaries, destructive action gates, guardrails
    has_constraint = bool(re.search(r"\b(?:destructive\s+actions?|consequential\s+actions?|guardrails?|prohibited\s+actions?|safety\s+boundary)\b", text_no_quotes))
    if has_constraint:
        matched_cats.append("constraint")
        reasons.append("task inquires about constraints or destructive action boundaries")

    # Category: identity
    # Matches system or user identity, callsigns, origins
    has_identity = bool(re.search(r"\b(?:who\s+is\s+josie|who\s+are\s+you|what\s+is\s+josie|who\s+is\s+dustin|dustin'?s\s+authority|callsign)\b", text_no_quotes))
    if has_identity:
        matched_cats.append("identity")
        reasons.append("task inquires about system or human authority identity")

    # Deduplicate while preserving canonical order
    if matched_cats:
        ordered_cats = tuple(c for c in (
            "profile", "preference", "hardware", "decision", "architecture",
            "procedure", "constraint", "identity", "project_state", "lesson",
            "relationship_context", "recurring_task", "general",
        ) if c in matched_cats)
        return MemoryRelevance(
            memory_needed=True,
            categories=ordered_cats,
            confidence=0.95,
            reason="; ".join(reasons),
            router_version=ROUTER_VERSION,
        )

    return None


def _route_local_model(
    task: str,
    *,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
    timeout: float = 15.0,
) -> MemoryRelevance:
    """Model-backed router fallback for unstructured conversational prompts."""
    system_prompt = (
        "You are Josie's Memory Relevance Router. "
        "Analyze the user request and determine whether approved canonical knowledge from memory is needed to answer or fulfill it. "
        "Allowed categories: "
        "- 'profile': user's personal credentials, certifications, qualifications, background, server experience, skills. "
        "- 'hardware': physical equipment, GPUs, servers, storage drives, inventory on hand. "
        "- 'preference': user's stated goals, preferences, hardware strategies, budgets. "
        "- 'decision': explicit architectural or system decisions previously agreed upon. "
        "- 'architecture': software design, worker/supervisor architecture, invariants. "
        "- 'procedure': operational procedures, runbooks, workflows, how to handle actions. "
        "- 'constraint': boundaries, guardrails, rules on destructive actions. "
        "- 'identity': identity of Josie or Dustin, constitutional authority, callsigns. "
        "- 'project_state': current project milestone or phase. "
        "If the task is a generic programming/math/writing task (e.g. 'write a function', 'reverse a string', 'calculate'), or if the task is ambiguous, set memory_needed=false and categories=[]. "
        "Return ONLY JSON adhering strictly to the schema."
    )

    schema = {
        "type": "object",
        "required": ["memory_needed", "categories", "confidence", "reason"],
        "properties": {
            "memory_needed": {"type": "boolean"},
            "categories": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": sorted(list(ALLOWED_CLAIM_CATEGORIES)),
                },
            },
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
    }

    payload = {
        "model": model,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0.0, "num_ctx": 2048},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task: {task[:1500]}"},
        ],
    }

    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body.get("message", {}).get("content")
        if not isinstance(content, str):
            return MemoryRelevance(
                memory_needed=False,
                categories=(),
                confidence=0.0,
                reason="model response lacked message content",
                router_version=ROUTER_VERSION,
            )
        parsed = json.loads(content)
        needed = bool(parsed.get("memory_needed", False))
        raw_cats = parsed.get("categories") or []
        valid_cats = [c for c in raw_cats if c in ALLOWED_CLAIM_CATEGORIES]
        conf = float(parsed.get("confidence", 0.8))
        reason = str(parsed.get("reason", "inferred by model router"))

        if not needed or not valid_cats or conf < DEFAULT_CONFIDENCE_THRESHOLD:
            return MemoryRelevance(
                memory_needed=False,
                categories=(),
                confidence=conf,
                reason=reason,
                router_version=ROUTER_VERSION,
            )

        return MemoryRelevance(
            memory_needed=True,
            categories=tuple(valid_cats),
            confidence=conf,
            reason=f"local model router: {reason}",
            router_version=ROUTER_VERSION,
        )
    except Exception as exc:
        return MemoryRelevance(
            memory_needed=False,
            categories=(),
            confidence=0.0,
            reason=f"local model router unavailable or failed closed: {exc}",
            router_version=ROUTER_VERSION,
        )


def route_memory_relevance(
    task: str,
    *,
    use_model_fallback: bool = True,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
    timeout: float = 15.0,
) -> MemoryRelevance:
    """Infer relevant approved canonical knowledge categories for an ordinary user task.

    Deterministic-first with qualified local model fallback. Fails closed.
    """
    clean = (task or "").strip()
    if not clean:
        return MemoryRelevance(
            memory_needed=False,
            categories=(),
            confidence=1.0,
            reason="empty task text",
            router_version=ROUTER_VERSION,
        )

    # 1. Deterministic rules
    det = _route_deterministic(clean)
    if det is not None:
        return det

    # 2. Local model fallback if requested and deterministic rules were indeterminate
    if use_model_fallback:
        return _route_local_model(
            clean,
            ollama_url=ollama_url,
            model=model,
            timeout=timeout,
        )

    # 3. Fail closed if no model fallback requested
    return MemoryRelevance(
        memory_needed=False,
        categories=(),
        confidence=0.0,
        reason="no deterministic category matched and model fallback disabled",
        router_version=ROUTER_VERSION,
    )
