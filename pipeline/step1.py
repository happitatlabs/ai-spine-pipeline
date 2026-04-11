from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from time import perf_counter
from typing import Any

import yaml

from pipeline.status import StepStatus, render_status


DEFAULT_SPINE_PATH = r"C:\Program Files\Spine\Spine.com"
UNRESOLVED_RATIO_LIMIT = 0.10


def load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    return json.loads(json_path.read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_yaml(path: str | Path) -> dict[str, Any]:
    yaml_path = Path(path)
    return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))


def _coerce_bbox(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"bbox must be a 4-item list, got: {value!r}")
    return tuple(int(item) for item in value)


def _coerce_pair(value: Any, field_name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field_name} must be a 2-item list, got: {value!r}")
    return (float(value[0]), float(value[1]))


def _normalize_side(value: Any) -> str | None:
    if value in (None, "", "NONE"):
        return None
    return str(value).upper()


@dataclass(frozen=True)
class PartSpec:
    part_id: str
    category: str
    side: str | None
    file_path: str
    bbox: tuple[int, int, int, int]
    pivot_hint: tuple[float, float]
    anchor_hint: str | None = None
    anchor_offset: tuple[float, float] = (0.0, 0.0)
    rotation_hint: float = 0.0
    z_order_hint: int = 0
    symmetry_group: str | None = None
    human_verified: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PartSpec":
        required = {"part_id", "category", "file_path", "bbox", "pivot_hint"}
        missing = sorted(required.difference(data))
        if missing:
            raise ValueError(f"part entry is missing required fields: {missing}")
        return cls(
            part_id=str(data["part_id"]),
            category=str(data["category"]).lower(),
            side=_normalize_side(data.get("side")),
            file_path=str(data["file_path"]),
            bbox=_coerce_bbox(data["bbox"]),
            pivot_hint=_coerce_pair(data["pivot_hint"], "pivot_hint"),
            anchor_hint=str(data["anchor_hint"]) if data.get("anchor_hint") else None,
            anchor_offset=_coerce_pair(data.get("anchor_offset", (0.0, 0.0)), "anchor_offset"),
            rotation_hint=float(data.get("rotation_hint", 0.0)),
            z_order_hint=int(data.get("z_order_hint", 0)),
            symmetry_group=str(data["symmetry_group"]) if data.get("symmetry_group") else None,
            human_verified=bool(data.get("human_verified", False)),
        )

    @property
    def width(self) -> int:
        return int(self.bbox[2])

    @property
    def height(self) -> int:
        return int(self.bbox[3])

    def resolve_source(self, manifest_dir: Path) -> Path:
        path = Path(self.file_path)
        if path.is_absolute():
            return path
        return (manifest_dir / path).resolve()


@dataclass
class PartsManifest:
    manifest_version: int
    template_hint: str | None
    parts: list[PartSpec]
    source_path: Path

    @property
    def manifest_dir(self) -> Path:
        return self.source_path.parent

    def part_by_id(self, part_id: str) -> PartSpec:
        for part in self.parts:
            if part.part_id == part_id:
                return part
        raise KeyError(f"Unknown part_id: {part_id}")


def load_parts_manifest(path: str | Path) -> PartsManifest:
    manifest_path = Path(path).resolve()
    raw = load_json(manifest_path)
    parts = [PartSpec.from_dict(item) for item in raw.get("parts", [])]
    if not parts:
        raise ValueError(f"parts manifest has no parts: {manifest_path}")
    return PartsManifest(
        manifest_version=int(raw.get("manifest_version", 1)),
        template_hint=raw.get("template_hint"),
        parts=parts,
        source_path=manifest_path,
    )


@dataclass(frozen=True)
class TemplateSlot:
    name: str
    bone: str
    default_attachment: str
    required: bool = True


@dataclass(frozen=True)
class FallbackRule:
    category: str
    slot: str
    side: str | None = None


