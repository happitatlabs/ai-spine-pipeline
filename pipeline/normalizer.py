from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from pipeline.step1 import load_template, load_yaml
from pipeline.step2_contracts import (
    CanonicalPartRule,
    NormalizedAsset,
    ScannedAsset,
    Step2Rules,
    TokenRule,
    TraceEntry,
)


DIRECT_MATCH_CONFIDENCE = 1.0
STRONG_TOKEN_CONFIDENCE = 0.8
FALLBACK_CONFIDENCE = 0.6
UNRESOLVED_CONFIDENCE = 0.0

CATEGORY_PIVOT_DEFAULTS = {
    "head": (0.5, 0.15),
    "body": (0.5, 0.5),
    "arm": (0.5, 0.2),
    "leg": (0.5, 0.1),
}


def load_step2_rules(template_id: str) -> Step2Rules:
    template = load_template(template_id)
    raw = load_yaml(template.template_root / "bone_template.yaml")
    section = raw.get("step2_normalization")
    if not isinstance(section, dict):
        raise ValueError(f"template {template_id} is missing step2_normalization")

    canonical_parts = {
        name: CanonicalPartRule(
            category=str(value["category"]).lower(),
            side=str(value["side"]).upper() if value.get("side") else None,
            anchor_hint=str(value["anchor_hint"]),
            z_order_hint=int(value.get("z_order_hint", 0)),
            symmetry_group=str(value["symmetry_group"]) if value.get("symmetry_group") else None,
        )
        for name, value in section.get("canonical_parts", {}).items()
    }
    return Step2Rules(
        template_id=template_id,
        required_canonical_parts=tuple(str(item) for item in section.get("required_canonical_parts", [])),
        canonical_parts=canonical_parts,
        category_tokens=_load_token_rules(section.get("category_tokens", {})),
        side_tokens=_load_token_rules(section.get("side_tokens", {})),
        variant_tokens=_load_token_rules(section.get("variant_tokens", {})),
        pivot_defaults={
            str(key): _coerce_pair(value)
            for key, value in section.get("pivot_defaults", {}).items()
        },
    )


def normalize_assets(assets: list[ScannedAsset], rules: Step2Rules) -> list[NormalizedAsset]:
    candidates = [_normalize_asset(asset, rules) for asset in assets]
    grouped: dict[str | None, list[NormalizedAsset]] = defaultdict(list)
    for asset in candidates:
        grouped[asset.normalized_name].append(asset)

    resolved_assets: list[NormalizedAsset] = []
    for normalized_name, group in grouped.items():
        if normalized_name is None:
            for item in group:
                resolved_assets.append(_replace_asset(item, selected=False, reject_reason="unresolved"))
            continue

        ordered_group = sorted(
            group,
            key=lambda item: (
                -item.confidence,
                -item.bbox_area,
                item.relative_path.lower(),
            ),
        )
        winner = ordered_group[0]
        resolved_assets.append(_replace_asset(winner, selected=True, reject_reason=None))
        for duplicate in ordered_group[1:]:
            resolved_assets.append(_replace_asset(duplicate, selected=False, reject_reason=f"duplicate:{normalized_name}"))

    return sorted(
        resolved_assets,
        key=lambda item: (
            item.normalized_name or "~",
            0 if item.selected else 1,
            item.relative_path.lower(),
        ),
    )


def build_step1_manifest(normalized_assets: list[NormalizedAsset], rules: Step2Rules) -> dict[str, Any]:
    selected = [asset for asset in normalized_assets if asset.selected and asset.normalized_name]
    ordered = sorted(selected, key=lambda item: (item.normalized_name or "", item.relative_path.lower()))
    parts = []
    for asset in ordered:
        rule = rules.canonical_parts[asset.normalized_name]
        parts.append(
            {
                "part_id": asset.normalized_name,
                "category": asset.category or rule.category,
                "side": rule.side,
                "file_path": f"normalized_assets/selected/{asset.normalized_name}.png",
                "bbox": list(asset.bbox),
                "pivot_hint": list(asset.pivot_hint),
                "anchor_hint": rule.anchor_hint,
                "anchor_offset": [0.0, 0.0],
                "rotation_hint": 0.0,
                "z_order_hint": rule.z_order_hint,
                "symmetry_group": rule.symmetry_group,
                "human_verified": False,
            }
        )
    return {
        "manifest_version": 1,
        "template_hint": rules.template_id,
        "parts": parts,
    }


