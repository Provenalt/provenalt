"""Validate agent-card content against the vendored ERC-8004 registration-v1 schema (§4.2).

The schema is a vendored, versioned copy authored from the normative structure in
ERC8004SPEC.md (see ``cards/schemas/registration-v1.schema.json``). Validation records a
boolean and a list of human-readable errors; malformed JSON is reported as invalid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

# Provenalt's version of the vendored schema. Bump when the vendored copy changes.
SCHEMA_VERSION = 1
_SCHEMA_RESOURCE = "registration-v1.schema.json"


@lru_cache(maxsize=1)
def load_registration_schema() -> dict[str, Any]:
    raw = resources.files("provenalt_indexer.cards.schemas").joinpath(_SCHEMA_RESOURCE).read_text()
    schema: dict[str, Any] = json.loads(raw)
    return schema


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(load_registration_schema())


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]


def validate_card(content: str | dict[str, Any]) -> ValidationResult:
    """Validate parsed card content (or a JSON string) against the registration schema."""
    if isinstance(content, str):
        try:
            document = json.loads(content)
        except json.JSONDecodeError as exc:
            return ValidationResult(valid=False, errors=[f"invalid JSON: {exc}"])
    else:
        document = content

    errors = sorted(_validator().iter_errors(document), key=lambda e: list(e.absolute_path))
    messages = [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]
    return ValidationResult(valid=not messages, errors=messages)
