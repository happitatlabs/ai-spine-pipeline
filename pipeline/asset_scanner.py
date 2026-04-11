from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from pipeline.step2_contracts import ScannedAsset, TraceEntry


TOKEN_BREAK_RE = re.compile(r"[^A-Za-z0-9]+")
CAMEL_BREAK_RE = re.compile(r"([a-z0-9])([A-Z])")
ALPHA_FALLBACK_BBOX = (0, 0, 0, 0)


def scan_assets(input_dir: str | Path) -> list[ScannedAsset]:
    root = Path(input_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"input_dir not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"input_dir is not a directory: {root}")

    assets: list[ScannedAsset] = []
    for path in sorted(root.rglob("*.png"), key=lambda item: item.relative_to(root).as_posix().lower()):
        relative_path = path.relative_to(root).as_posix()
        tokens, trace = tokenize_relative_path(relative_path)
        width, height, alpha_bbox = inspect_png(path)
        assets.append(
            ScannedAsset(
                source_path=path,
                relative_path=relative_path,
                file_stem=path.stem.lower(),
                tokens=tokens,
                image_size=(width, height),
                alpha_bbox=alpha_bbox,
                trace=trace,
            )
        )
    return assets


def tokenize_relative_path(relative_path: str) -> tuple[list[str], list[TraceEntry]]:
    trace: list[TraceEntry] = []
    collected: list[str] = []
    seen: set[str] = set()

    path = Path(relative_path)
    components = [part for part in path.parts[:-1]]
    components.append(path.stem)

    for component in components:
        normalized_component = CAMEL_BREAK_RE.sub(r"\1 \2", component).lower()
        chunks = [chunk for chunk in TOKEN_BREAK_RE.split(normalized_component) if chunk]
        split_tokens: list[str] = []
        for chunk in chunks:
            split_tokens.extend(_split_alnum_boundaries(chunk))
        deduped_chunk_tokens: list[str] = []
        for token in split_tokens:
            if token not in seen:
                collected.append(token)
                deduped_chunk_tokens.append(token)
                seen.add(token)
        trace.append(
            TraceEntry(
                type="tokenized",
                value=component,
                target="path_component",
                result=deduped_chunk_tokens,
            )
        )
    return collected, trace


def inspect_png(path: str | Path) -> tuple[int, int, tuple[int, int, int, int]]:
    image_path = Path(path)
    with Image.open(image_path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is None:
            return width, height, (0, 0, width, height)
        left, top, right, bottom = bbox
        return width, height, (left, top, right - left, bottom - top)


def _split_alnum_boundaries(chunk: str) -> list[str]:
    if not chunk:
        return []
    pieces = re.split(r"(?<=\D)(?=\d)|(?<=\d)(?=\D)", chunk)
    return [piece for piece in pieces if piece]
