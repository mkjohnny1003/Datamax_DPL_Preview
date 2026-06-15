from __future__ import annotations

import io
from hashlib import md5
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

try:
    from datamax_dpl_preview import (
        PRINTER_DPI,
        DPL_POSITION_UNITS_PER_INCH,
        ParsedLabel,
        barcode_runs,
        build_preview_svg,
        collect_target_files,
        containing_box,
        datamatrix_matrix,
        decode_ascii_safe,
        estimate_canvas_size,
        font_style,
        load_datamax_profile,
        parse_dpl_preview,
        qr_matrix,
        render_element_svg,
        resolve_graphic,
    )
except ModuleNotFoundError:
    from Datamax_DPL_Preview.datamax_dpl_preview import (
        PRINTER_DPI,
        DPL_POSITION_UNITS_PER_INCH,
        ParsedLabel,
        barcode_runs,
        build_preview_svg,
        collect_target_files,
        containing_box,
        datamatrix_matrix,
        decode_ascii_safe,
        estimate_canvas_size,
        font_style,
        load_datamax_profile,
        parse_dpl_preview,
        qr_matrix,
        render_element_svg,
        resolve_graphic,
    )


PREVIEW_BACKGROUND = "#f3f5f7"
CANVAS_BORDER = "#c7ccd4"
MANUAL_BORDER = "#2f6fed"
LABEL_BOUNDARY_COLOR = "#2f6fed"
TEXT_COLOR = (17, 17, 17, 255)
VIEWER_TITLE = "Datamax DPL Preview Viewer"
SUPPORTED_TYPES = [
    ("DPL files", "*.max *.dpl *.prn *.txt"),
    ("All files", "*.*"),
]
FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
FONT_SEARCH_PATHS = [
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    Path.home() / "AppData/Local/Fonts",
    Path("C:/Windows/Fonts"),
]
FONT_ROLE_CANDIDATES = {
    "black": ("ariblk.ttf", "ARIBLK.TTF", "arialbd.ttf"),
    "bold": ("arialbd.ttf", "ARIALBD.TTF", "tahomabd.ttf"),
    "courier": ("cour.ttf", "COUR.TTF", "courbd.ttf", "COURBD.TTF"),
    "regular": ("arial.ttf", "ARIAL.TTF", "tahoma.ttf", "TAHOMA.TTF"),
    "narrow": ("arialn.ttf", "ARIALN.TTF", "bahnschrift.ttf", "arial.ttf"),
    "times": ("times.ttf", "TIMES.TTF", "timesbd.ttf", "TIMESBD.TTF", "timesnewroman.ttf"),
    "tahoma": ("tahoma.ttf", "TAHOMA.TTF", "tahomabd.ttf"),
}
SIZE_NOTE_RE = re.compile(r"(?P<w>\d+(?:\.\d+)?)x(?P<h>\d+(?:\.\d+)?) mm", re.IGNORECASE)
BROWSER_CANDIDATES = (
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
)
BROWSER_RENDER_CACHE: dict[tuple[str, int, int], Image.Image] = {}


def units_from_mm(value_mm: float) -> int:
    return max(1, int(round(value_mm * DPL_POSITION_UNITS_PER_INCH / 25.4)))


def raster_scale() -> float:
    return PRINTER_DPI / DPL_POSITION_UNITS_PER_INCH


def to_px(value: int | float) -> int:
    return max(1, int(round(float(value) * raster_scale())))


def content_canvas_size(parsed: ParsedLabel) -> tuple[int, int]:
    min_x = 0
    min_y = 0
    width = 1
    height = 1
    if parsed.elements:
        min_x = min(0, min(element.x for element in parsed.elements))
        min_y = min(0, min(element.y for element in parsed.elements))
    for element in parsed.elements:
        width = max(width, element.x + max(element.w, 1) + 4)
        height = max(height, element.y + max(element.h, 1) + 4)
    return width - min_x, height - min_y


def parse_size_note_mm(note: str) -> tuple[float, float] | None:
    match = SIZE_NOTE_RE.search(note or "")
    if not match:
        return None
    return float(match.group("w")), float(match.group("h"))


