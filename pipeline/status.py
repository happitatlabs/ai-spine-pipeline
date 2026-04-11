from __future__ import annotations

from enum import Enum
from typing import TypeVar


class StepStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class StepReviewStatus(str, Enum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"


class StepRunState(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"


EnumType = TypeVar("EnumType", bound=Enum)


def coerce_step_status(value: StepStatus | str) -> StepStatus:
    return _coerce_exact_enum(value, StepStatus)


def coerce_step_review_status(value: StepReviewStatus | str) -> StepReviewStatus:
    return _coerce_exact_enum(value, StepReviewStatus)


def coerce_step_run_state(value: StepRunState | str) -> StepRunState:
    return _coerce_exact_enum(value, StepRunState)


def render_status(value: StepStatus | StepReviewStatus | StepRunState | str | None) -> str:
    # Serializer only: use this for rendering valid internal state to logs/JSON,
    # never for validating external input.
    if value is None:
        return ""
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _coerce_exact_enum(value: object, enum_cls: type[EnumType]) -> EnumType:
    # Strict boundary contract:
    # 1. Accept the exact enum type unchanged.
    # 2. Reject other Enum types, even if the string value happens to match.
    # 3. Accept only exact string matches for the target enum.
    # 4. Reject every other type.
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, Enum):
        raise TypeError(
            f"{enum_cls.__name__} must be a string or {enum_cls.__name__}, "
            f"got {value.__class__.__name__}"
        )
    if not isinstance(value, str):
        raise TypeError(
            f"{enum_cls.__name__} must be a string or {enum_cls.__name__}, "
            f"got {type(value).__name__}"
        )
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValueError(
            f"Invalid {enum_cls.__name__}: {value!r}. Allowed: {allowed}"
        ) from exc
