from pathlib import Path

from pipeline.asset_scanner import scan_assets


SAMPLES_ROOT = Path("D:/Spine/samples/step2")


def test_scan_assets_recurses_and_tokenizes() -> None:
    assets = scan_assets(SAMPLES_ROOT / "fallback_case")

    relative_paths = [asset.relative_path for asset in assets]
    assert relative_paths == sorted(relative_paths)

    arm_asset = next(asset for asset in assets if asset.relative_path.endswith("front-upper-arm.png"))
    assert {"front", "upper", "arm"}.issubset(set(arm_asset.tokens))
    assert all(entry.type == "tokenized" for entry in arm_asset.trace)
    assert arm_asset.alpha_bbox[2] > 0
    assert arm_asset.alpha_bbox[3] > 0