def _normalize_asset(asset: ScannedAsset, rules: Step2Rules) -> NormalizedAsset:
    if asset.file_stem in rules.canonical_parts:
        canonical_name = asset.file_stem
        canonical_rule = rules.canonical_parts[canonical_name]
        trace = list(asset.trace)
        trace.append(
            TraceEntry(
                type="direct_match",
                value=asset.file_stem,
                target="normalized_name",
                result=canonical_name,
                score=DIRECT_MATCH_CONFIDENCE,
            )
        )
        pivot_hint, pivot_trace = _resolve_pivot(
            category=canonical_rule.category,
            bbox=asset.alpha_bbox,
            image_size=asset.image_size,
            rules=rules,
        )
        trace.append(pivot_trace)
        return NormalizedAsset(
            source_path=asset.source_path,
            relative_path=asset.relative_path,
            normalized_name=canonical_name,
            category=canonical_rule.category,
            side=canonical_rule.side,
            variant=None,
            anchor_hint=canonical_rule.anchor_hint,
            bbox=asset.alpha_bbox,
            pivot_hint=pivot_hint,
            confidence=DIRECT_MATCH_CONFIDENCE,
            selected=False,
            trace=trace,
        )

    category, category_mode, category_trace = _pick_scored_candidate(asset.tokens, rules.category_tokens, "category")
    side, side_mode, side_trace = _pick_scored_candidate(asset.tokens, rules.side_tokens, "side")
    variant, _, variant_trace = _pick_scored_candidate(asset.tokens, rules.variant_tokens, "variant")

    trace = list(asset.trace)
    trace.extend(category_trace)
    trace.extend(side_trace)
    trace.extend(variant_trace)

    normalized_name = _resolve_canonical_name(category=category, side=side)
    if normalized_name is None or normalized_name not in rules.canonical_parts:
        trace.append(
            TraceEntry(
                type="decision",
                value=asset.file_stem,
                target="normalized_name",
                result=None,
                score=UNRESOLVED_CONFIDENCE,
            )
        )
        pivot_hint, pivot_trace = _resolve_pivot(
            category=category,
            bbox=asset.alpha_bbox,
            image_size=asset.image_size,
            rules=rules,
        )
        trace.append(pivot_trace)
        return NormalizedAsset(
            source_path=asset.source_path,
            relative_path=asset.relative_path,
            normalized_name=None,
            category=category,
            side=side,
            variant=variant,
            anchor_hint=None,
            bbox=asset.alpha_bbox,
            pivot_hint=pivot_hint,
            confidence=UNRESOLVED_CONFIDENCE,
            selected=False,
            trace=trace,
            reject_reason="unresolved",
        )

    canonical_rule = rules.canonical_parts[normalized_name]
    required_modes = [category_mode]
    if canonical_rule.side is not None:
        required_modes.append(side_mode)
    confidence = _confidence_from_modes(required_modes)
    trace.append(
        TraceEntry(
            type="decision",
            value=asset.file_stem,
            target="normalized_name",
            result=normalized_name,
            score=confidence,
        )
    )
    pivot_hint, pivot_trace = _resolve_pivot(
        category=canonical_rule.category,
        bbox=asset.alpha_bbox,
        image_size=asset.image_size,
        rules=rules,
    )
    trace.append(pivot_trace)
    return NormalizedAsset(
        source_path=asset.source_path,
        relative_path=asset.relative_path,
        normalized_name=normalized_name,
        category=canonical_rule.category,
        side=canonical_rule.side,
        variant=variant,
        anchor_hint=canonical_rule.anchor_hint,
        bbox=asset.alpha_bbox,
        pivot_hint=pivot_hint,
        confidence=confidence,
        selected=False,
        trace=trace,
    )


def _resolve_canonical_name(category: str | None, side: str | None) -> str | None:
    if category in {"head", "body"}:
        return category
    if category in {"arm", "leg"} and side in {"L", "R"}:
        return f"{category}_{side.lower()}"
    return None


