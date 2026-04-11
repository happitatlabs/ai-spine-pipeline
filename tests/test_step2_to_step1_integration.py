import argparse
from pathlib import Path

from pipeline.status import StepReviewStatus, StepStatus
from pipeline.step1 import load_json
from pipeline.step2 import run_step2


SAMPLES_ROOT = Path("D:/Spine/samples/step2")


def test_step2_generates_step1_manifest_and_bundle(tmp_path) -> None:
    result = run_step2(
        input_dir=SAMPLES_ROOT / "normal_case",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step2_output",
        run_step1_pipeline=True,
        step1_bundle_dir=tmp_path / "step1_bundle",
        step1_skip_roundtrip=True,
    )

    review_report = load_json(result["review_report"])
    step1_manifest = load_json(result["step1_manifest"])

    assert result["status"] == StepReviewStatus.PASS
    assert result["step1_status"] == StepStatus.PASS
    assert review_report["status"] == StepReviewStatus.PASS
    assert review_report["step1_status"] == StepStatus.PASS
    assert len(step1_manifest["parts"]) == 6
    assert (tmp_path / "step1_bundle" / "draft_skeleton.json").exists()


def test_step2_skips_step1_when_review_is_required(tmp_path) -> None:
    result = run_step2(
        input_dir=SAMPLES_ROOT / "fallback_case",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step2_output",
        run_step1_pipeline=True,
        step1_bundle_dir=tmp_path / "step1_bundle",
        step1_skip_roundtrip=True,
    )

    review_report = load_json(result["review_report"])

    assert result["status"] == StepReviewStatus.REVIEW_REQUIRED
    assert result["step1_status"] == StepStatus.SKIPPED
    assert review_report["step1_status"] == StepStatus.SKIPPED
    assert not (tmp_path / "step1_bundle").exists()


def test_step2_cli_returns_non_zero_when_requested_step1_fails(tmp_path, monkeypatch, capsys) -> None:
    import pipeline.step2 as step2

    monkeypatch.setattr(
        step2,
        "_parse_args",
        lambda: argparse.Namespace(
            input_dir=SAMPLES_ROOT / "normal_case",
            template_id="humanoid_v1",
            output_dir=tmp_path / "step2_output",
            run_step1=False,
            force_step1=True,
            step1_bundle_dir=tmp_path / "step1_bundle",
            step1_roundtrip_dir=None,
            step1_run_secondary_roundtrip=False,
            step1_secondary_project_path=None,
            step1_run_roundtrip=False,
            spine_path=None,
            force=False,
        ),
    )
    monkeypatch.setattr(
        step2,
        "run_step1",
        lambda **_: {
            "status": StepStatus.FAIL,
            "bundle_dir": str(tmp_path / "step1_bundle"),
            "review_report": str(tmp_path / "step1_bundle" / "review_report.json"),
            "mapping_confidence_avg": 0.0,
            "unresolved_parts": [],
            "missing_required_slots": ["head"],
            "roundtrip_dir": None,
        },
    )

    exit_code = step2.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "ERROR: STEP 1 FAILED" in captured.err
    assert "status: FAIL" in captured.err
    assert "error: STEP 1 returned status FAIL" in captured.err


def test_step2_marks_error_when_step1_raises(tmp_path, monkeypatch) -> None:
    import pipeline.step2 as step2

    def _raise_step1(**_):
        raise RuntimeError("boom")

    monkeypatch.setattr(step2, "run_step1", _raise_step1)

    result = run_step2(
        input_dir=SAMPLES_ROOT / "normal_case",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step2_output",
        force_step1=True,
        step1_bundle_dir=tmp_path / "step1_bundle",
        step1_skip_roundtrip=True,
    )

    review_report = load_json(result["review_report"])
    assert result["step1_status"] == StepStatus.ERROR
    assert review_report["step1_status"] == StepStatus.ERROR
    assert review_report["step1_error"] == "boom"


def test_step2_marks_error_when_step1_returns_invalid_status(tmp_path, monkeypatch) -> None:
    import pipeline.step2 as step2

    monkeypatch.setattr(
        step2,
        "run_step1",
        lambda **_: {
            "status": "pass",
            "bundle_dir": str(tmp_path / "step1_bundle"),
            "review_report": str(tmp_path / "step1_bundle" / "review_report.json"),
            "mapping_confidence_avg": 0.0,
            "unresolved_parts": [],
            "missing_required_slots": [],
            "roundtrip_dir": None,
        },
    )

    result = run_step2(
        input_dir=SAMPLES_ROOT / "normal_case",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step2_output",
        force_step1=True,
        step1_bundle_dir=tmp_path / "step1_bundle",
        step1_skip_roundtrip=True,
    )

    review_report = load_json(result["review_report"])
    assert result["step1_status"] == StepStatus.ERROR
    assert review_report["step1_status"] == StepStatus.ERROR
    assert "Invalid StepStatus" in review_report["step1_error"]
