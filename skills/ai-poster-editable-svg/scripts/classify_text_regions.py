#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify OCR text regions as editable text or art text.")
    parser.add_argument("regions", type=Path, help="Input text_regions.json from extract_poster_text.py.")
    parser.add_argument("--out", type=Path, required=True, help="Output classified JSON.")
    parser.add_argument("--art-confidence", type=float, default=0.58, help="Below this confidence, mark as art/needs review.")
    return parser.parse_args()


def classify(region: dict, art_confidence: float) -> dict:
    result = dict(region)
    if result.get("kind") == "art-text" or result.get("classification_locked"):
        return result
    bbox = result.get("bbox") or [0, 0, 0, 0]
    x1, y1, x2, y2 = [float(v) for v in bbox]
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    confidence = float(result.get("confidence") or 0)
    text = str(result.get("text") or "")

    # 低置信度、超大短标题、或形状比例异常的文字更可能是艺术字。
    if confidence < art_confidence:
        result["kind"] = "art-text"
        result["needs_review"] = True
    elif len(text.strip()) <= 4 and height >= 52 and width / height >= 2.8:
        result["kind"] = "art-text"
    else:
        result["kind"] = "editable-text"
    return result


def main() -> int:
    args = parse_args()
    data = json.loads(args.regions.read_text(encoding="utf-8"))
    regions = data if isinstance(data, list) else data.get("regions", [])
    output = dict(data) if isinstance(data, dict) else {}
    output["regions"] = [classify(region, args.art_confidence) for region in regions]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
