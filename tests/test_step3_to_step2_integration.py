from pathlib import Path

from pipeline.status import StepReviewStatus, StepRunState
from pipeline.step1 import load_json
from pipeline.step2 import run_step2
from pipeline.step3 import run_step3


SAMPLES_ROOT = Path("D:/Spine/samples/step3")


def test_step3_output_connects_to_step2(tmp_path) -> None:
    step3_result = run_step3(
        input_dir=SAMPLES_ROOT / "ai_package_valid",
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
        meta_json="metadata.json",
    )

    step2_result = run_step2(
        input_dir=step3_result["step2_input_dir"],
        template_id="humanoid_v1",
        output_dir=tmp_path / "step2_output",
    )

    step2_review = load_json(step2_result["review_report"])
    assert step3_result["status"] == StepReviewStatus.PASS
    assert step2_result["status"] == StepReviewStatus.PASS
    assert step2_result["step1_status"] == StepRunState.NOT_REQUESTED
    assert step2_review["status"] == StepReviewStatus.PASS
    assert Path(step2_result["normalized_manifest"]).exists()
    assert Path(step2_result["step1_manifest"]).exists()
