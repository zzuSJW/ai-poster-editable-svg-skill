#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vectorize art-text regions by differencing full poster and clean background.")
    parser.add_argument("full_poster", type=Path)
    parser.add_argument("clean_background", type=Path)
    parser.add_argument("classified_regions", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=24.0)
    parser.add_argument("--padding", type=int, default=8)
    return parser.parse_args()


def rect_path(bbox: list[float]) -> str:
    x1, y1, x2, y2 = bbox
    return f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y1:.1f} L {x2:.1f} {y2:.1f} L {x1:.1f} {y2:.1f} Z"


def path_from_points(points: np.ndarray, offset_x: int, offset_y: int) -> str:
    pts = points.reshape(-1, 2)
    if len(pts) < 3:
        return ""
    commands = [f"M {pts[0][0] + offset_x:.1f} {pts[0][1] + offset_y:.1f}"]
    commands.extend(f"L {x + offset_x:.1f} {y + offset_y:.1f}" for x, y in pts[1:])
    commands.append("Z")
    return " ".join(commands)


def median_fill(full_crop: np.ndarray, mask: np.ndarray, fallback: str) -> str:
    pixels = full_crop[mask > 0]
    if len(pixels) < 4:
        return fallback
    rgb = np.median(pixels, axis=0).astype(int)
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def vectorize_region(full: Image.Image, clean: Image.Image, region: dict, args: argparse.Namespace) -> dict:
    bbox = region.get("bbox") or [0, 0, 0, 0]
    x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
    x1 = max(0, x1 - args.padding)
    y1 = max(0, y1 - args.padding)
    x2 = min(full.width, x2 + args.padding)
    y2 = min(full.height, y2 + args.padding)
    if x2 <= x1 or y2 <= y1:
        return {"id": region.get("id"), "fill": region.get("color", "#111111"), "paths": []}

    full_crop = np.asarray(full.crop((x1, y1, x2, y2)).convert("RGB"))
    clean_crop = np.asarray(clean.crop((x1, y1, x2, y2)).convert("RGB"))
    diff = np.linalg.norm(full_crop.astype(float) - clean_crop.astype(float), axis=2)
    mask = (diff > args.threshold).astype(np.uint8) * 255
    fill = median_fill(full_crop, mask, region.get("color", "#111111"))

    paths: list[dict] = []
    try:
        import cv2

        kernel = np.ones((2, 2), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 6:
                continue
            epsilon = max(0.8, 0.006 * cv2.arcLength(contour, True))
            approx = cv2.approxPolyDP(contour, epsilon, True)
            d = path_from_points(approx, x1, y1)
            if d:
                paths.append({"d": d, "fill": fill, "area": round(float(area), 2)})
    except Exception:
        paths.append({"d": rect_path([x1, y1, x2, y2]), "fill": fill, "fallback": True})

    if not paths:
        paths.append({"d": rect_path([x1, y1, x2, y2]), "fill": fill, "fallback": True})
    return {"id": region.get("id"), "text": region.get("text"), "fill": fill, "bbox": [x1, y1, x2, y2], "paths": paths}


def main() -> int:
    args = parse_args()
    full = Image.open(args.full_poster).convert("RGB")
    clean = Image.open(args.clean_background).convert("RGB")
    if clean.size != full.size:
        clean_ratio = clean.width / clean.height
        full_ratio = full.width / full.height
        if abs(clean_ratio - full_ratio) > 0.02:
            raise SystemExit("Full poster and clean background ratios differ by more than 2%; regenerate the clean background.")
        clean = clean.resize(full.size, Image.Resampling.LANCZOS)
    data = json.loads(args.classified_regions.read_text(encoding="utf-8"))
    regions = data if isinstance(data, list) else data.get("regions", [])
    art_regions = [vectorize_region(full, clean, region, args) for region in regions if region.get("kind") == "art-text"]
    output = {"source": str(args.full_poster), "clean_background": str(args.clean_background), "art_regions": art_regions}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
