#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image


CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "google-chrome",
    "chromium",
    "chromium-browser",
    "chrome",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render SVG poster and compare it to the full poster.")
    parser.add_argument("svg", type=Path)
    parser.add_argument("full_poster", type=Path)
    parser.add_argument("--out", type=Path, default=Path("outputs/qa"))
    return parser.parse_args()


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if not candidate:
            continue
        if Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    raise SystemExit("No Chrome/Chromium found. Set CHROME_BIN to a browser binary.")


def render_svg(svg: Path, width: int, height: int, chrome: str, out_path: Path) -> Image.Image:
    screenshot = out_path.resolve()
    # 直接打开 SVG 文档，避免 <img> 嵌套时 Chrome 阻止 SVG 内部相对图片引用。
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--screenshot={screenshot}",
            f"--window-size={width},{height}",
            "--default-background-color=FFFFFFFF",
            svg.resolve().as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    if not screenshot.exists():
        raise SystemExit(f"Chrome finished but did not create screenshot: {screenshot}")
    return Image.open(screenshot).convert("RGB")


def main() -> int:
    args = parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    source = Image.open(args.full_poster).convert("RGB")
    width, height = source.size
    render_path = args.out / "render.png"
    render = render_svg(args.svg, width, height, find_chrome(), render_path)

    src = np.asarray(source).astype(float)
    ren = np.asarray(render).astype(float)
    delta = np.linalg.norm(src - ren, axis=2)
    overlay = src.copy()
    mask = delta > 38
    overlay[mask] = overlay[mask] * 0.35 + np.array([0, 200, 220]) * 0.65
    Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8)).save(args.out / "overlay.png")
    metrics = {
        "svg": str(args.svg),
        "full_poster": str(args.full_poster),
        "mean_delta": round(float(delta.mean()), 3),
        "changed_px": int(mask.sum()),
        "changed_ratio": round(float(mask.mean()), 5),
    }
    (args.out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
