#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an Illustrator-friendly SVG poster with linked clean background.")
    parser.add_argument("--full-poster", type=Path, required=True, help="Full poster image with baked-in text.")
    parser.add_argument("--clean-background", type=Path, required=True, help="Clean poster background without text.")
    parser.add_argument("--text-regions", type=Path, required=True, help="OCR/classified text region JSON.")
    parser.add_argument("--art-vectors", type=Path, help="Optional art text vector JSON from vectorize_art_text.py.")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/poster"), help="Output directory.")
    parser.add_argument("--title", default="Editable Poster", help="SVG title.")
    parser.add_argument("--target-size", help="Canvas size, e.g. A4, 1080x1920px, 210x297mm.")
    parser.add_argument("--font-family", default="", help="Override editable text font family.")
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitize_id(value: str, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    value = value.strip("-")
    return value or fallback


def fmt_num(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def parse_target_size(raw: str | None, width: int, height: int) -> tuple[str, str]:
    if not raw:
        return f"{width}px", f"{height}px"
    text = raw.strip().lower()
    if text == "a4":
        return ("297mm", "210mm") if width > height else ("210mm", "297mm")
    match = re.fullmatch(r"([0-9.]+)\s*x\s*([0-9.]+)\s*(px|mm|cm|in)?", text)
    if match:
        unit = match.group(3) or "px"
        return f"{match.group(1)}{unit}", f"{match.group(2)}{unit}"
    raise SystemExit(f"Unsupported --target-size: {raw}")


def normalize_background(full_poster: Path, clean_background: Path, out_dir: Path) -> tuple[int, int]:
    full = Image.open(full_poster).convert("RGB")
    clean = Image.open(clean_background).convert("RGB")
    width, height = full.size
    clean_ratio = clean.width / clean.height
    full_ratio = width / height
    if clean.size != full.size:
        if abs(clean_ratio - full_ratio) > 0.02:
            raise SystemExit("Full poster and clean background ratios differ by more than 2%; regenerate the clean background.")
        clean = clean.resize((width, height), Image.Resampling.LANCZOS)

    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    background = assets / "background.png"
    clean.save(background)
    return width, height


def load_regions(path: Path) -> list[dict]:
    data = read_json(path)
    regions = data if isinstance(data, list) else data.get("regions", [])
    if not isinstance(regions, list):
        raise SystemExit("Text region JSON must contain a 'regions' list.")
    return regions


def load_art_vectors(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        return {}
    data = read_json(path)
    items = data if isinstance(data, list) else data.get("art_regions", [])
    return {(item.get("id") or f"art-{index}"): item for index, item in enumerate(items, start=1)}


def choose_font(region: dict, override: str) -> str:
    if override:
        return override
    text = region.get("text", "")
    if re.search(r"[\u3400-\u9fff]", text):
        return "Microsoft YaHei, SimHei, Noto Sans CJK SC, Arial, sans-serif"
    return "Arial, Helvetica, sans-serif"


def editable_text_element(region: dict, index: int, font_override: str) -> str:
    bbox = region.get("bbox") or [0, 0, 0, 0]
    x1, y1, _x2, y2 = [float(v) for v in bbox]
    text = str(region.get("text", ""))
    font_size = float(region.get("font_size") or max(8.0, (y2 - y1) * 0.88))
    baseline = float(region.get("baseline") or (y1 + font_size))
    fill = region.get("color") or "#111111"
    confidence = float(region.get("confidence") or 0)
    region_id = sanitize_id(str(region.get("id") or text), f"text-{index}")
    review = ' data-needs-review="true"' if region.get("needs_review") or confidence < 0.75 else ""
    font_family = html.escape(choose_font(region, font_override), quote=True)
    return (
        f'    <text id="{region_id}" x="{fmt_num(x1)}" y="{fmt_num(baseline)}" '
        f'font-family="{font_family}" font-size="{fmt_num(font_size)}" fill="{html.escape(fill, quote=True)}"{review}>'
        f"{html.escape(text)}</text>"
    )


def fallback_art_path(region: dict, index: int) -> str:
    bbox = region.get("bbox") or [0, 0, 0, 0]
    x1, y1, x2, y2 = [float(v) for v in bbox]
    fill = html.escape(region.get("color") or "#111111", quote=True)
    region_id = sanitize_id(str(region.get("id") or region.get("text") or ""), f"art-{index}")
    d = " ".join(
        [
            f"M {fmt_num(x1)} {fmt_num(y1)}",
            f"L {fmt_num(x2)} {fmt_num(y1)}",
            f"L {fmt_num(x2)} {fmt_num(y2)}",
            f"L {fmt_num(x1)} {fmt_num(y2)}",
            "Z",
        ]
    )
    # 降级路径只标出艺术字占位，提醒后续可用矢量化脚本替换。
    return f'    <path id="{region_id}-fallback" d="{d}" fill="{fill}" opacity="0.35" data-fallback="true"/>'


def art_paths_for(region: dict, index: int, art_vectors: dict[str, dict]) -> list[str]:
    region_id = sanitize_id(str(region.get("id") or region.get("text") or ""), f"art-{index}")
    vector = art_vectors.get(region.get("id")) or art_vectors.get(region_id)
    if not vector:
        return [fallback_art_path(region, index)]
    lines = []
    for path_index, path in enumerate(vector.get("paths", []), start=1):
        d = path.get("d") if isinstance(path, dict) else str(path)
        fill = path.get("fill", vector.get("fill", region.get("color", "#111111"))) if isinstance(path, dict) else vector.get("fill", region.get("color", "#111111"))
        lines.append(
            f'    <path id="{region_id}-{path_index}" d="{html.escape(d, quote=True)}" '
            f'fill="{html.escape(fill, quote=True)}"/>'
        )
    return lines or [fallback_art_path(region, index)]


def build_svg(args: argparse.Namespace) -> Path:
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    width, height = normalize_background(args.full_poster, args.clean_background, out_dir)
    svg_width, svg_height = parse_target_size(args.target_size, width, height)
    regions = load_regions(args.text_regions)
    art_vectors = load_art_vectors(args.art_vectors)

    text_lines: list[str] = []
    art_lines: list[str] = []
    for index, region in enumerate(regions, start=1):
        kind = region.get("kind") or region.get("type") or "editable-text"
        if kind == "art-text":
            art_lines.extend(art_paths_for(region, index, art_vectors))
        else:
            text_lines.append(editable_text_element(region, index, args.font_family))

    svg = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{html.escape(svg_width, quote=True)}" height="{html.escape(svg_height, quote=True)}" viewBox="0 0 {width} {height}">',
            f"  <title>{html.escape(args.title)}</title>",
            '  <g id="background">',
            f'    <image id="clean-background" href="assets/background.png" x="0" y="0" width="{width}" height="{height}" preserveAspectRatio="none"/>',
            "  </g>",
            '  <g id="art-text">',
            *art_lines,
            "  </g>",
            '  <g id="editable-text">',
            *text_lines,
            "  </g>",
            '  <g id="qa-notes" display="none">',
            f'    <desc>Generated from {html.escape(str(args.full_poster))}; review low-confidence OCR text before print.</desc>',
            "  </g>",
            "</svg>",
            "",
        ]
    )
    svg_path = out_dir / "poster.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(svg_path)
    return svg_path


def main() -> int:
    build_svg(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
