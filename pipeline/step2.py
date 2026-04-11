from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
from typing import Any

from pipeline.asset_scanner import scan_assets
from pipeline.normalizer import build_step1_manifest, load_step2_rules, normalize_assets
from pipeline.review import build_review_report
from pipeline.status import (
    StepReviewStatus,
    StepRunState,
    StepStatus,
    coerce_step_status,
    render_status,
)
from pipeline.step1 import run_step1, write_json
from pipeline.step2_contracts import NormalizedAsset, ReviewReport


def run_step2(
    *,
    input_dir: str | Path,
    template_id: str,
    output_dir: str | Path,
    run_step1_pipeline: bool = False,
    force_step1: bool = False,
    step1_bundle_dir: str | Path | None = None,
    step1_roundtrip_dir: str | Path | None = None,
    step1_run_secondary_roundtrip: bool = False,
    step1_secondary_project_path: str | Path | None = None,
    spine_path: str | None = None,
    step1_skip_roundtrip: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    output_root = Path(output_dir).resolve()
    if output_root.exists():
        if not force:
            raise FileExistsError(f"STEP 2 output_dir already exists: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=False)

    rules = load_step2_rules(template_id)
    scanned_assets = scan_assets(input_dir)
    normalized_assets = normalize_assets(scanned_assets, rules)
    review_report = build_review_report(normalized_assets, rules)

    selected_dir = output_root / "normalized_assets" / "selected"
    rejected_dir = output_root / "normalized_assets" / "rejected"
    selected_dir.mkdir(parents=True, exist_ok=False)
    rejected_dir.mkdir(parents=True, exist_ok=False)
    _copy_assets(normalized_assets, selected_dir, rejected_dir)

    normalized_manifest_path = output_root / "normalized_manifest.json"
    step1_manifest_path = output_root / "step1_parts_manifest.json"
    review_report_path = output_root / "review_report.json"

    write_json(
        normalized_manifest_path,
        {
            "manifest_version": 1,
            "template_id": template_id,
            "scan_root": str(Path(input_dir).resolve()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parts": [asset.to_dict() for asset in normalized_assets],
        },
    )
    write_json(step1_manifest_path, build_step1_manifest(normalized_assets, rules))

    step1_requested = run_step1_pipeline or force_step1
    _update_step1_state(
        review_report=review_report,
        run_step1_pipeline=run_step1_pipeline,
        force_step1=force_step1,
    )

    if step1_requested and _should_run_step1(review_report.status, force_step1):
        bundle_dir = Path(step1_bundle_dir or (output_root / "step1_bundle"))
        roundtrip_dir = Path(step1_roundtrip_dir) if step1_roundtrip_dir else None
        secondary_project_path = (
            Path(step1_secondary_project_path)
            if step1_secondary_project_path
            else (roundtrip_dir / "generated.spine" if roundtrip_dir else None)
        )
        try:
            result = run_step1(
                parts_manifest_path=step1_manifest_path,
                template_id=template_id,
                bundle_dir=bundle_dir,
                roundtrip_dir=roundtrip_dir,
                run_secondary_roundtrip=step1_run_secondary_roundtrip,
                secondary_project_path=secondary_project_path,
                spine_path=spine_path or r"C:\Program Files\Spine\Spine.com",
                skip_roundtrip=step1_skip_roundtrip,
            )
            review_report.step1_status = coerce_step_status(result["status"])
            if review_report.step1_status != StepStatus.PASS:
                review_report.step1_error = f"STEP 1 returned status {render_status(review_report.step1_status)}"
        except Exception as exc:  # pragma: no cover - exercised via integration gating
            review_report.step1_status = StepStatus.ERROR
            review_report.step1_error = str(exc)
            review_report.notes.append(f"STEP 1 execution failed -> {exc}")

    write_json(review_report_path, review_report.to_dict())
    return {
        "status": review_report.status,
        "normalized_manifest": str(normalized_manifest_path),
        "step1_manifest": str(step1_manifest_path),
        "review_report": str(review_report_path),
        "step1_status": review_report.step1_status,
        "step1_error": review_report.step1_error,
        "output_dir": str(output_root),
    }


def _copy_assets(normalized_assets: list[NormalizedAsset], selected_dir: Path, rejected_dir: Path) -> None:
    for asset in normalized_assets:
        if asset.selected and asset.normalized_name:
            destination = selected_dir / f"{asset.normalized_name}.png"
        else:
            destination = rejected_dir / _safe_copy_name(asset.relative_path)
        shutil.copy2(asset.source_path, destination)


def _safe_copy_name(relative_path: str) -> str:
    path = Path(relative_path)
    sanitized = "__".join(path.parts)
    return sanitized.replace(" ", "_")


def _should_run_step1(status: StepReviewStatus, force_step1: bool) -> bool:
    if status == StepReviewStatus.FAIL:
        return False
    if status == StepReviewStatus.REVIEW_REQUIRED:
        return force_step1
    return status == StepReviewStatus.PASS


def _update_step1_state(
    *,
    review_report: ReviewReport,
    run_step1_pipeline: bool,
    force_step1: bool,
) -> None:
    if not (run_step1_pipeline or force_step1):
        review_report.step1_status = StepRunState.NOT_REQUESTED
        return
    if review_report.status == StepReviewStatus.FAIL:
        review_report.step1_status = StepStatus.SKIPPED
        review_report.notes.append("STEP 1 execution skipped because STEP 2 status is FAIL")
        return
    if review_report.status == StepReviewStatus.REVIEW_REQUIRED and not force_step1:
        review_report.step1_status = StepStatus.SKIPPED
        review_report.notes.append("STEP 1 execution skipped because STEP 2 review is required")
        return
    review_report.step1_status = StepRunState.PENDING


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run STEP 2 deterministic asset normalization.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--template-id", default="humanoid_v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-step1", action="store_true")
    parser.add_argument("--force-step1", action="store_true")
    parser.add_argument("--step1-bundle-dir")
    parser.add_argument("--step1-roundtrip-dir")
    parser.add_argument("--step1-run-secondary-roundtrip", action="store_true")
    parser.add_argument("--step1-secondary-project-path")
    parser.add_argument("--step1-run-roundtrip", action="store_true")
    parser.add_argument("--spine-path")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_step2(
        input_dir=args.input_dir,
        template_id=args.template_id,
        output_dir=args.output_dir,
        run_step1_pipeline=args.run_step1,
        force_step1=args.force_step1,
        step1_bundle_dir=args.step1_bundle_dir,
        step1_roundtrip_dir=args.step1_roundtrip_dir,
        step1_run_secondary_roundtrip=args.step1_run_secondary_roundtrip,
        step1_secondary_project_path=args.step1_secondary_project_path,
        spine_path=args.spine_path,
        step1_skip_roundtrip=not args.step1_run_roundtrip,
        force=args.force,
    )
    print(f"status={render_status(result['status'])}")
    print(f"normalized_manifest={result['normalized_manifest']}")
    print(f"step1_manifest={result['step1_manifest']}")
    print(f"review_report={result['review_report']}")
    print(f"step1_status={render_status(result['step1_status'])}")
    if result["step1_error"]:
        print(f"step1_error={result['step1_error']}")
    step1_requested = bool(args.run_step1 or args.force_step1)
    # If STEP 1 was requested, PASS is the only successful outcome for the CLI.
    if step1_requested and result["step1_status"] != StepStatus.PASS:
        _print_step1_failure(result["step1_status"], result["step1_error"])
        return 1
    return 0 if result["status"] != StepReviewStatus.FAIL else 1


def _print_step1_failure(step1_status: StepStatus | StepRunState | str, step1_error: str | None) -> None:
    print("ERROR: STEP 1 FAILED", file=sys.stderr)
    print(f"status: {render_status(step1_status)}", file=sys.stderr)
    if step1_error:
        print(f"error: {step1_error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
