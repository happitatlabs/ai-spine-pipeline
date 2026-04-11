from __future__ import annotations

from collections import defaultdict

from pipeline.normalizer import STRONG_TOKEN_CONFIDENCE
from pipeline.step2_contracts import NormalizedAsset, ReviewIssue, ReviewReport, Step2Rules


def build_review_report(normalized_assets: list[NormalizedAsset], rules: Step2Rules) -> ReviewReport:
    selected_assets = [asset for asset in normalized_assets if asset.selected and asset.normalized_name]
    unresolved_assets = [asset for asset in normalized_assets if asset.normalized_name is None]
    low_confidence_assets = [
        asset
        for asset in selected_assets
        if asset.confidence < STRONG_TOKEN_CONFIDENCE
    ]

    duplicate_groups: dict[str, list[str]] = {}
    grouped: dict[str, list[NormalizedAsset]] = defaultdict(list)
    for asset in normalized_assets:
        if asset.normalized_name:
            grouped[asset.normalized_name].append(asset)
    for normalized_name, assets in grouped.items():
        if len(assets) > 1:
            duplicate_groups[normalized_name] = sorted(asset.relative_path for asset in assets)

    selected_names = {asset.normalized_name for asset in selected_assets if asset.normalized_name}
    missing_required_parts = sorted(
        canonical_name
        for canonical_name in rules.required_canonical_parts
        if canonical_name not in selected_names
    )

    issues: list[ReviewIssue] = []
    notes: list[str] = []

    for asset in low_confidence_assets:
        message = f"{asset.normalized_name} inferred via fallback only -> verify side/category"
        issues.append(
            ReviewIssue(
                type="low_confidence",
                severity="warning",
                part=asset.normalized_name or asset.relative_path,
                message=message,
            )
        )
        notes.append(message)

    for asset in unresolved_assets:
        message = f"{asset.relative_path} had no canonical match -> classify or remove"
        issues.append(
            ReviewIssue(
                type="unresolved",
                severity="warning",
                part=asset.relative_path,
                message=message,
            )
        )
        notes.append(message)

    for normalized_name, assets in duplicate_groups.items():
        label = " vs ".join(assets)
        message = f"duplicate {normalized_name} candidates -> check {label}"
        issues.append(
            ReviewIssue(
                type="duplicate",
                severity="warning",
                part=normalized_name,
                message=message,
            )
        )
        notes.append(message)

    for canonical_name in missing_required_parts:
        message = f"required canonical part {canonical_name} was not resolved"
        issues.append(
            ReviewIssue(
                type="missing_required",
                severity="error",
                part=canonical_name,
                message=message,
            )
        )
        notes.append(message)

    if missing_required_parts:
        status = "FAIL"
    elif issues:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"

    return ReviewReport(
        status=status,
        template_id=rules.template_id,
        summary={
            "total_assets": len(normalized_assets),
            "selected_parts": len(selected_assets),
            "low_confidence_count": len(low_confidence_assets),
            "unresolved_count": len(unresolved_assets),
            "duplicate_count": len(duplicate_groups),
            "missing_required_count": len(missing_required_parts),
        },
        issues=issues,
        low_confidence_parts=sorted(asset.normalized_name for asset in low_confidence_assets if asset.normalized_name),
        unresolved_parts=sorted(asset.relative_path for asset in unresolved_assets),
        duplicate_groups=duplicate_groups,
        missing_required_parts=missing_required_parts,
        notes=notes,
    )
