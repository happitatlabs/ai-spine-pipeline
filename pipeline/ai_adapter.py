from __future__ import annotations

import json
import re
from pathlib import Path
import shutil
from typing import Any

from pipeline.status import StepReviewStatus
from pipeline.step3_contracts import AdapterIssue, AdapterReviewReport, AdapterTraceEntry, PreparedAsset


INPUT_KINDS = {"image_set", "ai_package", "manual_prep"}
SAFE_NAME_RE = re.compile(r"[^a-z0-9-]+")
SEPARATOR_RE = re.compile(r"-{2,}")


def build_adapter_output(
    *,
    input_dir: str | Path,
    input_kind: str,
    template_id: str,
    meta_json: str | Path | None = None,
) -> tuple[list[PreparedAsset], AdapterReviewReport]:
    root = Path(input_dir).resolve()
    issues: list[AdapterIssue] = []
    notes: list[str] = []
    summary = {
        "discovered_png_count": 0,
        "prepared_png_count": 0,
        "review_needed_count": 0,
        "missing_source_count": 0,
        "duplicate_target_count": 0,
    }

    if input_kind not in INPUT_KINDS:
        issues.append(
            AdapterIssue(
                type="invalid_input_kind",
                severity="error",
                item=input_kind,
                message=f"unsupported input_kind: {input_kind}",
            )
        )
        return [], _fail_report(template_id, input_kind, summary, issues, notes)

    if not root.exists():
        issues.append(
            AdapterIssue(
                type="missing_input_dir",
                severity="error",
                item=str(root),
                message=f"input_dir not found: {root}",
            )
        )
        return [], _fail_report(template_id, input_kind, summary, issues, notes)
    if not root.is_dir():
        issues.append(
            AdapterIssue(
                type="invalid_input_dir",
                severity="error",
                item=str(root),
                message=f"input_dir is not a directory: {root}",
            )
        )
        return [], _fail_report(template_id, input_kind, summary, issues, notes)

    discovered = discover_pngs(root)
    summary["discovered_png_count"] = len(discovered)
    if not discovered:
        issues.append(
            AdapterIssue(
                type="no_png_found",
                severity="error",
                item=str(root),
                message="no usable PNG files found",
            )
        )
        return [], _fail_report(template_id, input_kind, summary, issues, notes)

    metadata, metadata_issues, coverage = load_metadata(
        input_dir=root,
        input_kind=input_kind,
        meta_json=meta_json,
        discovered=discovered,
    )
    issues.extend(metadata_issues)
    if any(issue.severity == "error" for issue in issues):
        summary["missing_source_count"] = sum(1 for issue in issues if issue.type == "missing_source")
        return [], _fail_report(template_id, input_kind, summary, issues, notes)

    name_counts: dict[str, int] = {}
    prepared_assets: list[PreparedAsset] = []
    duplicate_count = 0

    for source_path in discovered:
        relative_path = source_path.relative_to(root).as_posix()
        metadata_entry = metadata.get(relative_path)
        original_name = source_path.stem
        asset_notes: list[str] = []
        asset_trace: list[AdapterTraceEntry] = []
        review_needed = False

        if metadata_entry and metadata_entry.get("suggested_name") is not None:
            prepared_base = sanitize_prepared_name(str(metadata_entry["suggested_name"]))
            asset_trace.append(
                AdapterTraceEntry(
                    type="meta_name",
                    value=metadata_entry["suggested_name"],
                    target="prepared_name",
                    result=prepared_base,
                )
            )
            if not prepared_base:
                issues.append(
                    AdapterIssue(
                        type="invalid_suggested_name",
                        severity="error",
                        item=relative_path,
                        message="sanitize result for suggested_name is empty",
                    )
                )
                return [], _fail_report(template_id, input_kind, summary, issues, notes)
        else:
            prepared_base = sanitize_prepared_name(original_name)
            asset_trace.append(
                AdapterTraceEntry(
                    type="source_name",
                    value=original_name,
                    target="prepared_name",
                    result=prepared_base,
                )
            )
            if not prepared_base:
                issues.append(
                    AdapterIssue(
                        type="invalid_source_name",
                        severity="error",
                        item=relative_path,
                        message="sanitize result for source file stem is empty",
                    )
                )
                return [], _fail_report(template_id, input_kind, summary, issues, notes)

        if coverage["partial"] and relative_path not in coverage["covered_paths"]:
            review_needed = True
            asset_notes.append("metadata incomplete for this asset")
            asset_trace.append(
                AdapterTraceEntry(
                    type="coverage_gap",
                    value=relative_path,
                    target="review_needed",
                    result=True,
                )
            )

        if metadata_entry and bool(metadata_entry.get("review_needed")):
            review_needed = True
            asset_notes.append("metadata marked this asset as review-needed")
            asset_trace.append(
                AdapterTraceEntry(
                    type="meta_review_needed",
                    value=True,
                    target="review_needed",
                    result=True,
                )
            )

        occurrence = name_counts.get(prepared_base, 0) + 1
        name_counts[prepared_base] = occurrence
        prepared_name = prepared_base if occurrence == 1 else f"{prepared_base}--{occurrence}"
        if occurrence > 1:
            duplicate_count += 1
            review_needed = True
            asset_notes.append("prepared target name collided; deterministic suffix applied")
            asset_trace.append(
                AdapterTraceEntry(
                    type="collision_suffix",
                    value=prepared_base,
                    target="prepared_name",
                    result=prepared_name,
                )
            )
            issues.append(
                AdapterIssue(
                    type="duplicate_target",
                    severity="warning",
                    item=prepared_base,
                    message="two inputs resolved to the same prepared name; deterministic suffix applied",
                )
            )

        prepared_path = f"raw/{prepared_name}.png"
        asset_trace.append(
            AdapterTraceEntry(
                type="copy",
                value=relative_path,
                target="prepared_path",
                result=prepared_path,
            )
        )

        metadata_notes = list(metadata_entry.get("notes", [])) if metadata_entry else []
        combined_notes = metadata_notes + [note for note in asset_notes if note not in metadata_notes]

        prepared_assets.append(
            PreparedAsset(
                source_path=relative_path,
                prepared_path=prepared_path,
                original_name=original_name,
                prepared_name=prepared_name,
                review_needed=review_needed,
                trace=asset_trace,
                category_hint=_optional_string(metadata_entry, "category_hint"),
                side_hint=_optional_string(metadata_entry, "side_hint"),
                variant_hint=_optional_string(metadata_entry, "variant_hint"),
                notes=combined_notes or None,
            )
        )

    summary["prepared_png_count"] = len(prepared_assets)
    summary["review_needed_count"] = sum(1 for asset in prepared_assets if asset.review_needed)
    summary["missing_source_count"] = sum(1 for issue in issues if issue.type == "missing_source")
    summary["duplicate_target_count"] = duplicate_count

    if coverage["partial"]:
        issues.append(
            AdapterIssue(
                type="metadata_incomplete",
                severity="warning",
                item=input_kind,
                message="metadata did not cover every discovered PNG asset",
            )
        )
        notes.append("manual review is required because metadata coverage is incomplete")

    if input_kind == "ai_package" and any(asset.review_needed for asset in prepared_assets):
        notes.append("manual review is required before trusting AI hints")
    elif any(asset.review_needed for asset in prepared_assets):
        notes.append("manual review is required for input uncertainty")

    if any(issue.severity == "error" for issue in issues):
        return [], _fail_report(template_id, input_kind, summary, issues, notes)

    status = StepReviewStatus.REVIEW_REQUIRED if issues or any(asset.review_needed for asset in prepared_assets) else StepReviewStatus.PASS
    if status != StepReviewStatus.FAIL:
        notes.insert(0, "prepared output is valid for STEP 2")
    return prepared_assets, AdapterReviewReport(
        status=status,
        template_id=template_id,
        input_kind=input_kind,
        summary=summary,
        issues=issues,
        notes=notes,
    )