@dataclass(frozen=True)
class TemplateSpec:
    template_id: str
    description: str
    spine_version: str
    skeleton_name: str
    template_root: Path
    base_template_json_path: Path
    base_skeleton: dict[str, Any]
    required_parts: list[str]
    anchor_slot_map: dict[str, str]
    fallback_rules: list[FallbackRule]
    slots: dict[str, TemplateSlot]

    @property
    def required_slot_names(self) -> list[str]:
        return [slot.name for slot in self.slots.values() if slot.required]


def load_template(template_id: str) -> TemplateSpec:
    template_root = Path(__file__).resolve().parent.parent / "spine" / "templates" / template_id
    template_yaml = template_root / "bone_template.yaml"
    if not template_yaml.exists():
        raise FileNotFoundError(f"Unknown template: {template_id}")

    raw = load_yaml(template_yaml)
    base_template_json_path = template_root / raw["base_template_json"]
    slots = {
        name: TemplateSlot(
            name=name,
            bone=str(value["bone"]),
            default_attachment=str(value.get("default_attachment", name)),
            required=bool(value.get("required", True)),
        )
        for name, value in raw["slots"].items()
    }
    fallback_rules = [
        FallbackRule(
            category=str(rule["category"]).lower(),
            slot=str(rule["slot"]),
            side=str(rule["side"]).upper() if rule.get("side") else None,
        )
        for rule in raw.get("fallback_rules", [])
    ]
    return TemplateSpec(
        template_id=str(raw["template_id"]),
        description=str(raw.get("description", "")),
        spine_version=str(raw.get("spine_version", "")),
        skeleton_name=str(raw.get("skeleton_name", raw["template_id"])),
        template_root=template_root,
        base_template_json_path=base_template_json_path,
        base_skeleton=load_json(base_template_json_path),
        required_parts=[str(item) for item in raw.get("required_parts", [])],
        anchor_slot_map={str(key): str(value) for key, value in raw.get("anchor_slot_map", {}).items()},
        fallback_rules=fallback_rules,
        slots=slots,
    )


@dataclass
class MappingEntry:
    part_id: str
    slot_name: str | None
    bone_name: str | None
    anchor_mode: str
    confidence: float
    status: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "slot_name": self.slot_name,
            "bone_name": self.bone_name,
            "anchor_mode": self.anchor_mode,
            "confidence": round(self.confidence, 4),
            "status": self.status,
            "notes": list(self.notes),
        }


@dataclass
class MappingResult:
    template_id: str
    entries: list[MappingEntry]
    unresolved_parts: list[str]
    missing_required_slots: list[str]
    mapping_confidence_avg: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "unresolved_parts": list(self.unresolved_parts),
            "missing_required_slots": list(self.missing_required_slots),
            "mapping_confidence_avg": round(self.mapping_confidence_avg, 4),
        }


def map_parts(manifest: PartsManifest, template: TemplateSpec) -> MappingResult:
    entries: list[MappingEntry] = []
    claimed_slots: dict[str, MappingEntry] = {}

    for part in manifest.parts:
        entry = _resolve_part(part, template)
        if entry.slot_name and entry.status == "resolved":
            existing = claimed_slots.get(entry.slot_name)
            if existing is None:
                claimed_slots[entry.slot_name] = entry
            elif existing.confidence < entry.confidence:
                existing.notes.append(f"slot {entry.slot_name} reassigned to higher confidence mapping")
                existing.slot_name = None
                existing.bone_name = None
                existing.anchor_mode = "collision"
                existing.status = "unresolved"
                existing.confidence = 0.0
                claimed_slots[entry.slot_name] = entry
            else:
                entry.notes.append(f"slot {entry.slot_name} already claimed by {existing.part_id}")
                entry.slot_name = None
                entry.bone_name = None
                entry.anchor_mode = "collision"
                entry.status = "unresolved"
                entry.confidence = 0.0
        entries.append(entry)

    unresolved_parts = sorted(entry.part_id for entry in entries if entry.status != "resolved")
    mapped_slots = {entry.slot_name for entry in entries if entry.status == "resolved" and entry.slot_name}
    missing_required_slots = sorted(slot for slot in template.required_slot_names if slot not in mapped_slots)
    average = sum(entry.confidence for entry in entries) / max(len(entries), 1)
    return MappingResult(
        template_id=template.template_id,
        entries=entries,
        unresolved_parts=unresolved_parts,
        missing_required_slots=missing_required_slots,
        mapping_confidence_avg=round(average, 4),
    )


