from pathlib import Path

from pipeline.step1 import (
    build_bundle,
    load_json,
    load_parts_manifest,
    load_template,
    map_parts,
    run_step1,
)


class FakeCli:
    def export_skeleton_data(self, *, input_path, output_path, export_mode="json+pack"):
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "draft_skeleton.json").write_text("{}", encoding="utf-8")
        (output_dir / "draft_skeleton.atlas").write_text("atlas", encoding="utf-8")
        (output_dir / "draft_skeleton.png").write_bytes(b"png")
        return _FakeResult(["export"], 0, "ok", "")

    def import_skeleton_data(self, *, input_path, project_path, skeleton_name):
        project = Path(project_path)
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_text("project", encoding="utf-8")
        return _FakeResult(["import"], 0, "ok", "")

    def clean_project(self, project_path):
        return _FakeResult(["clean"], 0, "ok", "")

    def export_project(self, *, input_path, output_path, export_mode="json+pack"):
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "secondary.json").write_text("{}", encoding="utf-8")
        (output_dir / "secondary.atlas").write_text("atlas", encoding="utf-8")
        (output_dir / "secondary.png").write_bytes(b"png")
        return _FakeResult(["export_project"], 0, "ok", "")


class _FakeResult:
    def __init__(self, command, exit_code, stdout, stderr):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self):
        return self.exit_code == 0


def test_map_parts_prefers_anchor_hint() -> None:
    manifest = load_parts_manifest(Path("D:/Spine/samples/parts/humanoid_a/parts_manifest.json"))
    template = load_template("humanoid_v1")

    result = map_parts(manifest, template)
    lookup = {entry.part_id: entry for entry in result.entries}

    assert lookup["arm_l"].slot_name == "arm_l"
    assert lookup["arm_l"].anchor_mode == "anchor_hint"
    assert result.unresolved_parts == []
    assert result.missing_required_slots == []


def test_map_parts_uses_category_side_fallback() -> None:
    manifest = load_parts_manifest(Path("D:/Spine/samples/parts/humanoid_b/parts_manifest.json"))
    template = load_template("humanoid_v1")

    result = map_parts(manifest, template)
    lookup = {entry.part_id: entry for entry in result.entries}

    assert lookup["arm_l"].slot_name == "arm_l"
    assert lookup["arm_l"].anchor_mode == "category_side_fallback"
    assert lookup["leg_r"].slot_name == "leg_r"
    assert result.unresolved_parts == []


def test_build_bundle_creates_minimum_structure(tmp_path) -> None:
    manifest = load_parts_manifest(Path("D:/Spine/samples/parts/humanoid_a/parts_manifest.json"))
    template = load_template("humanoid_v1")
    mapping = map_parts(manifest, template)

    bundle = build_bundle(manifest, template, mapping, tmp_path / "bundle")
    draft = load_json(bundle.draft_skeleton_path)

    assert set(draft.keys()) >= {"bones", "slots", "skins"}
    assert (bundle.images_dir / "head.png").exists()
    skin_attachments = draft["skins"][0]["attachments"]
    assert skin_attachments["body"]["body"]["path"] == "body"


def test_run_step1_writes_pass_report(tmp_path, monkeypatch) -> None:
    import pipeline.step1 as step1

    monkeypatch.setattr(step1, "SpineCliAdapter", lambda spine_path: FakeCli())

    result = run_step1(
        parts_manifest_path=Path("D:/Spine/samples/parts/humanoid_c/parts_manifest.json"),
        template_id="humanoid_v1",
        bundle_dir=tmp_path / "bundle",
        roundtrip_dir=tmp_path / "roundtrip",
        run_secondary_roundtrip=True,
        secondary_project_path=tmp_path / "roundtrip" / "generated.spine",
        skip_roundtrip=False,
    )

    report = load_json(result["review_report"])
    assert result["status"] == "PASS"
    assert report["status"] == "PASS"
    assert "primary" in report["roundtrip"]
    assert "secondary" in report["roundtrip"]
