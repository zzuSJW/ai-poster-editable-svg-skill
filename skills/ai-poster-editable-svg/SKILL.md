---
name: ai-poster-editable-svg
description: Use when Codex needs to convert AI-generated poster images, ChatGPT poster outputs, or 有字海报 + 无字背景 pairs into Illustrator-friendly SVG with editable normal text, vector art text, and a linked clean background image.
---

# AI Poster Editable SVG

## Overview

把 ChatGPT / AI 生成的海报重建为适合 Illustrator 后续编辑和印刷排版的 SVG。默认使用两张图：有字完整海报用于识别文字，无字背景图作为 SVG 外链背景；普通文字输出为真实 `<text>`，艺术字输出为 SVG path。

## Core Contract

- 默认交付 `poster.svg` 和 `assets/background.png`，背景必须用 `<image href="assets/background.png">` 引用，禁止 base64。
- 普通标题、正文、价格、日期、地址、按钮文案优先做成可编辑文本。
- 花体、变形、强描边、发光、透视、与插画融合的文字归为艺术字，允许不可编辑但必须矢量化为 path。
- 背景不做矢量化；如果用户只给有字图，允许低稳定度单图兜底，但必须说明不如双图流程可靠。
- 面向 Illustrator / 印刷优先，保持真实画布尺寸、语义分组和可移动图层。

## Workflow

1. 收集输入：`full_poster`、`clean_background`、目标尺寸。优先要求两图同尺寸。
2. 运行 OCR：
   ```bash
   python scripts/extract_poster_text.py full_poster.png --clean-background clean_background.png --out outputs/text_regions.json
   ```
3. 分类文字：
   ```bash
   python scripts/classify_text_regions.py outputs/text_regions.json --out outputs/classified_regions.json
   ```
4. 矢量化艺术字：
   ```bash
   python scripts/vectorize_art_text.py full_poster.png clean_background.png outputs/classified_regions.json --out outputs/art_vectors.json
   ```
5. 构建 SVG：
   ```bash
   python scripts/build_editable_svg.py --full-poster full_poster.png --clean-background clean_background.png --text-regions outputs/classified_regions.json --art-vectors outputs/art_vectors.json --out-dir outputs/poster
   ```
6. QA 渲染检查：
   ```bash
   python scripts/qa_render_svg.py outputs/poster/poster.svg full_poster.png --out outputs/qa
   ```
7. 交付 `outputs/poster/poster.svg` 和 `outputs/poster/assets/background.png`。

## Decision Rules

- 如果用户能提供无字背景，必须走双图流程。
- 如果两图比例不同超过 2%，停止并要求重新生成无字背景；不要强行拉伸。
- 如果 OCR 置信度低、文字很小、或识别结果明显不通顺，把该项标记为 `needs_review`，最终提醒用户复核。
- 如果用户提供原始文案，以用户文案覆盖 OCR 结果；如果没有文案，保留 OCR 文本并提示校对。
- 如果字体无法精确匹配，选相近本机字体并保留可编辑性；不要为了完全像原图而把普通文字转路径。
- 只有艺术字、装饰字、强风格字可以转路径。

## SVG Requirements

- 顶层分组使用 `background`、`editable-text`、`art-text`、`qa-notes`。
- 背景图固定写为 `assets/background.png`，使用相对路径，不使用绝对路径、不使用 base64。
- 文本层使用 `<text>` / `<tspan>`，保留 `font-family`、`font-size`、`fill`、`x`、`y`。
- 避免 `<foreignObject>`、脚本、动画、外部 CSS 和远程字体。
- 生成的 SVG 必须能在浏览器打开，也要尽量兼容 Illustrator 导入。

## Scripts

- `extract_poster_text.py`：用 RapidOCR 识别中英文文字；缺依赖时提示安装。
- `classify_text_regions.py`：按置信度、尺寸和视觉复杂度区分普通文字与艺术字。
- `vectorize_art_text.py`：用有字版和无字背景做差分，输出艺术字 path 数据。
- `build_editable_svg.py`：复制无字背景为 `assets/background.png`，生成最终 `poster.svg`。
- `qa_render_svg.py`：用 Chrome 渲染 SVG，生成 `render.png`、`overlay.png` 和 `metrics.json`。

## References

Read `references/illustrator-poster-workflow.md` before deciding whether a region should stay editable text or become art text.