def _resolve_part(part: PartSpec, template: TemplateSpec) -> MappingEntry:
    notes: list[str] = []
    if part.anchor_hint:
        slot_name = template.anchor_slot_map.get(part.anchor_hint)
        if slot_name:
            slot = template.slots[slot_name]
            return MappingEntry(
                part_id=part.part_id,
                slot_name=slot_name,
                bone_name=slot.bone,
                anchor_mode="anchor_hint",
                confidence=1.0,
                status="resolved",
                notes=notes,
            )
        notes.append(f"unknown anchor_hint:{part.anchor_hint}")

    for rule in template.fallback_rules:
        if rule.category != part.category:
            continue
        if rule.side is None or rule.side == part.side:
            slot = template.slots[rule.slot]
            return MappingEntry(
                part_id=part.part_id,
                slot_name=rule.slot,
                bone_name=slot.bone,
                anchor_mode="category_side_fallback",
                confidence=0.75,
                status="resolved",
                notes=notes,
            )

    notes.append("no anchor_hint or fallback rule matched")
    return MappingEntry(
        part_id=part.part_id,
        slot_name=None,
        bone_name=None,
        anchor_mode="unresolved",
        confidence=0.0,
        status="unresolved",
        notes=notes,
    )


def _extract_skin_attachments(skeleton: dict[str, Any]) -> tuple[Any, dict[str, Any], bool]:
    skins = skeleton.get("skins", {})
    if isinstance(skins, list):
        if not skins:
            raise ValueError("template JSON must include at least one skin")
        skin_entry = skins[0]
        attachments = skin_entry.setdefault("attachments", {})
        return skins, attachments, True
    if isinstance(skins, dict):
        default_skin = skins.setdefault("default", {})
        return skins, default_skin, False
    raise ValueError("template JSON has unsupported skins format")


def build_draft_skeleton(
    manifest: PartsManifest,
    template: TemplateSpec,
    mapping: MappingResult,
) -> dict[str, Any]:
    draft = deepcopy(template.base_skeleton)
    draft.pop("animations", None)
    draft.pop("events", None)
    draft.setdefault("skeleton", {})
    draft["skeleton"]["images"] = "./images/"

    slots_by_name = {slot["name"]: slot for slot in draft.get("slots", [])}
    skins, base_attachments, uses_skin_list = _extract_skin_attachments(draft)
    updated_attachments: dict[str, Any] = {}

    for entry in mapping.entries:
        if entry.status != "resolved" or not entry.slot_name:
            continue
        part = manifest.part_by_id(entry.part_id)
        slot_spec = template.slots[entry.slot_name]
        base_attachment = _find_base_attachment(base_attachments, entry.slot_name, slot_spec.default_attachment)
        updated_attachments[entry.slot_name] = {
            part.part_id: {
                **deepcopy(base_attachment),
                "type": "region",
                "path": part.part_id,
                "x": round(float(base_attachment.get("x", 0.0)) + part.anchor_offset[0], 2),
                "y": round(float(base_attachment.get("y", 0.0)) + part.anchor_offset[1], 2),
                "rotation": round(float(base_attachment.get("rotation", 0.0)) + part.rotation_hint, 2),
                "width": part.width,
                "height": part.height,
            }
        }
        slots_by_name[entry.slot_name]["attachment"] = part.part_id

    for slot_name, slot in slots_by_name.items():
        if slot_name not in updated_attachments:
            slot.pop("attachment", None)

    if uses_skin_list:
        skins[0]["attachments"] = updated_attachments
        draft["skins"] = skins
    else:
        skins["default"] = updated_attachments
        draft["skins"] = skins

    return draft


def _find_base_attachment(
    base_attachments: dict[str, Any],
    slot_name: str,
    default_attachment_name: str,
) -> dict[str, Any]:
    slot_attachments = base_attachments.get(slot_name, {})
    if default_attachment_name in slot_attachments:
        return slot_attachments[default_attachment_name]
    if slot_attachments:
        return next(iter(slot_attachments.values()))
    return {}