def font_role(font_code: str) -> str:
    if font_code in {"S00", "S98", "S51"}:
        return "black"
    if font_code == "S95":
        return "narrow"
    if font_code == "S94":
        return "times"
    if font_code == "S97":
        return "courier"
    if font_code == "S52":
        return "narrow"
    if font_code == "S50":
        return "regular"
    style = font_style(font_code)
    if int(style.get("weight", "400")) >= 700:
        return "bold"
    return "regular"


def locate_font_file(role: str) -> str | None:
    for candidate in FONT_ROLE_CANDIDATES.get(role, ()):
        for base in FONT_SEARCH_PATHS:
            font_path = base / candidate
            if font_path.exists():
                return str(font_path)
        try:
            ImageFont.truetype(candidate, 10)
            return candidate
        except OSError:
            continue
    return None


def load_font(font_code: str, size_px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size_px = max(8, size_px)
    role = font_role(font_code)
    cache_key = (role, size_px)
    if cache_key in FONT_CACHE:
        return FONT_CACHE[cache_key]

    font_path = locate_font_file(role)
    if font_path is not None:
        font = ImageFont.truetype(font_path, size_px)
    else:
        font = ImageFont.load_default()
    FONT_CACHE[cache_key] = font
    return font


def barcode_image(width_px: int, height_px: int, seed_text: str, runs: list[tuple[bool, int]]) -> Image.Image:
    image = Image.new("RGBA", (max(1, width_px), max(1, height_px)), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    if runs:
        total_dots = sum(run_width for _is_bar, run_width in runs)
        if total_dots > 0:
            scale_x = width_px / total_dots
            cursor = 0.0
            inner_y = max(0.0, height_px * 0.06)
            inner_h = max(1.0, height_px * 0.88)
            for is_bar, run_width in runs:
                draw_width = run_width * scale_x
                if is_bar and draw_width > 0:
                    draw.rectangle(
                        (
                            cursor,
                            inner_y,
                            cursor + draw_width - 1,
                            inner_y + inner_h - 1,
                        ),
                        fill=TEXT_COLOR,
                    )
                cursor += draw_width
            return image

    digest = md5(seed_text.encode("utf-8")).digest()
    x = 4
    index = 0
    while x < width_px - 4:
        value = digest[index % len(digest)]
        bar_w = 1 + (value % 4)
        gap = 1 + ((value // 4) % 3)
        draw.rectangle((x, 4, x + bar_w - 1, max(5, height_px - 5)), fill=TEXT_COLOR)
        x += bar_w + gap
        index += 1
    return image


def matrix_image(matrix: list[list[bool]], width_px: int, height_px: int) -> Image.Image:
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    tiny = Image.new("1", (max(cols, 1), max(rows, 1)), 1)
    for row in range(rows):
        for col in range(cols):
            if matrix[row][col]:
                tiny.putpixel((col, row), 0)
    enlarged = tiny.resize((max(1, width_px), max(1, height_px)), Image.Resampling.NEAREST)
    rgba = Image.new("RGBA", enlarged.size, (255, 255, 255, 0))
    mask = ImageOps.invert(enlarged.convert("L"))
    rgba.paste((17, 17, 17, 255), mask=mask)
    return rgba


def graphic_image(graphic: tuple[int, int, list[str]], width_px: int, height_px: int) -> Image.Image:
    width_bits, height_rows, rows = graphic
    tiny = Image.new("1", (max(width_bits, 1), max(height_rows, 1)), 1)
    for row_index, row in enumerate(reversed(rows)):
        for nibble_index, nibble in enumerate(row):
            value = int(nibble, 16)
            for bit in range(4):
                if value & (1 << (3 - bit)):
                    tiny.putpixel((nibble_index * 4 + bit, row_index), 0)
    enlarged = tiny.resize((max(1, width_px), max(1, height_px)), Image.Resampling.NEAREST)
    rgba = Image.new("RGBA", enlarged.size, (255, 255, 255, 0))
    mask = ImageOps.invert(enlarged.convert("L"))
    rgba.paste((17, 17, 17, 255), mask=mask)
    return rgba


def draw_scaled_text(
    canvas: Image.Image,
    text: str,
    x_px: int,
    y_px: int,
    font_code: str,
    font_size_px: int,
    width_scale: float,
) -> None:
    if not text:
        text = " "
    font = load_font(font_code, font_size_px)
    scratch = Image.new("RGBA", (8, 8), (255, 255, 255, 0))
    scratch_draw = ImageDraw.Draw(scratch)
    bbox = scratch_draw.textbbox((0, 0), text, font=font)
    text_width = max(1, bbox[2] - bbox[0])
    text_height = max(1, bbox[3] - bbox[1])
    temp = Image.new("RGBA", (text_width + 6, text_height + 6), (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(temp)
    temp_draw.text((3 - bbox[0], 3 - bbox[1]), text, font=font, fill=TEXT_COLOR)
    target_width = max(1, int(round(temp.width * max(width_scale, 0.05))))
    if target_width != temp.width:
        temp = temp.resize((target_width, temp.height), Image.Resampling.BICUBIC)
    canvas.alpha_composite(temp, (x_px, y_px))


def build_preview_image(
    parsed: ParsedLabel,
    label_size_override_mm: tuple[float, float] | None = None,
) -> tuple[Image.Image, dict[str, object]]:
    inferred_width, inferred_height, _min_x, _min_y = estimate_canvas_size(parsed)
    content_width, content_height = content_canvas_size(parsed)
    label_width = inferred_width
    label_height = inferred_height
    size_note = parsed.label_size or "300 dpi canvas"
    manual_override = False
    overflow = False

    if label_size_override_mm is not None:
        manual_override = True
        requested_width = units_from_mm(label_size_override_mm[0])
        requested_height = units_from_mm(label_size_override_mm[1])
        label_width = requested_width
        label_height = requested_height
        overflow = content_width > requested_width or content_height > requested_height
        size_note = f"{label_size_override_mm[0]:g}x{label_size_override_mm[1]:g} mm manual"

    canvas_width = max(content_width, label_width)
    canvas_height = max(content_height, label_height)
    output_w = to_px(canvas_width)
    output_h = to_px(canvas_height)
    image = Image.new("RGBA", (output_w, output_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    border_color = MANUAL_BORDER if manual_override else CANVAS_BORDER
    border_y = max(0, output_h - to_px(label_height))
    draw.rectangle(
        (
            0,
            border_y,
            max(1, to_px(label_width)) - 1,
            border_y + max(1, to_px(label_height)) - 1,
        ),
        outline=border_color,
        width=max(1, int(round(raster_scale() * 0.5))),
    )

    boxes = [element for element in parsed.elements if element.kind == "box"]

    for element in parsed.elements:
        x_px = int(round(element.x * raster_scale()))
        y_units = canvas_height - element.y - element.h
        y_px = int(round(y_units * raster_scale()))
        width_px = to_px(element.w)
        height_px = to_px(element.h)

        if element.kind == "line":
            draw.rectangle(
                (x_px, y_px, x_px + width_px - 1, y_px + height_px - 1),
                fill=TEXT_COLOR,
            )
            continue

        if element.kind == "box":
            draw.rectangle(
                (x_px, y_px, x_px + width_px - 1, y_px + height_px - 1),
                outline=TEXT_COLOR,
                width=max(1, int(round(raster_scale() * 0.4))),
            )
            continue

        if element.kind == "barcode":
            selector = str(element.meta.get("selector", ""))
            wide_dots = int(element.meta.get("wide_dots", 2))
            narrow_dots = int(element.meta.get("narrow_dots", 2))
            runs = barcode_runs(selector, element.text, wide_dots, narrow_dots)
            barcode = barcode_image(width_px, height_px, element.text + element.command, runs)
            image.alpha_composite(barcode, (x_px, y_px))
            continue

        if element.kind == "qrcode":
            qrcode_img = matrix_image(qr_matrix(element.text), width_px, height_px)
            image.alpha_composite(qrcode_img, (x_px, y_px))
            continue

        if element.kind == "datamatrix":
            datamatrix_img = matrix_image(datamatrix_matrix(element.text), width_px, height_px)
            image.alpha_composite(datamatrix_img, (x_px, y_px))
            continue

        if element.kind == "graphic":
            graphic = resolve_graphic(element.text, parsed.graphics)
            if graphic is not None:
                graphic_img = graphic_image(graphic, width_px, height_px)
                image.alpha_composite(graphic_img, (x_px, y_px))
            continue

        font_size_px = max(8, int(round((element.font_px or max(8, int(element.h * 0.82))) * raster_scale())))
        render_height_px = font_size_px + max(2, int(round(raster_scale() * 2)))
        text_y_units = canvas_height - element.y - (element.font_px or max(8, int(element.h * 0.82))) - 2
        text_y_px = int(round(text_y_units * raster_scale()))
        width_scale = 1.0
        char_height_dots = int(element.meta.get("char_height_dots", 0))
        char_width_dots = int(element.meta.get("char_width_dots", 0))
        if char_height_dots > 0 and char_width_dots > 0:
            width_scale = char_width_dots / char_height_dots
        width_scale *= float(font_style(element.font_code).get("scale", 1.0))
        box = containing_box(element, boxes)
        if box is not None:
            available_width_px = max(1, to_px(box.w - 4))
            rendered_width_px = max(1.0, width_px * width_scale)
            width_scale *= min(1.0, available_width_px / rendered_width_px)
        draw_scaled_text(
            image,
            element.text,
            x_px + 1,
            max(0, text_y_px),
            element.font_code,
            font_size_px,
            width_scale,
        )

    return image, {
        "canvas_units": (canvas_width, canvas_height),
        "label_units": (label_width, label_height),
        "content_units": (content_width, content_height),
        "label_origin_units": (0, canvas_height - label_height),
        "size_note": size_note,
        "manual_override": manual_override,
        "overflow": overflow,
    }


def build_preview_meta(
    parsed: ParsedLabel,
    label_size_override_mm: tuple[float, float] | None = None,
) -> dict[str, object]:
    inferred_width, inferred_height, _min_x, _min_y = estimate_canvas_size(parsed)
    content_width, content_height = content_canvas_size(parsed)
    label_width = inferred_width
    label_height = inferred_height
    size_note = parsed.label_size or "300 dpi canvas"
    manual_override = False
    overflow = False

    if label_size_override_mm is not None:
        manual_override = True
        requested_width = units_from_mm(label_size_override_mm[0])
        requested_height = units_from_mm(label_size_override_mm[1])
        label_width = requested_width
        label_height = requested_height
        overflow = content_width > requested_width or content_height > requested_height
        size_note = f"{label_size_override_mm[0]:g}x{label_size_override_mm[1]:g} mm manual"

    canvas_width = max(content_width, label_width)
    canvas_height = max(content_height, label_height)
    return {
        "canvas_units": (canvas_width, canvas_height),
        "label_units": (label_width, label_height),
        "content_units": (content_width, content_height),
        "label_origin_units": (0, canvas_height - label_height),
        "size_note": size_note,
        "manual_override": manual_override,
        "overflow": overflow,
    }


def locate_browser_executable() -> str | None:
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    for name in ("msedge.exe", "chrome.exe", "msedge", "chrome"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def build_browser_svg(parsed: ParsedLabel, preview_meta: dict[str, object]) -> str:
    profile = load_datamax_profile(parsed.path)
    canvas_width, canvas_height = preview_meta["canvas_units"]  # type: ignore[assignment]
    label_width, label_height = preview_meta["label_units"]  # type: ignore[assignment]
    label_origin_x, label_origin_y = preview_meta["label_origin_units"]  # type: ignore[assignment]
    boxes = [element for element in parsed.elements if element.kind == "box"]
    raster = PRINTER_DPI / DPL_POSITION_UNITS_PER_INCH
    output_w = max(1, int(round(canvas_width * raster)))
    output_h = max(1, int(round(canvas_height * raster)))

    parts: list[str] = []
    for element in parsed.elements:
        parts.append(
            render_element_svg(
                element,
                graphics=parsed.graphics,
                canvas_height=canvas_height,
                boxes=boxes,
                profile=profile,
            )
        )

    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{output_w}' height='{output_h}' "
        f"viewBox='0 0 {canvas_width} {canvas_height}'>"
        "<style>text { fill: #111111; dominant-baseline: alphabetic; }</style>"
        f"<rect x='0' y='0' width='{canvas_width}' height='{canvas_height}' fill='#ffffff' />"
        f"<rect x='{label_origin_x}' y='{label_origin_y}' width='{label_width}' height='{label_height}' "
        "fill='none' stroke='#c7ccd4' stroke-width='1' />"
        f"{''.join(parts)}"
        "</svg>"
    )


def render_svg_with_browser(svg_content: str, width_px: int, height_px: int) -> Image.Image | None:
    browser_executable = locate_browser_executable()
    if browser_executable is None:
        return None

    cache_key = (md5(svg_content.encode("utf-8")).hexdigest(), width_px, height_px)
    cached = BROWSER_RENDER_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()

    viewport_w = max(64, width_px)
    viewport_h = max(64, height_px)
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>"
        "html,body{margin:0;padding:0;background:#ffffff;overflow:hidden;}"
        f"html,body{{width:{viewport_w}px;height:{viewport_h}px;}}"
        "svg{display:block;}"
        "</style></head><body>"
        f"{svg_content}"
        "</body></html>"
    )

    with tempfile.TemporaryDirectory(prefix="dpl_preview_") as temp_dir:
        temp_root = Path(temp_dir)
        html_path = temp_root / "preview.html"
        png_path = temp_root / "preview.png"
        html_path.write_text(html, encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = None
        for headless_arg in ("--headless=new", "--headless"):
            command = [
                browser_executable,
                headless_arg,
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={viewport_w},{viewport_h}",
                f"--screenshot={png_path}",
                str(html_path),
            ]
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                timeout=20,
            )
            if completed.returncode == 0 and png_path.exists():
                break
        if completed is None or completed.returncode != 0 or not png_path.exists():
            return None
        with Image.open(png_path) as browser_image:
            rendered = browser_image.convert("RGBA")
        BROWSER_RENDER_CACHE[cache_key] = rendered.copy()
        return rendered


def render_from_bytes(
    path: Path,
    data: bytes,
    label_size_override_mm: tuple[float, float] | None = None,
) -> tuple[ParsedLabel, Image.Image, dict[str, object]]:
    parsed = parse_dpl_preview(path, data)
    preview_meta = build_preview_meta(parsed, label_size_override_mm)
    canvas_width, canvas_height = preview_meta["canvas_units"]  # type: ignore[assignment]
    svg_content = build_browser_svg(parsed, preview_meta)
    image = render_svg_with_browser(
        svg_content,
        to_px(canvas_width),
        to_px(canvas_height),
    )
    if image is None:
        image, preview_meta = build_preview_image(parsed, label_size_override_mm)
    return parsed, image, preview_meta


class PreviewViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(VIEWER_TITLE)
        self.root.geometry("1560x960")
        self.root.minsize(1180, 760)

        self.current_path: Path | None = None
        self.current_bytes: bytes = b""
        self.current_parsed: ParsedLabel | None = None
        self.current_image: Image.Image | None = None
        self.tk_image: ImageTk.PhotoImage | None = None
        self.folder_files: list[Path] = []
        self.listbox_index_to_path: dict[int, Path] = {}
        self.render_after_id: str | None = None
        self.zoom_mode = tk.StringVar(value="fit")
        self.auto_size = tk.BooleanVar(value=True)
        self.label_width_mm = tk.StringVar(value="")
        self.label_height_mm = tk.StringVar(value="")
        self.preview_meta: dict[str, object] = {}

        self._build_ui()
        self._set_editor_text(
            "[Start]\n"
            "1911S960224002700340032TYPE\n"
            "1911S960224012001000032ST7701SN-G5-1\n"
            "1e22000600150030ABC0123456789\n"
        )
        self.render_editor_content()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Open File", command=self.open_file).pack(side="left")
        ttk.Button(toolbar, text="Open Folder", command=self.open_folder).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Render Text", command=self.render_editor_content).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Save SVG", command=self.save_svg).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Reload File", command=self.reload_current_file).pack(side="left", padx=(6, 0))

        ttk.Label(toolbar, text="Preview zoom:").pack(side="left", padx=(18, 4))
        ttk.Radiobutton(toolbar, text="Fit", variable=self.zoom_mode, value="fit", command=self.refresh_preview).pack(side="left")
        ttk.Radiobutton(toolbar, text="100%", variable=self.zoom_mode, value="1.0", command=self.refresh_preview).pack(side="left")
        ttk.Radiobutton(toolbar, text="150%", variable=self.zoom_mode, value="1.5", command=self.refresh_preview).pack(side="left")
        ttk.Radiobutton(toolbar, text="200%", variable=self.zoom_mode, value="2.0", command=self.refresh_preview).pack(side="left")

        self.auto_render = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Auto render", variable=self.auto_render).pack(side="left", padx=(18, 0))

        size_frame = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        size_frame.pack(fill="x")
        ttk.Checkbutton(
            size_frame,
            text="Auto size",
            variable=self.auto_size,
            command=self.on_size_mode_changed,
        ).pack(side="left")
        ttk.Label(size_frame, text="Label size mm:").pack(side="left", padx=(14, 6))
        self.width_entry = ttk.Entry(size_frame, textvariable=self.label_width_mm, width=8)
        self.width_entry.pack(side="left")
        ttk.Label(size_frame, text="x").pack(side="left", padx=4)
        self.height_entry = ttk.Entry(size_frame, textvariable=self.label_height_mm, width=8)
        self.height_entry.pack(side="left")
        ttk.Label(size_frame, text="mm").pack(side="left", padx=(4, 0))
        ttk.Button(size_frame, text="Apply Size", command=self.render_editor_content).pack(side="left", padx=(10, 0))
        self.width_entry.bind("<KeyRelease>", self._schedule_auto_render)
        self.height_entry.bind("<KeyRelease>", self._schedule_auto_render)

        main_pane = ttk.Panedwindow(self.root, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left_frame = ttk.Frame(main_pane)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=5)
        main_pane.add(right_frame, weight=7)

        left_pane = ttk.Panedwindow(left_frame, orient="vertical")
        left_pane.pack(fill="both", expand=True)

        editor_frame = ttk.Frame(left_pane, padding=(0, 0, 0, 6))
        list_frame = ttk.Frame(left_pane)
        left_pane.add(editor_frame, weight=7)
        left_pane.add(list_frame, weight=3)

        ttk.Label(editor_frame, text="DPL source / pasted DPL").pack(anchor="w", pady=(0, 4))
        editor_container = ttk.Frame(editor_frame)
        editor_container.pack(fill="both", expand=True)
        self.editor = tk.Text(editor_container, wrap="none", undo=True, font=("Consolas", 10))
        editor_x = ttk.Scrollbar(editor_container, orient="horizontal", command=self.editor.xview)
        editor_y = ttk.Scrollbar(editor_container, orient="vertical", command=self.editor.yview)
        self.editor.configure(xscrollcommand=editor_x.set, yscrollcommand=editor_y.set)
        self.editor.grid(row=0, column=0, sticky="nsew")
        editor_y.grid(row=0, column=1, sticky="ns")
        editor_x.grid(row=1, column=0, sticky="ew")
        editor_container.columnconfigure(0, weight=1)
        editor_container.rowconfigure(0, weight=1)
        self.editor.bind("<KeyRelease>", self._schedule_auto_render)

        list_header = ttk.Frame(list_frame)
        list_header.pack(fill="x", pady=(0, 4))
        ttk.Label(list_header, text="Folder file list").pack(side="left")
        self.folder_summary_var = tk.StringVar(value="No folder loaded")
        ttk.Label(list_header, textvariable=self.folder_summary_var, foreground="#54606c").pack(side="right")

        list_container = ttk.Frame(list_frame)
        list_container.pack(fill="both", expand=True)
        self.file_list = tk.Listbox(list_container, font=("Consolas", 10))
        list_y = ttk.Scrollbar(list_container, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=list_y.set)
        self.file_list.grid(row=0, column=0, sticky="nsew")
        list_y.grid(row=0, column=1, sticky="ns")
        list_container.columnconfigure(0, weight=1)
        list_container.rowconfigure(0, weight=1)
        self.file_list.bind("<<ListboxSelect>>", self.on_file_selected)

        preview_header = ttk.Frame(right_frame, padding=(0, 0, 0, 6))
        preview_header.pack(fill="x")
        self.source_var = tk.StringVar(value="Source: pasted text")
        self.info_var = tk.StringVar(value="Ready")
        self.profile_var = tk.StringVar(value="Printer profile: built-in Datamax defaults")
        ttk.Label(preview_header, textvariable=self.source_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(preview_header, textvariable=self.info_var, foreground="#54606c").pack(anchor="w", pady=(2, 0))
        ttk.Label(preview_header, textvariable=self.profile_var, foreground="#54606c").pack(anchor="w", pady=(2, 0))

        preview_container = ttk.Frame(right_frame)
        preview_container.pack(fill="both", expand=True)
        self.preview_canvas = tk.Canvas(preview_container, background=PREVIEW_BACKGROUND, highlightthickness=0)
        preview_x = ttk.Scrollbar(preview_container, orient="horizontal", command=self.preview_canvas.xview)
        preview_y = ttk.Scrollbar(preview_container, orient="vertical", command=self.preview_canvas.yview)
        self.preview_canvas.configure(xscrollcommand=preview_x.set, yscrollcommand=preview_y.set)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        preview_y.grid(row=0, column=1, sticky="ns")
        preview_x.grid(row=1, column=0, sticky="ew")
        preview_container.columnconfigure(0, weight=1)
        preview_container.rowconfigure(0, weight=1)
        self.preview_canvas.bind("<Configure>", lambda _event: self.refresh_preview())

    def _set_editor_text(self, content: str) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)

    def _schedule_auto_render(self, _event: tk.Event | None = None) -> None:
        if not self.auto_render.get():
            return
        if self.render_after_id is not None:
            self.root.after_cancel(self.render_after_id)
        self.render_after_id = self.root.after(350, self.render_editor_content)

    def on_size_mode_changed(self) -> None:
        self._update_size_entry_state()
        self.render_editor_content()

    def _update_size_entry_state(self) -> None:
        state = "disabled" if self.auto_size.get() else "normal"
        self.width_entry.configure(state=state)
        self.height_entry.configure(state=state)

    def current_size_override_mm(self) -> tuple[float, float] | None:
        if self.auto_size.get():
            return None
        width_text = self.label_width_mm.get().strip()
        height_text = self.label_height_mm.get().strip()
        if not width_text or not height_text:
            return None
        try:
            width_mm = float(width_text)
            height_mm = float(height_text)
        except ValueError:
            return None
        if width_mm <= 0 or height_mm <= 0:
            return None
        return width_mm, height_mm

    def update_size_fields_from_parsed(self, parsed: ParsedLabel) -> None:
        if not self.auto_size.get():
            return
        inferred = parse_size_note_mm(parsed.label_size)
        if inferred is None:
            content_width, content_height = content_canvas_size(parsed)
            inferred = (
                round(content_width * 25.4 / DPL_POSITION_UNITS_PER_INCH, 1),
                round(content_height * 25.4 / DPL_POSITION_UNITS_PER_INCH, 1),
            )
        self.label_width_mm.set(f"{inferred[0]:g}")
        self.label_height_mm.set(f"{inferred[1]:g}")

    def open_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open DPL file",
            filetypes=SUPPORTED_TYPES,
        )
        if not filename:
            return
        self.load_file(Path(filename))

    def open_folder(self) -> None:
        directory = filedialog.askdirectory(title="Open folder")
        if not directory:
            return
        root = Path(directory)
        files = collect_target_files(root, recursive=True)
        self.folder_files = files
        self.file_list.delete(0, "end")
        self.listbox_index_to_path.clear()
        for index, file_path in enumerate(files):
            relative = file_path.relative_to(root)
            self.file_list.insert("end", str(relative))
            self.listbox_index_to_path[index] = file_path
        self.folder_summary_var.set(f"{len(files)} files")
        if files:
            self.file_list.selection_clear(0, "end")
            self.file_list.selection_set(0)
            self.file_list.see(0)
            self.load_file(files[0])

    def on_file_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.file_list.curselection()
        if not selection:
            return
        path = self.listbox_index_to_path.get(selection[0])
        if path is not None:
            self.load_file(path)

    def load_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as exc:
            messagebox.showerror(VIEWER_TITLE, f"Unable to read file:\n{path}\n\n{exc}")
            return
        self.current_path = path
        self.current_bytes = data
        self._set_editor_text(decode_ascii_safe(data))
        self.render_bytes(path, data)

    def reload_current_file(self) -> None:
        if self.current_path is None or not self.current_path.exists():
            return
        self.load_file(self.current_path)

    def render_editor_content(self) -> None:
        self.render_after_id = None
        text = self.editor.get("1.0", "end-1c")
        data = text.replace("\r\n", "\n").replace("\r", "\n").encode("latin-1", errors="ignore")
        path = self.current_path if self.current_path is not None else Path("pasted_dpl.max")
        self.current_bytes = data
        self.render_bytes(path, data)

    def render_bytes(self, path: Path, data: bytes) -> None:
        try:
            parsed, image, preview_meta = render_from_bytes(
                path,
                data,
                self.current_size_override_mm(),
            )
        except Exception as exc:  # pragma: no cover - GUI error path
            self.current_parsed = None
            self.current_image = None
            self.preview_meta = {}
            self.preview_canvas.delete("all")
            self.source_var.set(f"Source: {path.name}")
            self.info_var.set(f"Parse failed: {exc}")
            return

        self.current_parsed = parsed
        self.current_image = image
        self.preview_meta = preview_meta
        self.update_size_fields_from_parsed(parsed)
        self.source_var.set(f"Source: {path}")
        profile = load_datamax_profile(path)
        if profile is None:
            self.profile_var.set("Printer profile: built-in Datamax I-4310e Mark II defaults")
        else:
            self.profile_var.set(
                "Printer profile: "
                f"{profile.firmware or PRINTER_MODEL} | "
                f"downloaded {profile.downloaded_font_summary}"
            )
        label_width, label_height = preview_meta["label_units"]  # type: ignore[assignment]
        canvas_width, canvas_height = preview_meta["canvas_units"]  # type: ignore[assignment]
        info_parts = [
            str(preview_meta.get("size_note") or parsed.label_size or "300 dpi canvas"),
            f"label {to_px(label_width)}x{to_px(label_height)} px",
            f"canvas {to_px(canvas_width)}x{to_px(canvas_height)} px",
        ]
        if preview_meta.get("overflow"):
            info_parts.append("overflow: content exceeds label bounds")
        if parsed.font_counts:
            info_parts.append(
                ", ".join(
                    f"{font}:{count}" for font, count in parsed.font_counts.most_common()
                )
            )
        if parsed.missing_graphics:
            info_parts.append("missing: " + ", ".join(sorted(parsed.missing_graphics)))
        self.info_var.set(" | ".join(info_parts))
        self.refresh_preview()

    def refresh_preview(self) -> None:
        if self.current_image is None:
            return
        canvas_w = max(1, self.preview_canvas.winfo_width())
        canvas_h = max(1, self.preview_canvas.winfo_height())
        image = self.current_image
        if self.zoom_mode.get() == "fit":
            scale = min(canvas_w / image.width, canvas_h / image.height)
            scale = max(scale, 0.1)
        else:
            scale = float(self.zoom_mode.get())
        resized = image.resize(
            (
                max(1, int(round(image.width * scale))),
                max(1, int(round(image.height * scale))),
            ),
            Image.Resampling.LANCZOS,
        )
        self.tk_image = ImageTk.PhotoImage(resized)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
        label_origin_x_units, label_origin_y_units = self.preview_meta.get(  # type: ignore[misc]
            "label_origin_units",
            (0, 0),
        )
        label_width_units, label_height_units = self.preview_meta.get(  # type: ignore[misc]
            "label_units",
            (0, 0),
        )
        boundary_x1 = int(round(label_origin_x_units * raster_scale() * scale))
        boundary_y1 = int(round(label_origin_y_units * raster_scale() * scale))
        boundary_x2 = boundary_x1 + int(round(label_width_units * raster_scale() * scale))
        boundary_y2 = boundary_y1 + int(round(label_height_units * raster_scale() * scale))
        self.preview_canvas.create_rectangle(
            boundary_x1,
            boundary_y1,
            max(boundary_x1 + 1, boundary_x2),
            max(boundary_y1 + 1, boundary_y2),
            outline=LABEL_BOUNDARY_COLOR,
            width=2,
            dash=(8, 6),
        )
        self.preview_canvas.configure(scrollregion=(0, 0, resized.width, resized.height))

    def save_svg(self) -> None:
        if self.current_parsed is None:
            return
        filename = filedialog.asksaveasfilename(
            title="Save preview SVG",
            defaultextension=".svg",
            filetypes=[("SVG files", "*.svg"), ("All files", "*.*")],
            initialfile=(self.current_path.stem if self.current_path else "preview") + ".svg",
        )
        if not filename:
            return
        svg = build_preview_svg(self.current_parsed)
        Path(filename).write_text(svg, encoding="utf-8")


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = PreviewViewerApp(root)
    app._update_size_entry_state()
    root.mainloop()


if __name__ == "__main__":
    main()
