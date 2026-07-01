#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract poster text regions with RapidOCR.")
    parser.add_argument("poster", type=Path, help="Full poster image with text.")
    parser.add_argument("--clean-background", type=Path, help="Optional clean background for better color estimation.")
    parser.add_argument("--out", type=Path, default=Path("outputs/text_regions.json"), help="Output JSON path.")
    return parser.parse_args()


def normalize_ocr_item(item) -> tuple[list[list[float]], str, float] | None:
    if not item:
        return None
    if len(item) >= 3:
        box, text, score = item[0], item[1], item[2]
    elif len(item) == 2 and isinstance(item[1], (tuple, list)) and len(item[1]) >= 2:
        box, text, score = item[0], item[1][0], item[1][1]
    else:
        return None
    return box, str(text), float(score)


def bbox_from_poly(poly: list[list[float]]) -> list[int]:
    xs = [point[0] for point in poly]
    ys = [point[1] for point in poly]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def hex_color(rgb: np.ndarray) -> str:
    values = np.clip(np.round(rgb).astype(int), 0, 255)
    return "#{:02x}{:02x}{:02x}".format(int(values[0]), int(values[1]), int(values[2]))


def estimate_color(poster: Image.Image, clean: Image.Image | None, bbox: list[int]) -> str:
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(poster.width, x2), min(poster.height, y2)
    if x2 <= x1 or y2 <= y1:
        return "#111111"
    crop = np.asarray(poster.crop((x1, y1, x2, y2)).convert("RGB")).astype(float)
    if clean:
        bg = np.asarray(clean.crop((x1, y1, x2, y2)).convert("RGB")).astype(float)
        diff = np.linalg.norm(crop - bg, axis=2)
        mask = diff > max(18.0, float(np.percentile(diff, 80)))
    else:
        border = np.concatenate([crop[0], crop[-1], crop[:, 0], crop[:, -1]], axis=0)
        bg = np.median(border, axis=0)
        diff = np.linalg.norm(crop - bg, axis=2)
        mask = diff > max(18.0, float(np.percentile(diff, 75)))
    if int(mask.sum()) < 4:
        return hex_color(np.median(crop.reshape(-1, 3), axis=0))
    return hex_color(np.median(crop[mask], axis=0))


def safe_id(text: str, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return slug or f"text-{index}"


def run_ocr(image: Path):
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:
        raise SystemExit(
            "RapidOCR is required. Install with: pip install rapidocr-onnxruntime"
        ) from exc
    ocr = RapidOCR()
    result = ocr(str(image))
    if isinstance(result, tuple):
        return result[0] or []
    return result or []


def main() -> int:
    args = parse_args()
    poster = Image.open(args.poster).convert("RGB")
    clean = Image.open(args.clean_background).convert("RGB") if args.clean_background else None
    regions = []
    for index, raw in enumerate(run_ocr(args.poster), start=1):
        parsed = normalize_ocr_item(raw)
        if not parsed:
            continue
        poly, text, confidence = parsed
        bbox = bbox_from_poly(poly)
        font_size = max(8, int(round((bbox[3] - bbox[1]) * 0.88)))
        regions.append(
            {
                "id": safe_id(text, index),
                "text": text,
                "confidence": round(confidence, 4),
                "bbox": bbox,
                "polygon": poly,
                "color": estimate_color(poster, clean, bbox),
                "font_size": font_size,
                "kind": "editable-text",
                "needs_review": confidence < 0.75,
            }
        )
    output = {
        "source": str(args.poster),
        "clean_background": str(args.clean_background) if args.clean_background else None,
        "size": [poster.width, poster.height],
        "regions": regions,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