def copy_prepared_assets(
    *,
    input_dir: str | Path,
    output_step2_dir: str | Path,
    assets: list[PreparedAsset],
) -> None:
    input_root = Path(input_dir).resolve()
    step2_root = Path(output_step2_dir).resolve()
    raw_dir = step2_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for asset in assets:
        source = (input_root / Path(asset.source_path)).resolve()
        destination = (step2_root / Path(asset.prepared_path)).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        shutil.copy2(source, destination)


def discover_pngs(input_dir: str | Path) -> list[Path]:
    root = Path(input_dir).resolve()
    return sorted(
        [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".png"],
        key=lambda item: item.relative_to(root).as_posix().lower(),
    )


def load_metadata(
    *,
    input_dir: Path,
    input_kind: str,
    meta_json: str | Path | None,
    discovered: list[Path],
) -> tuple[dict[str, dict[str, Any]], list[AdapterIssue], dict[str, Any]]:
    issues: list[AdapterIssue] = []
    coverage = {
        "partial": False,
        "covered_paths": set(),
    }

    metadata_path = None
    if meta_json:
        candidate = Path(meta_json)
        metadata_path = candidate if candidate.is_absolute() else (input_dir / candidate)
    elif input_kind == "ai_package":
        issues.append(
            AdapterIssue(
                type="missing_metadata",
                severity="error",
                item=input_kind,
                message="ai_package requires metadata JSON",
            )
        )
        return {}, issues, coverage

    if metadata_path is None:
        return {}, issues, coverage
    if not metadata_path.exists():
        issues.append(
            AdapterIssue(
                type="missing_metadata",
                severity="error",
                item=str(metadata_path),
                message=f"metadata JSON not found: {metadata_path}",
            )
        )
        return {}, issues, coverage

    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(
            AdapterIssue(
                type="unreadable_metadata",
                severity="error",
                item=str(metadata_path),
                message=f"metadata JSON could not be read: {exc}",
            )
        )
        return {}, issues, coverage

    assets = raw.get("assets")
    if not isinstance(assets, list):
        issues.append(
            AdapterIssue(
                type="invalid_metadata",
                severity="error",
                item=str(metadata_path),
                message="metadata JSON must contain an assets list",
            )
        )
        return {}, issues, coverage

    discovered_set = {path.relative_to(input_dir).as_posix() for path in discovered}
    metadata_by_source: dict[str, dict[str, Any]] = {}
    for item in assets:
        if not isinstance(item, dict):
            issues.append(
                AdapterIssue(
                    type="invalid_metadata",
                    severity="error",
                    item=str(metadata_path),
                    message="metadata assets entries must be objects",
                )
            )
            continue
        source = item.get("source")
        if not isinstance(source, str) or not source:
            issues.append(
                AdapterIssue(
                    type="missing_source",
                    severity="error",
                    item=str(metadata_path),
                    message="metadata asset entry is missing source",
                )
            )
            continue
        normalized_source = _normalize_relative_source(input_dir, source)
        if normalized_source is None or normalized_source not in discovered_set:
            issues.append(
                AdapterIssue(
                    type="missing_source",
                    severity="error",
                    item=source,
                    message="metadata source does not resolve to an existing PNG under input_dir",
                )
            )
            continue
        normalized_entry = {
            "source": normalized_source,
            "suggested_name": item.get("suggested_name"),
            "category_hint": item.get("category_hint"),
            "side_hint": item.get("side_hint"),
            "variant_hint": item.get("variant_hint"),
            "review_needed": bool(item.get("review_needed", False)),
            "notes": list(item.get("notes", [])) if isinstance(item.get("notes", []), list) else [],
        }
        existing = metadata_by_source.get(normalized_source)
        if existing is not None and existing != normalized_entry:
            issues.append(
                AdapterIssue(
                    type="conflicting_metadata",
                    severity="error",
                    item=normalized_source,
                    message="metadata contains conflicting duplicate entries for the same source",
                )
            )
            continue
        metadata_by_source[normalized_source] = normalized_entry

    covered_paths = set(metadata_by_source)
    if metadata_by_source and covered_paths != discovered_set:
        coverage["partial"] = True
    coverage["covered_paths"] = covered_paths
    return metadata_by_source, issues, coverage


def sanitize_prepared_name(value: str) -> str:
    lowered = value.lower().replace(" ", "-").replace("_", "-")
    sanitized = SAFE_NAME_RE.sub("-", lowered)
    collapsed = SEPARATOR_RE.sub("-", sanitized)
    return collapsed.strip("-")


def _normalize_relative_source(input_dir: Path, source: str) -> str | None:
    candidate = (input_dir / Path(source)).resolve()
    try:
        return candidate.relative_to(input_dir.resolve()).as_posix()
    except ValueError:
        return None


def _fail_report(
    template_id: str,
    input_kind: str,
    summary: dict[str, Any],
    issues: list[AdapterIssue],
    notes: list[str],
) -> AdapterReviewReport:
    return AdapterReviewReport(
        status=StepReviewStatus.FAIL,
        template_id=template_id,
        input_kind=input_kind,
        summary=summary,
        issues=issues,
        notes=notes,
    )


def _optional_string(metadata_entry: dict[str, Any] | None, key: str) -> str | None:
    if not metadata_entry:
        return None
    value = metadata_entry.get(key)
    return str(value) if value is not None else None
