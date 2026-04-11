from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from pipeline.status import StepReviewStatus
from pipeline.step1 import load_json
from pipeline.step3 import run_step3


SAMPLES_ROOT = Path("D:/Spine/samples/step3")


def test_step3_plain_image_set_is_copy_only_and_passes(tmp_path) -> None:
    input_dir = SAMPLES_ROOT / "plain_image_set"
    before = _snapshot_tree(input_dir)

    result = run_step3(
        input_dir=input_dir,
        input_kind="image_set",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
    )

    after = _snapshot_tree(input_dir)
    review_report = load_json(result["review_report"])
    adapter_manifest = load_json(result["adapter_manifest"])

    assert before == after
    assert result["status"] == StepReviewStatus.PASS
    assert review_report["status"] == StepReviewStatus.PASS
    assert len(adapter_manifest["assets"]) == 6
    assert sorted(path.name for path in (Path(result["step2_input_dir"]) / "raw").glob("*.png")) == [
        "arm-l.png",
        "arm-r.png",
        "body.png",
        "head.png",
        "leg-l.png",
        "leg-r.png",
    ]


def test_step3_ai_package_valid_passes_and_records_hints(tmp_path) -> None:
    result = run_step3(
        input_dir=SAMPLES_ROOT / "ai_package_valid",
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
        meta_json="metadata.json",
    )

    adapter_manifest = load_json(result["adapter_manifest"])
    review_report = load_json(result["review_report"])
    assets_by_source = {asset["source_path"]: asset for asset in adapter_manifest["assets"]}

    assert result["status"] == StepReviewStatus.PASS
    assert review_report["status"] == StepReviewStatus.PASS
    assert assets_by_source["incoming/front_upper_arm.png"]["prepared_name"] == "arm-l"
    assert assets_by_source["incoming/front_upper_arm.png"]["category_hint"] == "arm"
    assert any(entry["type"] == "meta_name" for entry in assets_by_source["incoming/front_upper_arm.png"]["trace"])
    assert any(entry["type"] == "copy" for entry in assets_by_source["incoming/front_upper_arm.png"]["trace"])


def test_step3_ai_package_without_metadata_fails(tmp_path) -> None:
    result = run_step3(
        input_dir=SAMPLES_ROOT / "ai_package_valid",
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
    )

    review_report = load_json(result["review_report"])

    assert result["status"] == StepReviewStatus.FAIL
    assert review_report["status"] == StepReviewStatus.FAIL
    assert any(issue["type"] == "missing_metadata" for issue in review_report["issues"])
    assert not Path(result["adapter_manifest"]).exists()


def test_step3_ai_package_partial_metadata_is_review_required(tmp_path) -> None:
    result = run_step3(
        input_dir=SAMPLES_ROOT / "ai_package_partial",
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
        meta_json="metadata.json",
    )

    review_report = load_json(result["review_report"])
    adapter_manifest = load_json(result["adapter_manifest"])
    review_needed_assets = [asset for asset in adapter_manifest["assets"] if asset["review_needed"]]

    assert result["status"] == StepReviewStatus.REVIEW_REQUIRED
    assert review_report["status"] == StepReviewStatus.REVIEW_REQUIRED
    assert review_report["summary"]["review_needed_count"] > 0
    assert any(issue["type"] == "metadata_incomplete" for issue in review_report["issues"])
    assert review_needed_assets


def test_step3_invalid_suggested_name_fails(tmp_path) -> None:
    input_dir = tmp_path / "ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    _write_png(incoming / "front_upper_arm.png")
    (input_dir / "metadata.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "assets": [
                    {
                        "source": "incoming/front_upper_arm.png",
                        "suggested_name": "!!!",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_step3(
        input_dir=input_dir,
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
        meta_json="metadata.json",
    )

    review_report = load_json(result["review_report"])
    assert result["status"] == StepReviewStatus.FAIL
    assert any(issue["type"] == "invalid_suggested_name" for issue in review_report["issues"])


def test_step3_metadata_missing_source_fails(tmp_path) -> None:
    result = run_step3(
        input_dir=SAMPLES_ROOT / "ai_package_broken",
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
        meta_json="metadata.json",
    )

    review_report = load_json(result["review_report"])
    assert result["status"] == StepReviewStatus.FAIL
    assert any(issue["type"] == "missing_source" for issue in review_report["issues"])


def test_step3_collision_suffix_is_deterministic_and_review_required(tmp_path) -> None:
    input_dir = tmp_path / "ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    _write_png(incoming / "arm_a.png")
    _write_png(incoming / "arm_b.png")
    (input_dir / "metadata.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "assets": [
                    {"source": "incoming/arm_a.png", "suggested_name": "Arm"},
                    {"source": "incoming/arm_b.png", "suggested_name": "Arm"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_step3(
        input_dir=input_dir,
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
        meta_json="metadata.json",
    )

    adapter_manifest = load_json(result["adapter_manifest"])
    review_report = load_json(result["review_report"])
    prepared_names = [asset["prepared_name"] for asset in adapter_manifest["assets"]]

    assert result["status"] == StepReviewStatus.REVIEW_REQUIRED
    assert prepared_names == ["arm", "arm--2"]
    assert any(issue["type"] == "duplicate_target" for issue in review_report["issues"])


def test_step3_is_idempotent_with_force(tmp_path) -> None:
    input_dir = SAMPLES_ROOT / "ai_package_valid"
    before = _snapshot_tree(input_dir)
    output_dir = tmp_path / "step3_output"

    run_step3(
        input_dir=input_dir,
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=output_dir,
        meta_json="metadata.json",
        force=True,
    )
    first = _content_snapshot(output_dir)

    run_step3(
        input_dir=input_dir,
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=output_dir,
        meta_json="metadata.json",
        force=True,
    )
    second = _content_snapshot(output_dir)
    after = _snapshot_tree(input_dir)

    assert first == second
    assert before == after


def _write_png(path: Path) -> None:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    image.save(path)


def _snapshot_tree(root: Path) -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    return snapshot


def _content_snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot
