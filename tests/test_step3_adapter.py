from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random

from PIL import Image

from pipeline.status import StepReviewStatus
from pipeline.step1 import load_json
from pipeline.step3_contracts import AdapterTraceEntry, PreparedAsset
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


def test_step3_fails_when_input_path_is_file(tmp_path) -> None:
    input_file = tmp_path / "not_a_dir.txt"
    input_file.write_text("x", encoding="utf-8")

    result = run_step3(
        input_dir=input_file,
        input_kind="image_set",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
    )

    review_report = load_json(result["review_report"])
    assert result["status"] == StepReviewStatus.FAIL
    assert any(issue["type"] == "invalid_input_dir" for issue in review_report["issues"])


def test_step3_fails_when_no_png_found(tmp_path) -> None:
    input_dir = tmp_path / "empty"
    input_dir.mkdir()
    (input_dir / "notes.txt").write_text("hello", encoding="utf-8")

    result = run_step3(
        input_dir=input_dir,
        input_kind="image_set",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
    )

    review_report = load_json(result["review_report"])
    assert result["status"] == StepReviewStatus.FAIL
    assert any(issue["type"] == "no_png_found" for issue in review_report["issues"])


def test_step3_accepts_uppercase_png_and_ignores_non_png(tmp_path) -> None:
    input_dir = tmp_path / "mixed"
    nested = input_dir / "nested"
    nested.mkdir(parents=True)
    _write_png(nested / "Head.PNG")
    (nested / "ignore.jpg").write_bytes(b"not-png")

    result = run_step3(
        input_dir=input_dir,
        input_kind="image_set",
        template_id="humanoid_v1",
        output_dir=tmp_path / "step3_output",
    )

    adapter_manifest = load_json(result["adapter_manifest"])
    assert result["status"] == StepReviewStatus.PASS
    assert len(adapter_manifest["assets"]) == 1
    assert adapter_manifest["assets"][0]["prepared_name"] == "head"


def test_step3_fails_when_metadata_assets_is_not_list(tmp_path) -> None:
    input_dir = tmp_path / "ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    _write_png(incoming / "head.png")
    (input_dir / "metadata.json").write_text(
        json.dumps({"manifest_version": 1, "assets": {}}),
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
    assert any(issue["type"] == "invalid_metadata" for issue in review_report["issues"])


def test_step3_fails_when_metadata_entry_is_not_object(tmp_path) -> None:
    input_dir = tmp_path / "ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    _write_png(incoming / "head.png")
    (input_dir / "metadata.json").write_text(
        json.dumps({"manifest_version": 1, "assets": ["bad"]}),
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
    assert any(issue["type"] == "invalid_metadata" for issue in review_report["issues"])


def test_step3_fails_when_metadata_source_escapes_input_dir(tmp_path) -> None:
    input_dir = tmp_path / "ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    _write_png(incoming / "head.png")
    outside = tmp_path / "outside"
    outside.mkdir()
    _write_png(outside / "head.png")
    (input_dir / "metadata.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "assets": [
                    {"source": "../outside/head.png", "suggested_name": "head"},
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
    assert any(issue["type"] == "missing_source" for issue in review_report["issues"])


def test_step3_fails_when_duplicate_source_metadata_conflicts(tmp_path) -> None:
    input_dir = tmp_path / "ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    _write_png(incoming / "head.png")
    (input_dir / "metadata.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "assets": [
                    {"source": "incoming/head.png", "suggested_name": "head"},
                    {"source": "incoming/head.png", "suggested_name": "body"},
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
    assert any(issue["type"] == "conflicting_metadata" for issue in review_report["issues"])


def test_step3_ai_package_empty_metadata_assets_is_review_required(tmp_path) -> None:
    input_dir = tmp_path / "ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    _write_png(incoming / "head.png")
    (input_dir / "metadata.json").write_text(
        json.dumps({"manifest_version": 1, "assets": []}),
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
    adapter_manifest = load_json(result["adapter_manifest"])
    assert result["status"] == StepReviewStatus.REVIEW_REQUIRED
    assert any(issue["type"] == "metadata_incomplete" for issue in review_report["issues"])
    assert adapter_manifest["assets"][0]["review_needed"] is True


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


def test_step3_large_seeded_input_is_deterministic_and_copy_only(tmp_path) -> None:
    rng = random.Random(20260411)
    input_dir = tmp_path / "large_ai_package"
    incoming = input_dir / "incoming"
    incoming.mkdir(parents=True)
    assets = []
    for index in range(120):
        stem = f"Part_{index % 17}_{rng.choice(['Left', 'Right', 'Upper', 'Lower'])}_{index}"
        filename = f"{stem}.png"
        _write_png(incoming / filename, color=(index % 255, (index * 7) % 255, (index * 11) % 255, 255))
        assets.append(
            {
                "source": f"incoming/{filename}",
                "suggested_name": f"group_{index % 9}_{rng.choice(['Alpha', 'Beta', 'Gamma'])}",
                "review_needed": bool(index % 13 == 0),
            }
        )
    (input_dir / "metadata.json").write_text(
        json.dumps({"manifest_version": 1, "assets": assets}, indent=2),
        encoding="utf-8",
    )

    before = _snapshot_tree(input_dir)
    output_a = tmp_path / "step3_output_a"
    output_b = tmp_path / "step3_output_b"

    result_a = run_step3(
        input_dir=input_dir,
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=output_a,
        meta_json="metadata.json",
        force=True,
    )
    result_b = run_step3(
        input_dir=input_dir,
        input_kind="ai_package",
        template_id="humanoid_v1",
        output_dir=output_b,
        meta_json="metadata.json",
        force=True,
    )

    after = _snapshot_tree(input_dir)
    assert before == after
    assert result_a["status"] == result_b["status"] == StepReviewStatus.REVIEW_REQUIRED
    assert _content_snapshot(output_a) == _content_snapshot(output_b)


def test_prepared_asset_contract_rejects_missing_required_fields() -> None:
    asset = PreparedAsset(
        source_path="incoming/head.png",
        prepared_path="raw/head.png",
        original_name="head",
        prepared_name="head",
        review_needed=False,
        trace=[AdapterTraceEntry(type="copy", value="incoming/head.png", target="prepared_path", result="raw/head.png")],
    )
    assert asset.to_dict()["prepared_name"] == "head"

    broken = PreparedAsset(
        source_path="incoming/head.png",
        prepared_path="raw/head.png",
        original_name="head",
        prepared_name="",
        review_needed=False,
        trace=[AdapterTraceEntry(type="copy", value="incoming/head.png", target="prepared_path", result="raw/head.png")],
    )
    try:
        broken.to_dict()
    except ValueError as exc:
        assert "required field prepared_name" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("PreparedAsset.to_dict() should reject missing required fields")


def _write_png(path: Path, color: tuple[int, int, int, int] = (255, 0, 0, 255)) -> None:
    image = Image.new("RGBA", (8, 8), color)
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