@dataclass
class BundleArtifacts:
    bundle_dir: Path
    images_dir: Path
    draft_skeleton_path: Path
    bundle_meta_path: Path
    slot_map_path: Path
    review_report_path: Path


def build_bundle(
    manifest: PartsManifest,
    template: TemplateSpec,
    mapping: MappingResult,
    output_dir: str | Path,
) -> BundleArtifacts:
    bundle_dir = Path(output_dir)
    if bundle_dir.exists():
        raise FileExistsError(f"Bundle directory already exists: {bundle_dir}")

    images_dir = bundle_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=False)

    for part in manifest.parts:
        source = part.resolve_source(manifest.manifest_dir)
        if not source.exists():
            raise FileNotFoundError(f"Part image not found: {source}")
        if source.suffix.lower() != ".png":
            raise ValueError(f"STEP 1 only supports PNG parts: {source}")
        shutil.copy2(source, images_dir / f"{part.part_id}.png")

    draft_skeleton_path = bundle_dir / "draft_skeleton.json"
    bundle_meta_path = bundle_dir / "bundle_meta.json"
    slot_map_path = bundle_dir / "slot_map.json"
    review_report_path = bundle_dir / "review_report.json"

    draft_skeleton = build_draft_skeleton(manifest=manifest, template=template, mapping=mapping)
    write_json(draft_skeleton_path, draft_skeleton)
    write_json(
        bundle_meta_path,
        {
            "template_id": template.template_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parts_count": len(manifest.parts),
            "unresolved_parts": mapping.unresolved_parts,
            "mapping_confidence_avg": mapping.mapping_confidence_avg,
        },
    )
    write_json(slot_map_path, mapping.to_dict())

    return BundleArtifacts(
        bundle_dir=bundle_dir,
        images_dir=images_dir,
        draft_skeleton_path=draft_skeleton_path,
        bundle_meta_path=bundle_meta_path,
        slot_map_path=slot_map_path,
        review_report_path=review_report_path,
    )


@dataclass
class CliCommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SpineCliAdapter:
    def __init__(self, spine_path: str = DEFAULT_SPINE_PATH) -> None:
        self.spine_path = Path(spine_path)
        if not self.spine_path.exists():
            raise FileNotFoundError(f"Spine CLI not found: {self.spine_path}")

    def export_skeleton_data(
        self,
        *,
        input_path: str | Path,
        output_path: str | Path,
        export_mode: str = "json+pack",
    ) -> CliCommandResult:
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        return self._run([str(self.spine_path), "-i", str(input_path), "-o", str(output_dir), "-e", export_mode])

    def import_skeleton_data(
        self,
        *,
        input_path: str | Path,
        project_path: str | Path,
        skeleton_name: str,
    ) -> CliCommandResult:
        project = Path(project_path)
        project.parent.mkdir(parents=True, exist_ok=True)
        return self._run([str(self.spine_path), "-i", str(input_path), "-o", str(project), "-r", skeleton_name])

    def clean_project(self, project_path: str | Path) -> CliCommandResult:
        return self._run([str(self.spine_path), "-i", str(project_path), "-m"])

    def export_project(
        self,
        *,
        input_path: str | Path,
        output_path: str | Path,
        export_mode: str = "json+pack",
    ) -> CliCommandResult:
        return self.export_skeleton_data(input_path=input_path, output_path=output_path, export_mode=export_mode)

    @staticmethod
    def _run(command: list[str]) -> CliCommandResult:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return CliCommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass
class ReviewReport:
    status: StepStatus
    failure_type: str | None
    template_id: str
    parts_count: int
    unresolved_parts: list[str]
    missing_required_slots: list[str]
    mapping_confidence_avg: float
    notes: list[str] = field(default_factory=list)
    roundtrip: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_step1(
    manifest: PartsManifest,
    template: TemplateSpec,
    mapping: MappingResult,
    bundle: BundleArtifacts,
    cli: SpineCliAdapter | None = None,
    roundtrip_dir: str | Path | None = None,
    run_secondary_roundtrip: bool = False,
    secondary_project_path: str | Path | None = None,
) -> ReviewReport:
    draft = load_json(bundle.draft_skeleton_path)
    for key in ("bones", "slots", "skins"):
        if key not in draft:
            raise ValueError(f"draft_skeleton.json missing required top-level key: {key}")

    unresolved_ratio = len(mapping.unresolved_parts) / max(len(manifest.parts), 1)
    notes: list[str] = []
    if mapping.missing_required_slots or unresolved_ratio > UNRESOLVED_RATIO_LIMIT:
        if mapping.missing_required_slots:
            notes.append(f"missing required slots: {', '.join(mapping.missing_required_slots)}")
        if unresolved_ratio > UNRESOLVED_RATIO_LIMIT:
            notes.append(f"unresolved ratio {unresolved_ratio:.2%} exceeds 10%")
        report = ReviewReport(
            status=StepStatus.FAIL,
            failure_type="MAPPING_FAILURE",
            template_id=template.template_id,
            parts_count=len(manifest.parts),
            unresolved_parts=mapping.unresolved_parts,
            missing_required_slots=mapping.missing_required_slots,
            mapping_confidence_avg=mapping.mapping_confidence_avg,
            notes=notes,
        )
        write_json(bundle.review_report_path, report.to_dict())
        return report

    for part in manifest.parts:
        max_dimension = max(part.width, part.height, 1)
        if abs(part.anchor_offset[0]) > max_dimension or abs(part.anchor_offset[1]) > max_dimension:
            notes.append(f"potential layout risk on {part.part_id}: anchor_offset exceeds the part size envelope")
        if abs(part.rotation_hint) > 90:
            notes.append(f"potential layout risk on {part.part_id}: rotation_hint exceeds +/-90 degrees")
    if not notes:
        notes.append("visual layout review still required in STEP 1")

    report = ReviewReport(
        status=StepStatus.PASS,
        failure_type=None,
        template_id=template.template_id,
        parts_count=len(manifest.parts),
        unresolved_parts=mapping.unresolved_parts,
        missing_required_slots=mapping.missing_required_slots,
        mapping_confidence_avg=mapping.mapping_confidence_avg,
        notes=notes,
    )

    if cli and roundtrip_dir:
        roundtrip_root = Path(roundtrip_dir)
        primary_dir = roundtrip_root / "primary"
        primary = cli.export_skeleton_data(input_path=bundle.draft_skeleton_path, output_path=primary_dir, export_mode="json+pack")
        report.roundtrip["primary"] = _roundtrip_payload(primary, primary_dir)
        if not primary.ok or not _has_required_export_files(primary_dir):
            report.status = StepStatus.FAIL
            report.failure_type = "EXPORT_FAILURE"
            if _has_required_export_files(primary_dir) is False:
                report.notes.append("primary roundtrip did not produce .json, .atlas, and .png outputs")

        if report.status == StepStatus.PASS and run_secondary_roundtrip:
            project_path = Path(secondary_project_path or (roundtrip_root / "generated.spine"))
            imported = cli.import_skeleton_data(
                input_path=bundle.draft_skeleton_path,
                project_path=project_path,
                skeleton_name=template.skeleton_name,
            )
            secondary_payload = {"import": _cli_payload(imported)}
            if not imported.ok:
                report.status = StepStatus.FAIL
                report.failure_type = "IMPORT_FAILURE"
                report.roundtrip["secondary"] = secondary_payload
            else:
                cleaned = cli.clean_project(project_path)
                secondary_export_dir = roundtrip_root / "secondary_export"
                exported = cli.export_project(
                    input_path=project_path,
                    output_path=secondary_export_dir,
                    export_mode="json+pack",
                )
                secondary_payload["clean"] = _cli_payload(cleaned)
                secondary_payload["export"] = _roundtrip_payload(exported, secondary_export_dir)
                report.roundtrip["secondary"] = secondary_payload
                if not exported.ok or not _has_required_export_files(secondary_export_dir):
                    report.status = StepStatus.FAIL
                    report.failure_type = "EXPORT_FAILURE"

    write_json(bundle.review_report_path, report.to_dict())
    return report