def _pick_scored_candidate(
    tokens: list[str],
    rule_map: dict[str, TokenRule],
    target: str,
) -> tuple[str | None, str | None, list[TraceEntry]]:
    winner: str | None = None
    winner_mode: str | None = None
    winner_score = 0.0
    winner_trace: list[TraceEntry] = []

    for candidate in sorted(rule_map):
        rule = rule_map[candidate]
        candidate_score = 0.0
        has_strong = False
        has_fallback = False
        candidate_trace: list[TraceEntry] = []

        for token in tokens:
            if token in rule.strong:
                candidate_score += 1.0
                has_strong = True
                candidate_trace.append(
                    TraceEntry(
                        type="token_match",
                        value=token,
                        target=target,
                        result=candidate,
                        score=1.0,
                    )
                )
            elif token in rule.fallback:
                candidate_score += 0.6
                has_fallback = True
                candidate_trace.append(
                    TraceEntry(
                        type="alias_match",
                        value=token,
                        target=target,
                        result=candidate,
                        score=0.6,
                    )
                )

        if candidate_score <= 0:
            continue

        candidate_mode = "strong" if has_strong else "fallback" if has_fallback else None
        ordering = (
            candidate_score,
            1 if candidate_mode == "strong" else 0,
            candidate,
        )
        winner_ordering = (
            winner_score,
            1 if winner_mode == "strong" else 0,
            winner or "",
        )
        if winner is None or ordering > winner_ordering:
            winner = candidate
            winner_mode = candidate_mode
            winner_score = candidate_score
            winner_trace = candidate_trace

    return winner, winner_mode, winner_trace


def _confidence_from_modes(modes: list[str | None]) -> float:
    filtered = [mode for mode in modes if mode]
    if not filtered:
        return UNRESOLVED_CONFIDENCE
    if all(mode == "strong" for mode in filtered):
        return STRONG_TOKEN_CONFIDENCE
    return FALLBACK_CONFIDENCE


def _resolve_pivot(
    *,
    category: str | None,
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    rules: Step2Rules,
) -> tuple[tuple[float, float], TraceEntry]:
    if category and category in rules.pivot_defaults:
        pivot = rules.pivot_defaults[category]
        return pivot, TraceEntry(
            type="pivot_default",
            value=category,
            target="pivot",
            result=list(pivot),
            score=1.0,
        )
    if category and category in CATEGORY_PIVOT_DEFAULTS:
        pivot = CATEGORY_PIVOT_DEFAULTS[category]
        return pivot, TraceEntry(
            type="pivot_category_rule",
            value=category,
            target="pivot",
            result=list(pivot),
            score=0.8,
        )
    x, y, width, height = bbox
    image_width = max(image_size[0], 1)
    image_height = max(image_size[1], 1)
    pivot = (
        round((x + (width / 2.0)) / image_width, 4),
        round(y / image_height, 4),
    )
    return pivot, TraceEntry(
        type="pivot_bbox_fallback",
        value=list(bbox),
        target="pivot",
        result=list(pivot),
        score=0.6,
    )


def _replace_asset(asset: NormalizedAsset, *, selected: bool, reject_reason: str | None) -> NormalizedAsset:
    return NormalizedAsset(
        source_path=asset.source_path,
        relative_path=asset.relative_path,
        normalized_name=asset.normalized_name,
        category=asset.category,
        side=asset.side,
        variant=asset.variant,
        anchor_hint=asset.anchor_hint,
        bbox=asset.bbox,
        pivot_hint=asset.pivot_hint,
        confidence=asset.confidence,
        selected=selected,
        trace=list(asset.trace),
        reject_reason=reject_reason,
    )


def _load_token_rules(raw: dict[str, Any]) -> dict[str, TokenRule]:
    return {
        str(name): TokenRule(
            strong=tuple(str(item).lower() for item in value.get("strong", [])),
            fallback=tuple(str(item).lower() for item in value.get("fallback", [])),
        )
        for name, value in raw.items()
    }


def _coerce_pair(value: Any) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"pivot default must be a 2-item list, got: {value!r}")
    return (float(value[0]), float(value[1]))
