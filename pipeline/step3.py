from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from pipeline.ai_adapter import build_adapter_output, copy_prepared_assets
from pipeline.status import StepReviewStatus, render_status
from pipeline.step1 import write_json


def run_step3(
    *,
    input_dir: str | Path,
    input_kind: str,
    template_id: str,
    output_dir: str | Path,
    meta_json: str | Path | None = None,
    force: bool = False,
) -> dict[str, str | StepReviewStatus]:
    output_root = Path(output_dir).resolve()
    if output_root.exists():
        if not force:
            raise FileExistsError(f"STEP 3 output_dir already exists: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=False)

    step2_input_dir = output_root / "step2_input"
    raw_dir = step2_input_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=False)

    prepared_assets, review_report = build_adapter_output(
        input_dir=input_dir,
        input_kind=input_kind,
        template_id=template_id,
        meta_json=meta_json,
    )

    adapter_manifest_path = step2_input_dir / "adapter_manifest.json"
    review_report_path = output_root / "review_report.json"

    if review_report.status != StepReviewStatus.FAIL:
        copy_prepared_assets(
            input_dir=input_dir,
            output_step2_dir=step2_input_dir,
            assets=prepared_assets,
        )
        write_json(
            adapter_manifest_path,
            {
                "manifest_version": 1,
                "template_id": template_id,
                "input_kind": input_kind,
                "assets": [asset.to_dict() for asset in prepared_assets],
            },
        )

    write_json(review_report_path, review_report.to_dict())
    return {
        "status": review_report.status,
        "step2_input_dir": str(step2_input_dir),
        "adapter_manifest": str(adapter_manifest_path),
        "review_report": str(review_report_path),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run STEP 3 copy-only external result adapter.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--input-kind", required=True, choices=["image_set", "ai_package", "manual_prep"])
    parser.add_argument("--template-id", default="humanoid_v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--meta-json")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_step3(
        input_dir=args.input_dir,
        input_kind=args.input_kind,
        template_id=args.template_id,
        output_dir=args.output_dir,
        meta_json=args.meta_json,
        force=args.force,
    )
    print(f"status={render_status(result['status'])}")
    print(f"step2_input_dir={result['step2_input_dir']}")
    print(f"adapter_manifest={result['adapter_manifest']}")
    print(f"review_report={result['review_report']}")
    return 0 if result["status"] != StepReviewStatus.FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
