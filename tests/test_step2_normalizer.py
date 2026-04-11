from pathlib import Path

from pipeline.asset_scanner import scan_assets
from pipeline.normalizer import load_step2_rules, normalize_assets
from pipeline.review import build_review_report
from pipeline.status import StepReviewStatus


SAMPLES_ROOT = Path("D:/Spine/samples/step2")


def test_normalize_assets_direct_match_is_exact() -> None:
    rules = load_step2_rules("humanoid_v1")
    assets = scan_assets(SAMPLES_ROOT / "normal_case")

    normalized = normalize_assets(assets, rules)
    selected = {asset.normalized_name: asset for asset in normalized if asset.selected}

    assert set(selected) == {"head", "body", "arm_l", "arm_r", "leg_l", "leg_r"}
    assert all(asset.confidence == 1.0 for asset in selected.values())


def test_normalize_assets_uses_fallback_scoring() -> None:
    rules = load_step2_rules("humanoid_v1")
    assets = scan_assets(SAMPLES_ROOT / "fallback_case")

    normalized = normalize_assets(assets, rules)
    selected = {asset.normalized_name: asset for asset in normalized if asset.selected}

    assert selected["body"].relative_path == "raw/torso.png"
    assert selected["body"].confidence == 0.6
    assert selected["arm_l"].relative_path == "raw/front-upper-arm.png"
    assert selected["arm_l"].confidence == 0.6
    assert selected["arm_r"].relative_path == "raw/rear-upper-arm.png"


def test_normalize_assets_is_deterministic_for_duplicates_and_review_status() -> None:
    rules = load_step2_rules("humanoid_v1")
    assets = scan_assets(SAMPLES_ROOT / "ambiguous_case")

    normalized = normalize_assets(assets, rules)
    selected_body = next(asset for asset in normalized if asset.selected and asset.normalized_name == "body")
    duplicate_body = next(asset for asset in normalized if asset.relative_path == "raw/body_main.png")

    assert selected_body.relative_path == "raw/body_alt.png"
    assert duplicate_body.reject_reason == "duplicate:body"

    report = build_review_report(normalized, rules)
    assert report.status == StepReviewStatus.FAIL
    assert "body" in report.duplicate_groups
    assert "arm_l" in report.missing_required_parts
    assert "arm_r" in report.missing_required_parts
    assert "raw/arm.png" in report.unresolved_parts
