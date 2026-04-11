from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TraceEntry:
    type: str
    value: Any
    target: str
    result: Any = None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "type": self.type,
            "value": self.value,
            "target": self.target,
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.score is not None:
            payload["score"] = round(float(self.score), 4)
        return payload


@dataclass(frozen=True)
class ScannedAsset:
    source_path: Path
    relative_path: str
    file_stem: str
    tokens: list[str]
    image_size: tuple[int, int]
    alpha_bbox: tuple[int, int, int, int]
    trace: list[TraceEntry] = field(default_factory=list)

    @property
    def bbox_area(self) -> int:
        return int(self.alpha_bbox[2]) * int(self.alpha_bbox[3])

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.relative_path,
            "relative_path": self.relative_path,
            "file_stem": self.file_stem,
            "tokens": list(self.tokens),
            "image_size": list(self.image_size),
            "alpha_bbox": list(self.alpha_bbox),
            "trace": [entry.to_dict() for entry in self.trace],
        }


@dataclass(frozen=True)
class CanonicalPartRule:
    category: str
    side: str | None
    anchor_hint: str
    z_order_hint: int
    symmetry_group: str | None


@dataclass(frozen=True)
class TokenRule:
    strong: tuple[str, ...] = ()
    fallback: tuple[str, ...] = ()


@dataclass(frozen=True)
class Step2Rules:
    template_id: str
    required_canonical_parts: tuple[str, ...]
    canonical_parts: dict[str, CanonicalPartRule]
    category_tokens: dict[str, TokenRule]
    side_tokens: dict[str, TokenRule]
    variant_tokens: dict[str, TokenRule]
    pivot_defaults: dict[str, tuple[float, float]]


@dataclass
class NormalizedAsset:
    source_path: Path
    relative_path: str
    normalized_name: str | None
    category: str | None
    side: str | None
    variant: str | None
    anchor_hint: str | None
    bbox: tuple[int, int, int, int]
    pivot_hint: tuple[float, float]
    confidence: float
    selected: bool
    trace: list[TraceEntry] = field(default_factory=list)
    reject_reason: str | None = None

    @property
    def bbox_area(self) -> int:
        return int(self.bbox[2]) * int(self.bbox[3])

    @property
    def source_name(self) -> str:
        return Path(self.relative_path).name

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.relative_path,
            "relative_path": self.relative_path,
            "normalized_name": self.normalized_name,
            "category": self.category,
            "side": self.side,
            "variant": self.variant,
            "anchor_hint": self.anchor_hint,
            "bbox": list(self.bbox),
            "pivot_hint": list(self.pivot_hint),
            "confidence": round(float(self.confidence), 4),
            "selected": self.selected,
            "reject_reason": self.reject_reason,
            "trace": [entry.to_dict() for entry in self.trace],
        }


@dataclass(frozen=True)
class ReviewIssue:
    type: str
    severity: str
    part: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewReport:
    status: str
    template_id: str
    summary: dict[str, Any]
    issues: list[ReviewIssue]
    low_confidence_parts: list[str]
    unresolved_parts: list[str]
    duplicate_groups: dict[str, list[str]]
    missing_required_parts: list[str]
    notes: list[str]
    step1_status: str = "NOT_RUN"
    step1_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "template_id": self.template_id,
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
            "low_confidence_parts": list(self.low_confidence_parts),
            "unresolved_parts": list(self.unresolved_parts),
            "duplicate_groups": {key: list(value) for key, value in self.duplicate_groups.items()},
            "missing_required_parts": list(self.missing_required_parts),
            "notes": list(self.notes),
            "step1_status": self.step1_status,
            "step1_error": self.step1_error,
        }
