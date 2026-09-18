from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

PROMPT_CONTRACT_VERSION_V1 = "1.0"
DEFAULT_PROMPT_CONTRACT_VERSION = PROMPT_CONTRACT_VERSION_V1
SUPPORTED_PROMPT_CONTRACT_VERSIONS = frozenset({PROMPT_CONTRACT_VERSION_V1})

CANONICAL_SECTIONS: tuple[str, ...] = (
    "ROLE",
    "STATE",
    "ENVIRONMENT",
    "OBJECTIVE",
    "AUTHORIZED SCOPE",
    "EXECUTION",
    "FAILURE GUARDS",
    "ATTEMPT / TIME LIMITS",
    "RESOURCE RULES",
    "ACCEPTANCE",
    "RECEIPTS",
    "FINAL REPORT",
)
CANONICAL_SECTION_SET: frozenset[str] = frozenset(CANONICAL_SECTIONS)

_HEADER_PATTERN = re.compile(
    r"(?:^|\r?\n)(" + "|".join(re.escape(sec) for sec in CANONICAL_SECTIONS) + r")(?:\r?\n|$)"
)


def validate_contract_version(version: str) -> str:
    """Validate that the given prompt contract version is supported."""
    if not isinstance(version, str) or not version.strip():
        raise ValueError("prompt_contract_version must be a nonempty string")
    if version not in SUPPORTED_PROMPT_CONTRACT_VERSIONS:
        raise ValueError(
            f"unsupported prompt_contract_version: {version!r}. "
            f"Supported versions: {sorted(SUPPORTED_PROMPT_CONTRACT_VERSIONS)}"
        )
    return version


def render_prompt_contract(
    sections: Mapping[str, str],
    retry_notice: str = "",
) -> str:
    """Deterministically render a prompt conforming to Prompt Contract v1.0.

    Ensures all 12 canonical sections are present and renders them in canonical order.
    """
    missing = [sec for sec in CANONICAL_SECTIONS if sec not in sections]
    if missing:
        raise ValueError(f"Cannot render prompt contract, missing section(s): {', '.join(missing)}")

    blocks: list[str] = []
    for sec in CANONICAL_SECTIONS:
        content = sections[sec].strip()
        blocks.append(f"{sec}\n{content}")

    body = "\n\n".join(blocks)
    if retry_notice and retry_notice.strip():
        return f"{retry_notice.strip()}\n\n{body}"
    return body


def parse_prompt_contract(prompt_text: str) -> dict[str, str]:
    """Parse and validate a rendered prompt against Prompt Contract v1.0.

    Returns a dictionary mapping canonical section names to their contents.
    If a preamble (such as a retry notice) precedes ROLE, it is stored under '__preamble__'.

    Raises ValueError if:
    - Any canonical section is missing
    - Any canonical section appears more than once
    - Sections appear out of canonical order
    """
    matches = list(_HEADER_PATTERN.finditer(prompt_text))
    found_names = [m.group(1) for m in matches]

    duplicates = [sec for sec in CANONICAL_SECTIONS if found_names.count(sec) > 1]
    if duplicates:
        raise ValueError(f"Duplicate prompt contract section(s): {', '.join(duplicates)}")

    missing = [sec for sec in CANONICAL_SECTIONS if sec not in found_names]
    if missing:
        raise ValueError(f"Missing prompt contract section(s): {', '.join(missing)}")

    if tuple(found_names) != CANONICAL_SECTIONS:
        raise ValueError(
            f"Prompt contract sections not in canonical order. Expected: {list(CANONICAL_SECTIONS)}, found: {found_names}"
        )

    parsed: dict[str, str] = {}
    first_match = matches[0]
    preamble = prompt_text[:first_match.start()].strip()
    if preamble:
        parsed["__preamble__"] = preamble

    for idx, match in enumerate(matches):
        sec_name = match.group(1)
        content_start = match.end()
        content_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(prompt_text)
        parsed[sec_name] = prompt_text[content_start:content_end].strip()

    return parsed


def validate_contract_prompt(prompt_text: str) -> dict[str, str]:
    """Validate that prompt_text conforms to Prompt Contract v1.0 and return parsed sections."""
    return parse_prompt_contract(prompt_text)


@dataclass(frozen=True)
class PromptContract:
    version: str = PROMPT_CONTRACT_VERSION_V1
    canonical_sections: tuple[str, ...] = CANONICAL_SECTIONS

    @classmethod
    def render(cls, sections: Mapping[str, str], retry_notice: str = "") -> str:
        return render_prompt_contract(sections, retry_notice=retry_notice)

    @classmethod
    def validate(cls, prompt_text: str) -> dict[str, str]:
        return validate_contract_prompt(prompt_text)