def _has_required_export_files(output_dir: Path) -> bool:
    return bool(list(output_dir.rglob("*.json")) and list(output_dir.rglob("*.atlas")) and list(output_dir.rglob("*.png")))


def _cli_payload(result: CliCommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _roundtrip_payload(result: CliCommandResult, output_dir: Path) -> dict[str, Any]:
    payload = _cli_payload(result)
    payload["output_dir"] = str(output_dir)
    payload["produced_files"] = sorted(str(path) for path in output_dir.rglob("*") if path.is_file())
    return payload


def run_step1(
    *,
    parts_manifest_path: str | Path,
    template_id: str,
    bundle_dir: str | Path,
    roundtrip_dir: str | Path | None = None,
    run_secondary_roundtrip: bool = False,
    secondary_project_path: str | Path | None = None,
    spine_path: str = DEFAULT_SPINE_PATH,
    skip_roundtrip: bool = False,
) -> dict[str, Any]:
    started = perf_counter()
    manifest = load_parts_manifest(parts_manifest_path)
    template = load_template(template_id)
    mapping = map_parts(manifest, template)
    bundle = build_bundle(manifest, template, mapping, bundle_dir)
    cli = None if skip_roundtrip else SpineCliAdapter(spine_path)
    report = validate_step1(
        manifest=manifest,
        template=template,
        mapping=mapping,
        bundle=bundle,
        cli=cli,
        roundtrip_dir=roundtrip_dir,
        run_secondary_roundtrip=run_secondary_roundtrip,
        secondary_project_path=secondary_project_path,
    )
    report.timing["elapsed_seconds"] = round(perf_counter() - started, 3)
    write_json(bundle.review_report_path, report.to_dict())
    return {
        "status": report.status,
        "bundle_dir": str(bundle.bundle_dir),
        "review_report": str(bundle.review_report_path),
        "mapping_confidence_avg": report.mapping_confidence_avg,
        "unresolved_parts": report.unresolved_parts,
        "missing_required_slots": report.missing_required_slots,
        "roundtrip_dir": str(roundtrip_dir) if roundtrip_dir else None,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run STEP 1 of the AI-to-Spine pipeline.")
    parser.add_argument("--parts-manifest", required=True)
    parser.add_argument("--template-id", default="humanoid_v1")
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--roundtrip-dir")
    parser.add_argument("--run-secondary-roundtrip", action="store_true")
    parser.add_argument("--secondary-project-path")
    parser.add_argument("--spine-path", default=DEFAULT_SPINE_PATH)
    parser.add_argument("--skip-roundtrip", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _force_delete(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value)
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def main() -> int:
    args = _parse_args()
    if args.force:
        _force_delete(args.bundle_dir)
        _force_delete(args.roundtrip_dir)
        _force_delete(args.secondary_project_path)

    result = run_step1(
        parts_manifest_path=args.parts_manifest,
        template_id=args.template_id,
        bundle_dir=args.bundle_dir,
        roundtrip_dir=args.roundtrip_dir,
        run_secondary_roundtrip=args.run_secondary_roundtrip,
        secondary_project_path=args.secondary_project_path,
        spine_path=args.spine_path,
        skip_roundtrip=args.skip_roundtrip,
    )

    print(f"status={render_status(result['status'])}")
    print(f"bundle_dir={result['bundle_dir']}")
    print(f"review_report={result['review_report']}")
    print(f"mapping_confidence_avg={result['mapping_confidence_avg']}")
    if result["roundtrip_dir"]:
        print(f"roundtrip_dir={result['roundtrip_dir']}")
    if result["unresolved_parts"]:
        print(f"unresolved_parts={','.join(result['unresolved_parts'])}")
    if result["missing_required_slots"]:
        print(f"missing_required_slots={','.join(result['missing_required_slots'])}")
    return 0 if result["status"] == StepStatus.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
