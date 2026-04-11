from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeline.status import StepReviewStatus


@dataclass(frozen=True)
class AdapterTraceEntry:
    type: str
    value: Any
    target: str
    result: Any = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "type": self.type,
            "value": self.value,
            "target": self.target,
        }
        if self.result is not None:
            payload["result"] = self.result
        return payload


@dataclass
class PreparedAsset:
    source_path: str
    prepared_path: str
    original_name: str
    prepared_name: str
    review_needed: bool
    trace: list[AdapterTraceEntry] = field(default_factory=list)
    category_hint: str | None = None
    side_hint: str | None = None
    variant_hint: str | None = None
    notes: list[str] | None = None

    def validate(self) -> None:
        required_fields = {
            "source_path": self.source_path,
            "prepared_path": self.prepared_path,
            "original_name": self.original_name,
            "prepared_name": self.prepared_name,
        }
        for field_name, value in required_fields.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"adapter_manifest required field {field_name} is missing")
        if not isinstance(self.review_needed, bool):
            raise ValueError("adapter_manifest required field review_needed is missing")
        if not isinstance(self.trace, list):
            raise ValueError("adapter_manifest required field trace is missing")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "source_path": self.source_path,
            "prepared_path": self.prepared_path,
            "original_name": self.original_name,
            "prepared_name": self.prepared_name,
            "review_needed": self.review_needed,
            "trace": [entry.to_dict() for entry in self.trace],
        }
        if self.category_hint is not None:
            payload["category_hint"] = self.category_hint
        if self.side_hint is not None:
            payload["side_hint"] = self.side_hint
        if self.variant_hint is not None:
            payload["variant_hint"] = self.variant_hint
        if self.notes:
            payload["notes"] = list(self.notes)
        return payload


@dataclass(frozen=True)
class AdapterIssue:
    type: str
    severity: str
    item: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "item": self.item,
            "message": self.message,
        }


@dataclass
class AdapterReviewReport:
    status: StepReviewStatus
    template_id: str
    input_kind: str
    summary: dict[str, Any]
    issues: list[AdapterIssue]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "template_id": self.template_id,
            "input_kind": self.input_kind,
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
            "notes": list(self.notes),
        }
