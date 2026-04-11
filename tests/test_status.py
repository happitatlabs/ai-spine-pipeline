import pytest

from pipeline.status import (
    StepReviewStatus,
    StepRunState,
    StepStatus,
    coerce_step_review_status,
    coerce_step_run_state,
    coerce_step_status,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (StepStatus.PASS, StepStatus.PASS),
        ("PASS", StepStatus.PASS),
    ],
)
def test_coerce_step_status_accepts_exact_values(value, expected) -> None:
    assert coerce_step_status(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (StepReviewStatus.REVIEW_REQUIRED, StepReviewStatus.REVIEW_REQUIRED),
        ("REVIEW_REQUIRED", StepReviewStatus.REVIEW_REQUIRED),
    ],
)
def test_coerce_step_review_status_accepts_exact_values(value, expected) -> None:
    assert coerce_step_review_status(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (StepRunState.PENDING, StepRunState.PENDING),
        ("PENDING", StepRunState.PENDING),
    ],
)
def test_coerce_step_run_state_accepts_exact_values(value, expected) -> None:
    assert coerce_step_run_state(value) is expected


@pytest.mark.parametrize("value", ["pass", " PASS ", "", "UNKNOWN"])
def test_coerce_step_status_rejects_invalid_strings(value) -> None:
    with pytest.raises(ValueError, match=r"Invalid StepStatus: .*Allowed: PASS, FAIL, ERROR, SKIPPED"):
        coerce_step_status(value)


@pytest.mark.parametrize("value", ["review_required", " REVIEW_REQUIRED ", "", "UNKNOWN"])
def test_coerce_step_review_status_rejects_invalid_strings(value) -> None:
    with pytest.raises(ValueError, match=r"Invalid StepReviewStatus: .*Allowed: PASS, REVIEW_REQUIRED, FAIL"):
        coerce_step_review_status(value)


@pytest.mark.parametrize("value", ["pending", " PENDING ", "", "UNKNOWN"])
def test_coerce_step_run_state_rejects_invalid_strings(value) -> None:
    with pytest.raises(ValueError, match=r"Invalid StepRunState: .*Allowed: NOT_REQUESTED, PENDING"):
        coerce_step_run_state(value)


@pytest.mark.parametrize("value", [None, 0, 123, [], {}, object()])
def test_coerce_step_status_rejects_invalid_types(value) -> None:
    with pytest.raises(TypeError, match=r"StepStatus must be a string or StepStatus, got "):
        coerce_step_status(value)


@pytest.mark.parametrize("value", [None, 0, 123, [], {}, object()])
def test_coerce_step_review_status_rejects_invalid_types(value) -> None:
    with pytest.raises(TypeError, match=r"StepReviewStatus must be a string or StepReviewStatus, got "):
        coerce_step_review_status(value)


@pytest.mark.parametrize("value", [None, 0, 123, [], {}, object()])
def test_coerce_step_run_state_rejects_invalid_types(value) -> None:
    with pytest.raises(TypeError, match=r"StepRunState must be a string or StepRunState, got "):
        coerce_step_run_state(value)


def test_coerce_step_status_rejects_other_enum_types_even_if_value_matches() -> None:
    with pytest.raises(TypeError, match=r"StepStatus must be a string or StepStatus, got StepReviewStatus"):
        coerce_step_status(StepReviewStatus.PASS)
    with pytest.raises(TypeError, match=r"StepStatus must be a string or StepStatus, got StepRunState"):
        coerce_step_status(StepRunState.PENDING)


def test_coerce_step_review_status_rejects_other_enum_types_even_if_value_matches() -> None:
    with pytest.raises(TypeError, match=r"StepReviewStatus must be a string or StepReviewStatus, got StepStatus"):
        coerce_step_review_status(StepStatus.PASS)
    with pytest.raises(TypeError, match=r"StepReviewStatus must be a string or StepReviewStatus, got StepRunState"):
        coerce_step_review_status(StepRunState.PENDING)


def test_coerce_step_run_state_rejects_other_enum_types_even_if_value_matches() -> None:
    with pytest.raises(TypeError, match=r"StepRunState must be a string or StepRunState, got StepStatus"):
        coerce_step_run_state(StepStatus.PASS)
    with pytest.raises(TypeError, match=r"StepRunState must be a string or StepRunState, got StepReviewStatus"):
        coerce_step_run_state(StepReviewStatus.PASS)
