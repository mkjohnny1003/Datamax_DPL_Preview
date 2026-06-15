# -*- coding: utf-8 -*-
"""Datamax DPL label preview generator.

Files are read as bytes so DPL control characters remain intact. The generated
HTML gallery and SVG files are intended for rapid visual inspection.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from hashlib import md5
from html import escape
from pathlib import Path
import argparse
import csv
import math
import re
import sys

try:
    import qrcode
except ImportError:
    qrcode = None

try:
    from barcode.codex import Code128, Code39
except ImportError:
    Code128 = None
    Code39 = None

try:
    from pystrich.datamatrix import DataMatrixEncoder
except ImportError:
    DataMatrixEncoder = None


PRINTER_DPI = 300
DPL_POSITION_UNITS_PER_INCH = 100
FONT_DOT_TO_POSITION = DPL_POSITION_UNITS_PER_INCH / PRINTER_DPI
DPL_UNITS_PER_MM = DPL_POSITION_UNITS_PER_INCH / 25.4
QR_PREVIEW_DATA = "ABC0123456789"
PRINTER_MODEL = "Datamax-O'Neil I-4310e Mark II"
PRINTER_MAX_MEDIA_WIDTH_MM = 118.1
PRINTER_MAX_PRINTABLE_WIDTH_MM = 105.7
PRINTER_UNPRINTABLE_RANGE_MM = 2.5

TEXT_S_RE = re.compile(
    r"^1911S(?P<font>\d{2})(?P<y>\d{4})(?P<x>\d{4})(?P<w>\d{4})(?P<h>\d{4})(?P<text>.*)$"
)
TEXT_A_RE = re.compile(
    r"^1911A(?P<font>\d{2})(?P<y>\d{4})(?P<x>\d{4})(?P<text>.*)$"
)
BARCODE_RE = re.compile(
    r"^(?P<rotation>[1-4])(?P<sym>[a-zA-Z])(?P<wide>[0-9A-Za-z])"
    r"(?P<narrow>[0-9A-Za-z])(?P<height>\d{3})(?P<y>\d{4})(?P<x>\d{4})(?P<rest>.*)$"
)
QR_RE = re.compile(
    r"^(?P<rotation>[1-4])W1(?P<type>[dD])"
    r"(?P<cell_x>[1-9A-Za-z])(?P<cell_y>[1-9A-Za-z])"
    r"(?P<height>\d{3})(?P<y>\d{4})(?P<x>\d{4})(?P<data>.*)$"
)
DATAMATRIX_RE = re.compile(
    r"^(?P<rotation>[1-4])W1(?P<type>[cC])"
    r"(?P<cell_x>[1-9A-Za-z])(?P<cell_y>[1-9A-Za-z])"
    r"(?P<height>\d{3})(?P<y>\d{4})(?P<x>\d{4})(?P<rest>.*)$"
)
LINE_RE = re.compile(
    r"^1X\d{6}(?P<y>\d{3})(?P<x>\d{4})l(?P<a>\d{4})(?P<b>\d{4})$"
)
BOX_RE = re.compile(
    r"^1X\d{6}(?P<y>\d{3})(?P<x>\d{4})B(?P<rest>\d+)$"
)
GRAPHIC_DEF_RE = re.compile(r"^(?:I[AC][AF])(?P<name>[A-Za-z0-9_]+)$")
GRAPHIC_CALL_RE = re.compile(
    r"^(?P<rotation>[1-4])Y(?P<wmul>[0-9A-Za-z])(?P<hmul>[0-9A-Za-z])000"
    r"(?P<y>\d{4})(?P<x>\d{4})(?P<name>[A-Za-z0-9_]+)$"
)
VARIABLE_RE = re.compile(r"^V(?P<index>\d+)=(?P<value>.*)$")
ANGLE_VAR_RE = re.compile(r"<([^>]+)>")
COLUMN_OFFSET_RE = re.compile(r"^C(?P<offset>\d{4})$")
ROW_OFFSET_RE = re.compile(r"^R(?P<offset>\d{4})$")
FILENAME_SIZE_RE = re.compile(r"(?<!\d)(?P<w>\d{2,3})\s*[xX]\s*(?P<h>\d{2,3})(?!\d)")
LABEL_PAPER_SIZE_RE = re.compile(r"(?P<w>\d{2,3})\s*[xX\*]\s*(?P<h>\d{2,3})")

A_FONT_HEIGHTS = {
    "03": 7,
    "04": 9,
    "05": 9,
    "06": 10,
    "08": 12,
    "10": 14,
    "12": 20,
    "14": 28,
    "18": 36,
}

FONT_STYLE_MAP = {
    "S00": {"family": "Arial Black, Arial, sans-serif", "weight": "900", "scale": 1.0},
    "S01": {"family": "Arial, sans-serif", "weight": "400", "scale": 0.82},
    "S50": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "S51": {"family": "Arial Black, Arial, sans-serif", "weight": "900", "scale": 1.0},
    "S52": {"family": "Arial Narrow, Arial, sans-serif", "weight": "400", "scale": 1.0},
    "S94": {"family": "'Times New Roman', Times, serif", "weight": "400", "scale": 1.0},
    "S95": {"family": "Arial Narrow, Arial, sans-serif", "weight": "700", "scale": 1.0},
    "S96": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "S97": {"family": "'Courier New', Courier, monospace", "weight": "400", "scale": 1.0},
    "S98": {"family": "Arial Black, Arial, sans-serif", "weight": "900", "scale": 1.0},
    "A05": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "A06": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "A08": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "A10": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "A12": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "A14": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
    "A18": {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0},
}

EXACT_SIZE_RULES_MM = {
    "MATERIALS_PASS": [(70.0, 30.0, "70x30 mm DSLabel rule")],
    "CGC_BOX_LABEL": [(85.0, 50.0, "85x50 mm DSLabel rule")],
    "CGC_CARTONEXTRA_LABEL": [(85.0, 50.0, "85x50 mm DSLabel rule")],
    "JI_BOX_LABEL": [(85.0, 50.0, "85x50 mm DSLabel rule")],
    "JI_CARTONEXTRA_LABEL": [(85.0, 50.0, "85x50 mm DSLabel rule")],
    "JI_TRAY_LABEL": [(100.0, 40.0, "100x40 mm DSLabel rule")],
}

GROUP_SIZE_RULES_MM = (
    (re.compile(r"WP_TRAY_LABEL_3N4", re.IGNORECASE), [(76.2, 101.6, "3x4 in DSLabel rule")]),
    (
        re.compile(r"WP_BOX_LABEL_LOTQTY", re.IGNORECASE),
        [
            (101.6, 101.6, "4x4 in DSLabel rule"),
            (101.6, 152.4, "4x6 in DSLabel rule"),
        ],
    ),
)
LABELINDEX_CSV_NAME = "labelindex.csv"
DATAMAX_PROFILE_DIR_NAME = "datamax"
_LABELINDEX_SIZE_CACHE: dict[Path, dict[str, list[tuple[int, int, str]]]] = {}
_DATAMAX_PROFILE_CACHE: dict[Path, "DatamaxPrinterProfile"] = {}

@dataclass
class LabelElement:
    kind: str
    x: int
    y: int
    w: int
    h: int
    text: str = ""
    font_code: str = ""
    command: str = ""
    font_px: int = 0
    meta: dict[str, str | int] = field(default_factory=dict)


@dataclass
class ParsedLabel:
    path: Path
    variables: dict[str, str] = field(default_factory=dict)
    elements: list[LabelElement] = field(default_factory=list)
    font_counts: Counter[str] = field(default_factory=Counter)
    q_code: str = ""
    graphics: dict[str, tuple[int, int, list[str]]] = field(default_factory=dict)
    missing_graphics: set[str] = field(default_factory=set)
    label_size: str = ""


@dataclass
class DatamaxPrinterProfile:
    source_dir: Path
    firmware: str = ""
    status_raw: str = ""
    downloaded_fonts: dict[str, str] = field(default_factory=dict)
    resident_scalable_fonts: dict[str, str] = field(default_factory=dict)
    module_contents: dict[str, list[str]] = field(default_factory=dict)

    @property
    def downloaded_font_summary(self) -> str:
        if not self.downloaded_fonts:
            return "none"
        return ", ".join(
            f"{code}={name}" for code, name in sorted(self.downloaded_fonts.items())
        )

    @property
    def resident_font_summary(self) -> str:
        if not self.resident_scalable_fonts:
            return "none"
        return ", ".join(
            f"{code}={name}" for code, name in sorted(self.resident_scalable_fonts.items())
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Datamax DPL label previews as an HTML/SVG gallery."
    )
    parser.add_argument("path", nargs="?", help="Input file or folder. Drag and drop is supported.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N files after sorting. 0 means all files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search files recursively when the input path is a folder.",
    )
    return parser.parse_args()


def prompt_for_input_path() -> str:
    return input("Enter a file or folder path: ").strip().strip('"')


def normalize_input_path(input_text: str | None) -> Path:
    if input_text:
        candidate = input_text.strip().strip('"')
    else:
        candidate = prompt_for_input_path()
    return Path(candidate).expanduser().resolve()


def is_target_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".txt", ".dpl", ".prn", ".max"}


def collect_target_files(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path] if is_target_file(input_path) else []

    iterator = input_path.rglob("*") if recursive else input_path.iterdir()
    files = [path for path in iterator if is_target_file(path)]
    blocked_names = {"DPL_Preview"}
    return [path for path in files if not any(part in blocked_names for part in path.parts)]


def decode_ascii_safe(data: bytes) -> str:
    return data.decode("latin-1", errors="ignore").replace("\r", "")


def expand_preview_text(text: str, variables: dict[str, str]) -> str:
    normalized_text = text.lower()
    variable_only = not ANGLE_VAR_RE.sub("", text).strip()
    top_mark_index = 0

    def sample_value(name: str) -> str:
        nonlocal top_mark_index
        normalized = name.strip().lower()
        if "today" in normalized or "date" in normalized:
            return "2026/03/25"
        if "qty" in normalized or "q'ty" in normalized or "figure" in normalized:
            return "9999"
        if "thk" in normalized_text or "thickness" in normalized_text:
            return "8"
        if normalized.startswith("patent7"):
            return "8"
        if "mpn" in normalized_text:
            return "MPN12345"
        if normalized.startswith("po_no"):
            return "PO12345"
        if normalized.startswith("top_mark"):
            if "qa" in normalized_text:
                return ""
            if variable_only:
                samples = ("01234", "56", "789")
                value = samples[min(top_mark_index, len(samples) - 1)]
                top_mark_index += 1
                return value
        return "0123456789"

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        source_name = variables.get(key, key)
        return sample_value(source_name)

    return ANGLE_VAR_RE.sub(repl, text).strip()


def parse_text_s(line: str, variables: dict[str, str]) -> LabelElement | None:
    match = TEXT_S_RE.match(line)
    if not match:
        return None
    font_code = f"S{match.group('font')}"
    text = expand_preview_text(match.group("text"), variables)
    char_height = int(match.group("w"))
    char_width = int(match.group("h"))
    render_height = max(3, int(round(char_height * FONT_DOT_TO_POSITION)))
    render_char_width = max(2, char_width * FONT_DOT_TO_POSITION)
    text_width = max(2, int(round(max(len(text), 1) * render_char_width)))
    return LabelElement(
        kind="text",
        x=int(match.group("x")),
        y=int(match.group("y")),
        w=text_width,
        h=render_height,
        text=text,
        font_code=font_code,
        command=line,
        font_px=render_height,
        meta={
            "char_height_dots": char_height,
            "char_width_dots": char_width,
        },
    )


def parse_text_a(line: str, variables: dict[str, str]) -> LabelElement | None:
    match = TEXT_A_RE.match(line)
    if not match:
        return None
    font_suffix = match.group("font")
    font_code = f"A{font_suffix}"
    height = A_FONT_HEIGHTS.get(font_suffix, 22)
    text = expand_preview_text(match.group("text"), variables)
    width = max(height, int(max(len(text), 1) * height * 0.56))
    return LabelElement(
        kind="text",
        x=int(match.group("x")),
        y=int(match.group("y")),
        w=width,
        h=height,
        text=text,
        font_code=font_code,
        command=line,
        font_px=height,
    )


def parse_barcode(line: str, variables: dict[str, str]) -> LabelElement | None:
    if line.startswith("1W1D") or line.startswith("1X"):
        return None
    match = BARCODE_RE.match(line)
    if not match:
        return None
    rest = expand_preview_text(match.group("rest"), variables)
    if rest.startswith(("A", "B")):
        rest = rest[1:]
    selector = match.group("sym")
    wide_dots = max(1, int(match.group("wide"), 36))
    narrow_dots = max(1, int(match.group("narrow"), 36))
    content = rest or "0123456789"
    width = estimate_barcode_width(selector, content, wide_dots, narrow_dots)
    height = max(1, int(match.group("height")))
    return LabelElement(
        kind="barcode",
        x=int(match.group("x")),
        y=int(match.group("y")),
        w=width,
        h=height,
        text=rest or "{BARCODE}",
        font_code=f"1{match.group('sym')}",
        command=line,
        meta={
            "selector": selector,
            "wide_dots": wide_dots,
            "narrow_dots": narrow_dots,
        },
    )


def estimate_barcode_width(selector: str, data: str, wide_dots: int, narrow_dots: int) -> int:
    runs = barcode_runs(selector, data, wide_dots, narrow_dots)
    if runs:
        width_dots = sum(run_width for _is_bar, run_width in runs)
    else:
        payload_len = max(1, len(data))
        avg_module_dots = max(1.0, (wide_dots + narrow_dots) / 2)
        width_dots = (payload_len * 14 + 30) * avg_module_dots
    width_units = width_dots * FONT_DOT_TO_POSITION
    return max(24, int(math.ceil(width_units)))


def run_lengths(bit_pattern: str) -> list[tuple[bool, int]]:
    if not bit_pattern:
        return []
    runs: list[tuple[bool, int]] = []
    current = bit_pattern[0]
    count = 0
    for bit in bit_pattern:
        if bit == current:
            count += 1
            continue
        runs.append((current == "1", count))
        current = bit
        count = 1
    runs.append((current == "1", count))
    return runs


def encoded_barcode_pattern(selector: str, data: str) -> str | None:
    try:
        if selector == "e" and Code128 is not None:
            return Code128(data).build()[0]
        if selector in {"a", "A", "h", "H"} and Code39 is not None:
            return Code39(data, add_checksum=False).build()[0]
    except Exception:
        return None
    return None


def barcode_runs(
    selector: str, data: str, wide_dots: int, narrow_dots: int
) -> list[tuple[bool, int]]:
    bit_pattern = encoded_barcode_pattern(selector, data)
    if not bit_pattern:
        return []

    raw_runs = run_lengths(bit_pattern)
    quiet_dots = 10 * narrow_dots
    scaled_runs: list[tuple[bool, int]] = [(False, quiet_dots)]
    module_dots = narrow_dots if wide_dots != narrow_dots else wide_dots

    for is_bar, count in raw_runs:
        if selector in {"a", "A", "h", "H"}:
            if count == 1:
                run_width = narrow_dots
            elif count == 3:
                run_width = wide_dots
            else:
                run_width = count * narrow_dots
        else:
            run_width = count * module_dots
        scaled_runs.append((is_bar, run_width))

    scaled_runs.append((False, quiet_dots))
    return scaled_runs


def parse_datamatrix(line: str, variables: dict[str, str]) -> LabelElement | None:
    qr_match = QR_RE.match(line)
    if qr_match:
        cell_x_dots = max(1, dpl_multiplier(qr_match.group("cell_x")))
        cell_y_dots = max(1, dpl_multiplier(qr_match.group("cell_y")))
        raw_data = qr_match.group("data")
        preview_data = expand_preview_text(raw_data, variables) or QR_PREVIEW_DATA
        modules = len(qr_matrix(preview_data))
        return LabelElement(
            kind="qrcode",
            x=int(qr_match.group("x")),
            y=int(qr_match.group("y")),
            w=max(1, int(round(modules * cell_x_dots * FONT_DOT_TO_POSITION))),
            h=max(1, int(round(modules * cell_y_dots * FONT_DOT_TO_POSITION))),
            text=preview_data,
            font_code=f"1W1{qr_match.group('type')}",
            command=line,
            meta={
                "rotation": int(qr_match.group("rotation")),
                "cell_x_dots": cell_x_dots,
                "cell_y_dots": cell_y_dots,
                "modules": modules,
            },
        )

    datamatrix_match = DATAMATRIX_RE.match(line)
    if not datamatrix_match:
        return None

    rest = datamatrix_match.group("rest")
    if datamatrix_match.group("type") == "C":
        if len(rest) < 14 or not rest[:14].isdigit():
            return None
        byte_count = int(rest[:4])
        header = rest[4:14]
        raw_data = rest[14 : 14 + byte_count]
    else:
        if len(rest) < 10 or not rest[:10].isdigit():
            return None
        byte_count = 0
        header = rest[:10]
        raw_data = rest[10:]

    ecc = int(header[:3])
    rows = int(header[4:7])
    columns = int(header[7:10])
    preview_data = expand_preview_text(raw_data, variables) or QR_PREVIEW_DATA
    matrix = datamatrix_matrix(preview_data)
    auto_modules = len(matrix)
    modules = max(rows, columns) if max(rows, columns) > 0 else auto_modules
    cell_x_dots = max(1, dpl_multiplier(datamatrix_match.group("cell_x")))
    cell_y_dots = max(1, dpl_multiplier(datamatrix_match.group("cell_y")))
    return LabelElement(
        kind="datamatrix",
        x=int(datamatrix_match.group("x")),
        y=int(datamatrix_match.group("y")),
        w=max(1, int(round(modules * cell_x_dots * FONT_DOT_TO_POSITION))),
        h=max(1, int(round(modules * cell_y_dots * FONT_DOT_TO_POSITION))),
        text=preview_data,
        font_code=f"1W1{datamatrix_match.group('type')}",
        command=line,
        meta={
            "rotation": int(datamatrix_match.group("rotation")),
            "cell_x_dots": cell_x_dots,
            "cell_y_dots": cell_y_dots,
            "modules": modules,
            "ecc": ecc,
            "rows": rows,
            "columns": columns,
            "byte_count": byte_count,
            "template_data": int("<" in raw_data or ">" in raw_data),
        },
    )


def parse_line_element(line: str) -> LabelElement | None:
    match = re.match(r"^1X\d{5}(?P<y>\d{4})(?P<x>\d{4})l(?P<a>\d{4})(?P<b>\d{4})$", line)
    if not match:
        return None
    x = int(match.group("x"))
    y = int(match.group("y"))
    a = int(match.group("a"))
    b = int(match.group("b"))
    if a >= b:
        return LabelElement("line", x=x, y=y, w=max(a, 1), h=max(b, 1), command=line)
    return LabelElement("line", x=x, y=y, w=max(a, 1), h=max(b, 1), command=line)


def parse_box_element(line: str) -> LabelElement | None:
    match = re.match(r"^1X\d{5}(?P<y>\d{4})(?P<x>\d{4})B(?P<rest>\d+)$", line)
    if not match:
        return None
    rest = match.group("rest")
    if len(rest) == 12:
        width = int(rest[0:3])
        height = int(rest[3:6])
    elif len(rest) >= 16:
        width = int(rest[0:4])
        height = int(rest[4:8])
    else:
        return None
    return LabelElement(
        kind="box",
        x=int(match.group("x")),
        y=int(match.group("y")),
        w=max(width, 1),
        h=max(height, 1),
        command=line,
    )


def is_hex_graphic_row(line: str) -> bool:
    return bool(line) and all(ch in "0123456789ABCDEF" for ch in line)


def decode_graphic_rows(rows: list[str]) -> tuple[int, list[str]]:
    expanded_rows: list[str] = []
    row_width = 0
    previous_row = ""

    for row in rows:
        if row == "FFFF":
            break
        if row.startswith("0000FF") and len(row) == 8 and previous_row:
            repeat_count = int(row[6:8], 16)
            expanded_rows.extend([previous_row] * repeat_count)
            continue
        if not row.startswith("80") or len(row) < 4:
            continue

        pair_count = int(row[2:4], 16)
        bitmap_hex = row[4:]
        expected_length = pair_count * 2
        if len(bitmap_hex) < expected_length:
            continue

        bitmap_hex = bitmap_hex[:expected_length]
        previous_row = bitmap_hex
        expanded_rows.append(bitmap_hex)
        row_width = max(row_width, pair_count * 8)

    return row_width, expanded_rows


def graphic_name_aliases(name: str) -> list[str]:
    aliases: list[str] = []
    for candidate in (name, name.lstrip("F")):
        if candidate and candidate not in aliases:
            aliases.append(candidate)
    return aliases


def dpl_multiplier(value: str) -> int:
    if "0" <= value <= "9":
        return int(value)
    if "A" <= value <= "Z":
        return ord(value) - ord("A") + 10
    if "a" <= value <= "z":
        return ord(value) - ord("a") + 36
    return 1


def store_graphic(parsed: ParsedLabel, name: str, rows: list[str]) -> None:
    if not rows:
        return
    row_width, expanded_rows = decode_graphic_rows(rows)
    if not expanded_rows:
        return
    payload = (row_width, len(expanded_rows), expanded_rows)
    for alias in graphic_name_aliases(name):
        parsed.graphics[alias] = payload


def resolve_graphic(
    name: str, graphics: dict[str, tuple[int, int, list[str]]]
) -> tuple[int, int, list[str]] | None:
    for alias in graphic_name_aliases(name):
        if alias in graphics:
            return graphics[alias]
    return None


def parse_graphic_call(line: str, parsed: ParsedLabel) -> LabelElement | None:
    match = GRAPHIC_CALL_RE.match(line)
    if not match:
        return None
    name = match.group("name")
    graphic = resolve_graphic(name, parsed.graphics)
    width_multiplier = max(1, dpl_multiplier(match.group("wmul")))
    height_multiplier = max(1, dpl_multiplier(match.group("hmul")))
    if graphic is not None:
        width_bits, height_rows, _rows = graphic
        width = max(1, int(round(width_bits * width_multiplier * FONT_DOT_TO_POSITION)))
        height = max(1, int(round(height_rows * height_multiplier * FONT_DOT_TO_POSITION)))
    else:
        parsed.missing_graphics.add(name)
        width = 72 * width_multiplier
        height = 36 * height_multiplier
    return LabelElement(
        kind="graphic",
        x=int(match.group("x")),
        y=int(match.group("y")),
        w=width,
        h=height,
        text=name,
        command=line,
    )


def parse_dpl_preview(path: Path, data: bytes) -> ParsedLabel:
    parsed = ParsedLabel(path=path)
    lines = decode_ascii_safe(data).split("\n")
    has_start_marker = any(line.strip().upper() == "[START]" for line in lines)
    in_header = has_start_marker
    active_graphic_name: str | None = None
    active_graphic_rows: list[str] = []
    column_offset = 0
    row_offset = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if active_graphic_name and active_graphic_rows:
                store_graphic(parsed, active_graphic_name, active_graphic_rows)
                active_graphic_name = None
                active_graphic_rows = []
            continue

        if line == "[Start]":
            in_header = False
            continue

        if in_header:
            variable_match = VARIABLE_RE.match(line)
            if variable_match:
                parsed.variables[f"V{variable_match.group('index')}"] = variable_match.group("value").strip()
            continue

        if line.startswith("\x02q") and len(line) >= 3:
            parsed.q_code = line[2:]

        normalized = line.lstrip("\x02")

        column_offset_match = COLUMN_OFFSET_RE.match(normalized)
        if column_offset_match:
            column_offset = int(column_offset_match.group("offset"))
            continue
        row_offset_match = ROW_OFFSET_RE.match(normalized)
        if row_offset_match:
            row_offset = int(row_offset_match.group("offset"))
            continue

        if active_graphic_name:
            if is_hex_graphic_row(normalized):
                active_graphic_rows.append(normalized)
                continue
            if active_graphic_rows:
                store_graphic(parsed, active_graphic_name, active_graphic_rows)
            active_graphic_name = None
            active_graphic_rows = []

        graphic_match = GRAPHIC_DEF_RE.match(normalized)
        if graphic_match:
            active_graphic_name = graphic_match.group("name")
            active_graphic_rows = []
            continue

        element = (
            parse_text_s(normalized, parsed.variables)
            or parse_text_a(normalized, parsed.variables)
            or parse_datamatrix(normalized, parsed.variables)
            or parse_line_element(normalized)
            or parse_box_element(normalized)
            or parse_graphic_call(normalized, parsed)
            or parse_barcode(normalized, parsed.variables)
        )
        if element is None:
            continue
        element.x += column_offset
        element.y += row_offset
        parsed.elements.append(element)
        if element.font_code:
            parsed.font_counts[element.font_code] += 1

    if active_graphic_name and active_graphic_rows:
        store_graphic(parsed, active_graphic_name, active_graphic_rows)

    return parsed


def estimate_canvas_size(parsed: ParsedLabel) -> tuple[int, int, int, int]:
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

    content_width = width - min_x
    content_height = height - min_y
    override = infer_label_canvas(parsed.path, content_width, content_height)
    if override is None:
        parsed.label_size = "300 dpi canvas"
        return content_width, content_height, min_x, min_y

    page_width, page_height, note = override
    parsed.label_size = note
    return page_width, page_height, min_x, min_y


def infer_label_canvas(
    path: Path, content_width: int, content_height: int
) -> tuple[int, int, str] | None:
    candidates = label_size_candidates(path)
    if not candidates:
        return None

    chosen_width, chosen_height, note = min(
        candidates,
        key=lambda item: (
            max(0, content_width - item[0]) + max(0, content_height - item[1]),
            item[0] * item[1],
        ),
    )
    page_width = max(content_width, chosen_width)
    page_height = max(content_height, chosen_height)
    if page_width != chosen_width or page_height != chosen_height:
        note = f"{note}; expanded to fit content"
    return page_width, page_height, note


def label_size_candidates(path: Path) -> list[tuple[int, int, str]]:
    normalized = normalize_label_name(path)
    candidates: list[tuple[int, int, str]] = []

    candidates.extend(labelindex_size_candidates(path))

    for width_mm, height_mm, note in EXACT_SIZE_RULES_MM.get(normalized, []):
        candidates.append((mm_to_units(width_mm), mm_to_units(height_mm), note))

    for pattern, group_candidates in GROUP_SIZE_RULES_MM:
        if pattern.search(normalized):
            for width_mm, height_mm, note in group_candidates:
                candidates.append((mm_to_units(width_mm), mm_to_units(height_mm), note))

    token_match = FILENAME_SIZE_RE.search(path.stem)
    if token_match:
        width_mm = float(token_match.group("w"))
        height_mm = float(token_match.group("h"))
        candidates.append(
            (
                mm_to_units(width_mm),
                mm_to_units(height_mm),
                f"{token_match.group('w')}x{token_match.group('h')} mm filename rule",
            )
        )

    return dedupe_size_candidates(candidates)


def labelindex_size_candidates(path: Path) -> list[tuple[int, int, str]]:
    labelindex_sizes = load_labelindex_size_map(path)
    return list(labelindex_sizes.get(path.name.upper(), []))


def load_labelindex_size_map(path: Path) -> dict[str, list[tuple[int, int, str]]]:
    csv_path = find_labelindex_csv(path)
    if csv_path is None:
        return {}
    cached = _LABELINDEX_SIZE_CACHE.get(csv_path)
    if cached is not None:
        return cached

    text = csv_path.read_bytes().decode("cp950", errors="replace")
    rows = csv.DictReader(text.splitlines())
    mapping: dict[str, list[tuple[int, int, str]]] = {}
    for row in rows:
        label_file = row.get("labelFile", "").strip()
        label_paper = row.get("LabelPaper", "").strip()
        if not label_file or not label_paper or not label_file.upper().endswith(".MAX"):
            continue
        sizes = extract_label_paper_sizes(label_paper)
        if not sizes:
            continue
        key = Path(label_file).name.upper()
        mapping.setdefault(key, [])
        for width_mm, height_mm in sizes:
            mapping[key].append(
                (
                    mm_to_units(width_mm),
                    mm_to_units(height_mm),
                    f"{width_mm:g}x{height_mm:g} mm labelindex.csv",
                )
            )

    deduped = {
        key: dedupe_size_candidates(value)
        for key, value in mapping.items()
    }
    _LABELINDEX_SIZE_CACHE[csv_path] = deduped
    return deduped


def find_labelindex_csv(path: Path) -> Path | None:
    candidate_roots = [
        path.parent if path.is_file() else path,
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent.parent,
        Path.cwd(),
    ]
    executable = Path(sys.executable).resolve()
    candidate_roots.extend([executable.parent, executable.parent.parent])
    seen: set[Path] = set()
    for root in candidate_roots:
        if root in seen:
            continue
        seen.add(root)
        candidate = root / LABELINDEX_CSV_NAME
        if candidate.exists():
            return candidate.resolve()
    return None


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="latin-1", errors="replace").replace("\r", "")


def parse_module_listing(text: str) -> dict[str, list[str]]:
    module_contents: dict[str, list[str]] = {}
    current_module = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Module: "):
            current_module = line.split(":", 1)[1].strip()
            module_contents.setdefault(current_module, [])
            continue
        if line.startswith("Available Bytes:"):
            continue
        if current_module:
            module_contents.setdefault(current_module, []).append(line)
    return module_contents


def parse_resident_scalable_fonts(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("S"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        mapping[parts[0]] = parts[1].strip()
    return mapping


def find_datamax_profile_dir(path: Path) -> Path | None:
    candidate_roots = [
        path.parent if path.is_file() else path,
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent.parent,
        Path.cwd(),
    ]
    executable = Path(sys.executable).resolve()
    candidate_roots.extend([executable.parent, executable.parent.parent])
    seen: set[Path] = set()
    for root in candidate_roots:
        if root in seen:
            continue
        seen.add(root)
        candidate = root / DATAMAX_PROFILE_DIR_NAME
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return None


def load_datamax_profile(path: Path) -> DatamaxPrinterProfile | None:
    profile_dir = find_datamax_profile_dir(path)
    if profile_dir is None:
        return None
    cached = _DATAMAX_PROFILE_CACHE.get(profile_dir)
    if cached is not None:
        return cached

    profile = DatamaxPrinterProfile(source_dir=profile_dir)
    downloaded_text = read_text_if_exists(profile_dir / "datamax_Downloaded_fonts_STXWF.txt")
    resident_text = read_text_if_exists(profile_dir / "datamax_Resident_fonts_STXWf.txt")
    all_memory_text = read_text_if_exists(profile_dir / "datamax_All_memory_contents_STXWALL.txt")
    firmware_text = read_text_if_exists(profile_dir / "datamax_Firmware_STXv.txt")
    status_text = read_text_if_exists(profile_dir / "datamax_Status_SOHA.txt")

    profile.firmware = firmware_text.strip()
    profile.status_raw = status_text.strip()
    downloaded_fonts: dict[str, str] = {}
    for entry in parse_module_listing(downloaded_text).get("G", []):
        parts = entry.split(None, 1)
        if len(parts) != 2:
            continue
        downloaded_fonts[parts[0].strip()] = parts[1].strip()
    profile.downloaded_fonts = downloaded_fonts
    profile.resident_scalable_fonts = parse_resident_scalable_fonts(resident_text)
    profile.module_contents = parse_module_listing(all_memory_text)

    _DATAMAX_PROFILE_CACHE[profile_dir] = profile
    return profile


def profile_font_overrides(profile: DatamaxPrinterProfile | None) -> dict[str, dict[str, str | float]]:
    if profile is None:
        return {}

    overrides: dict[str, dict[str, str | float]] = {}
    for font_code, font_name in profile.downloaded_fonts.items():
        name = font_name.lower()
        if "arialblack" in name:
            overrides[font_code] = {"family": "Arial Black, Arial, sans-serif", "weight": "900", "scale": 1.0}
        elif "arialnarrowb" in name:
            overrides[font_code] = {"family": "Arial Narrow, Arial, sans-serif", "weight": "700", "scale": 1.0}
        elif "arialnarrow" in name:
            overrides[font_code] = {"family": "Arial Narrow, Arial, sans-serif", "weight": "400", "scale": 1.0}
        elif "timesnewroma" in name or "timesnewroman" in name:
            overrides[font_code] = {"family": "'Times New Roman', Times, serif", "weight": "400", "scale": 1.0}
        elif "courier" in name:
            overrides[font_code] = {"family": "'Courier New', Courier, monospace", "weight": "400", "scale": 1.0}
        elif "arial" in name:
            overrides[font_code] = {"family": "Arial, sans-serif", "weight": "400", "scale": 1.0}
    return overrides


def extract_label_paper_sizes(label_paper: str) -> list[tuple[float, float]]:
    sizes: list[tuple[float, float]] = []
    for match in LABEL_PAPER_SIZE_RE.finditer(label_paper):
        size = (float(match.group("w")), float(match.group("h")))
        if size not in sizes:
            sizes.append(size)
    return sizes


def normalize_label_name(path: Path) -> str:
    return path.stem.upper().replace(" ", "").replace("-", "_")


def mm_to_units(value_mm: float) -> int:
    return max(1, int(round(value_mm * DPL_UNITS_PER_MM)))


def dedupe_size_candidates(
    candidates: list[tuple[int, int, str]]
) -> list[tuple[int, int, str]]:
    seen: set[tuple[int, int, str]] = set()
    unique: list[tuple[int, int, str]] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def font_style(
    font_code: str,
    profile: DatamaxPrinterProfile | None = None,
) -> dict[str, str | float]:
    overrides = profile_font_overrides(profile)
    if font_code in overrides:
        return overrides[font_code]
    return FONT_STYLE_MAP.get(
        font_code,
        {"family": "Arial, sans-serif", "weight": "700", "scale": 1.0},
    )


def svg_bar_pattern(width: int, height: int, seed_text: str) -> str:
    digest = md5(seed_text.encode("utf-8")).digest()
    bars: list[str] = []
    x = 4
    index = 0
    while x < width - 4:
        value = digest[index % len(digest)]
        bar_w = 1 + (value % 4)
        gap = 1 + ((value // 4) % 3)
        bars.append(f"<rect x='{x}' y='4' width='{bar_w}' height='{height - 8}' fill='#111111' />")
        x += bar_w + gap
        index += 1
    return "".join(bars)


def svg_barcode_runs(width: int, height: int, runs: list[tuple[bool, int]]) -> str:
    if not runs:
        return ""
    total_dots = sum(run_width for _is_bar, run_width in runs)
    if total_dots <= 0:
        return ""

    scale_x = width / total_dots
    parts: list[str] = []
    cursor = 0.0
    inner_y = max(0.0, height * 0.06)
    inner_h = max(1.0, height * 0.88)
    for is_bar, run_width in runs:
        draw_width = run_width * scale_x
        if is_bar and draw_width > 0:
            parts.append(
                f"<rect x='{cursor:.3f}' y='{inner_y:.3f}' width='{draw_width:.3f}' height='{inner_h:.3f}' fill='#111111' />"
            )
        cursor += draw_width
    return "".join(parts)


def svg_matrix_pattern(width: int, height: int, seed_text: str) -> str:
    digest = md5(seed_text.encode("utf-8")).digest()
    cell = max(4, min(9, width // 18))
    cols = max(8, width // cell)
    rows = max(8, height // cell)
    parts: list[str] = []
    for row in range(rows):
        for col in range(cols):
            value = digest[(row * cols + col) % len(digest)]
            if (value + row + col) % 3 == 0:
                parts.append(
                    f"<rect x='{col * cell}' y='{row * cell}' width='{cell}' height='{cell}' fill='#111111' />"
                )
    return "".join(parts)


def qr_matrix(data: str) -> list[list[bool]]:
    if qrcode is not None:
        qr = qrcode.QRCode(border=0)
        qr.add_data(data)
        qr.make(fit=True)
        return qr.get_matrix()

    # Fallback QR-like matrix with finder patterns when qrcode is unavailable.
    size = 21
    digest = md5(data.encode("utf-8")).digest()
    matrix = [[False for _ in range(size)] for _ in range(size)]

    def place_finder(top: int, left: int) -> None:
        for r in range(7):
            for c in range(7):
                rr = top + r
                cc = left + c
                on = r in {0, 6} or c in {0, 6} or (2 <= r <= 4 and 2 <= c <= 4)
                matrix[rr][cc] = on

    place_finder(0, 0)
    place_finder(0, size - 7)
    place_finder(size - 7, 0)

    for row in range(size):
        for col in range(size):
            in_finder = (
                (row < 7 and col < 7)
                or (row < 7 and col >= size - 7)
                or (row >= size - 7 and col < 7)
            )
            if in_finder:
                continue
            value = digest[(row * size + col) % len(digest)]
            matrix[row][col] = ((value + row + col) % 2) == 0
    return matrix


def datamatrix_matrix(data: str) -> list[list[bool]]:
    if DataMatrixEncoder is not None:
        try:
            matrix = DataMatrixEncoder(data).matrix
            return [[bool(cell) for cell in row] for row in matrix]
        except Exception:
            pass
    return [[bool((row + col) % 2) for col in range(10)] for row in range(10)]


def svg_binary_matrix_pattern(
    width: int, height: int, matrix: list[list[bool]]
) -> str:
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    if not rows or not cols:
        return ""
    scale_x = width / cols
    scale_y = height / rows
    parts: list[str] = []
    for row_idx, row in enumerate(matrix):
        for col_idx, on in enumerate(row):
            if on:
                parts.append(
                    f"<rect x='{col_idx * scale_x:.3f}' y='{row_idx * scale_y:.3f}' "
                    f"width='{scale_x:.3f}' height='{scale_y:.3f}' fill='#111111' />"
                )
    return "".join(parts)


def svg_qr_pattern(width: int, height: int, data: str) -> str:
    return svg_binary_matrix_pattern(width, height, qr_matrix(data))


def svg_graphic_pattern(rows: list[str], scale: int) -> str:
    parts: list[str] = []
    # DPL image rows are stored from the printer's bottom-origin perspective.
    for row_index, row in enumerate(reversed(rows)):
        for col_nibble, nibble in enumerate(row):
            value = int(nibble, 16)
            for bit in range(4):
                if value & (1 << (3 - bit)):
                    x = (col_nibble * 4 + bit) * scale
                    y = row_index * scale
                    parts.append(
                        f"<rect x='{x}' y='{y}' width='{scale}' height='{scale}' fill='#111111' />"
                    )
    return "".join(parts)


def containing_box(
    element: LabelElement, boxes: list[LabelElement] | None
) -> LabelElement | None:
    if not boxes or element.kind != "text":
        return None

    candidates = [
        box
        for box in boxes
        if box.x <= element.x <= box.x + box.w
        and box.y <= element.y
        and element.y + element.h <= box.y + box.h + 2
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda box: box.w * box.h)


def render_element_svg(
    element: LabelElement,
    graphics: dict[str, tuple[int, int, list[str]]] | None = None,
    canvas_height: int = 0,
    show_guides: bool = False,
    boxes: list[LabelElement] | None = None,
    profile: DatamaxPrinterProfile | None = None,
) -> str:
    x = element.x
    y = canvas_height - element.y - element.h

    if element.kind == "line":
        if element.w >= element.h:
            return (
                f"<rect x='{x}' y='{y}' width='{max(element.w, 1)}' "
                f"height='{max(element.h, 1)}' fill='#111111' />"
            )
        return (
            f"<rect x='{x}' y='{y}' width='{max(element.w, 1)}' "
            f"height='{max(element.h, 1)}' fill='#111111' />"
        )

    if element.kind == "box":
        return (
            f"<rect x='{x}' y='{y}' width='{element.w}' height='{element.h}' "
            f"fill='none' stroke='#111111' stroke-width='1.2' />"
        )

    if element.kind == "barcode":
        selector = str(element.meta.get("selector", ""))
        wide_dots = int(element.meta.get("wide_dots", 2))
        narrow_dots = int(element.meta.get("narrow_dots", 2))
        runs = barcode_runs(selector, element.text, wide_dots, narrow_dots)
        bars = svg_barcode_runs(element.w, element.h, runs)
        if not bars:
            bars = svg_bar_pattern(element.w, element.h, element.text + element.command)
        return (
            f"<g>"
            f"<g transform='translate({x},{y})'>{bars}</g>"
            f"</g>"
        )

    if element.kind == "qrcode":
        matrix = svg_qr_pattern(element.w, element.h, element.text)
        return (
            f"<g>"
            f"<g transform='translate({x},{y})'>{matrix}</g>"
            f"</g>"
        )

    if element.kind == "datamatrix":
        matrix = svg_binary_matrix_pattern(
            element.w, element.h, datamatrix_matrix(element.text)
        )
        return f"<g transform='translate({x},{y})'>{matrix}</g>"

    if element.kind == "graphic":
        graphic = resolve_graphic(element.text, graphics or {})
        if graphic is not None:
            width_bits, height_rows, rows = graphic
            scale_x = element.w / max(width_bits, 1)
            scale_y = element.h / max(height_rows, 1)
            return (
                f"<g>"
                f"<g transform='translate({x},{y}) scale({scale_x:.4f},{scale_y:.4f})'>"
                f"{svg_graphic_pattern(rows, 1)}</g>"
                f"</g>"
            )
        return ""

    font_code = element.font_code
    style = font_style(font_code, profile)
    font_size = element.font_px or max(8, int(element.h * 0.82))
    render_height = font_size + 2
    y = canvas_height - element.y - render_height
    baseline_y = y + font_size
    text_value = escape(element.text) if element.text else " "
    width_scale = 1.0
    char_height_dots = int(element.meta.get("char_height_dots", 0))
    char_width_dots = int(element.meta.get("char_width_dots", 0))
    if char_height_dots > 0 and char_width_dots > 0:
        width_scale = char_width_dots / char_height_dots
    width_scale *= float(style.get("scale", 1.0))
    box = containing_box(element, boxes)
    if box is not None:
        horizontal_padding = 2
        available_width = max(1, box.w - horizontal_padding * 2)
        rendered_width = max(1.0, element.w * width_scale)
        width_scale *= min(1.0, available_width / rendered_width)
    note = font_code
    note = f"{note} {font_size}px {element.w}x{element.h}"
    guide = ""
    if show_guides:
        guide = (
            f"<rect x='{x}' y='{y}' width='{element.w}' height='{element.h}' "
            f"fill='none' stroke='#cfd4dc' stroke-width='0.6' />"
            f"<text x='{x}' y='{max(y - 2, 10)}' font-size='8' fill='#7a8594' "
            f"font-family='Consolas, monospace'>{escape(note)}</text>"
        )
    return (
        f"<g>"
        f"{guide}"
        f"<text x='0' y='{baseline_y}' "
        f"font-size='{font_size}' font-family=\"{style['family']}\" font-weight='{style['weight']}' "
        f"transform='translate({x + 1},0) scale({width_scale:.4f},1)'>{text_value}</text>"
        f"</g>"
    )

def build_preview_svg(parsed: ParsedLabel) -> str:
    profile = load_datamax_profile(parsed.path)
    label_width, label_height, _min_x, _min_y = estimate_canvas_size(parsed)
    boxes = [element for element in parsed.elements if element.kind == "box"]
    page_w = label_width
    page_h = label_height
    raster_scale = PRINTER_DPI / DPL_POSITION_UNITS_PER_INCH
    output_w = int(round(page_w * raster_scale))
    output_h = int(round(page_h * raster_scale))

    left_parts: list[str] = []
    for element in parsed.elements:
        left_parts.append(
            render_element_svg(
                element,
                graphics=parsed.graphics,
                canvas_height=label_height,
                boxes=boxes,
                profile=profile,
            )
        )

    svg = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{output_w}' height='{output_h}' viewBox='0 0 {page_w} {page_h}'>"
        "<style>text { fill: #111111; dominant-baseline: alphabetic; }</style>"
        f"<g>"
        f"<rect x='0' y='0' width='{label_width}' height='{label_height}' fill='#ffffff' stroke='#c7ccd4' stroke-width='1' />"
        f"{''.join(left_parts)}"
        "</g>"
        "</svg>"
    )
    return svg


def profile_note_html(profile: DatamaxPrinterProfile | None) -> str:
    if profile is None:
        return "<p class='note'>Printer profile data folder not found. Rendering uses the built-in Datamax I-4310e Mark II defaults.</p>"
    firmware = escape(profile.firmware or "unknown")
    status_raw = escape(profile.status_raw or "unknown")
    downloaded = escape(profile.downloaded_font_summary)
    resident = escape(profile.resident_font_summary)
    profile_dir = escape(str(profile.source_dir))
    return (
        "<details class='profile' open>"
        "<summary>Loaded printer profile from Datamax I-4310e Mark II</summary>"
        f"<div class='profile-line'>Source: {profile_dir}</div>"
        f"<div class='profile-line'>Firmware: {firmware}</div>"
        f"<div class='profile-line'>Status raw: {status_raw}</div>"
        f"<div class='profile-line'>Downloaded fonts: {downloaded}</div>"
        f"<div class='profile-line'>Resident scalable fonts: {resident}</div>"
        "</details>"
    )


def write_preview_outputs(input_root: Path, files: list[Path]) -> Path:
    output_dir = input_root / "DPL_Preview"
    svg_dir = output_dir / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)
    profile = load_datamax_profile(input_root)

    rows: list[str] = []
    rows.append("<!DOCTYPE html><html><head><meta charset='utf-8'><title>DPL Preview</title>")
    rows.append(
        "<style>"
        "body{font-family:Arial,sans-serif;background:#e9ecef;color:#111;margin:20px;}"
        ".toolbar{position:sticky;top:0;background:#e9ecef;padding:0 0 14px;z-index:2;}"
        "input{width:min(520px,90vw);padding:10px 12px;border:1px solid #adb5bd;border-radius:6px;font-size:16px;}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:14px;}"
        ".card{background:#fff;border:1px solid #cfd4da;border-radius:7px;padding:10px;overflow:hidden;}"
        ".name{font:700 13px Consolas,monospace;margin-bottom:8px;}"
        ".fonts{font:11px Consolas,monospace;color:#59636e;margin-top:7px;}"
        ".note{max-width:1320px;line-height:1.45;}"
        ".profile{max-width:1320px;background:#fff;border:1px solid #cfd4da;border-radius:7px;padding:10px 12px;margin:10px 0 14px;}"
        ".profile summary{cursor:pointer;font-weight:700;}"
        ".profile-line{font:12px Consolas,monospace;color:#37414c;margin-top:6px;word-break:break-word;}"
        ".preview{height:260px;display:flex;align-items:center;justify-content:center;"
        "overflow:hidden;border:1px solid #ddd;background:#fff;}"
        "img{display:block;max-width:100%;max-height:100%;width:auto;height:auto;}"
        "a{color:#1659d0;text-decoration:none;}"
        "</style></head><body>"
    )
    rows.append("<div class='toolbar'><h1>DPL Label Preview</h1>")
    rows.append("<input id='filter' type='search' placeholder='Filter by file name...' oninput='filterCards(this.value)'></div>")
    rows.append(
        "<p class='note'>This view shows the original DPL label layout. "
        f"Printer profile: {escape(PRINTER_MODEL)}, {PRINTER_DPI} dpi, "
        f"maximum media width {PRINTER_MAX_MEDIA_WIDTH_MM} mm, maximum printable width "
        f"{PRINTER_MAX_PRINTABLE_WIDTH_MM} mm, driver unprintable range "
        f"{PRINTER_UNPRINTABLE_RANGE_MM} mm. The driver's current 103.5 x 152.4 mm "
        "user stock is not forced onto formats that do not declare that size.</p>"
    )
    rows.append(profile_note_html(profile))
    rows.append("<div class='grid'>")

    for file_path in files:
        data = file_path.read_bytes()
        parsed = parse_dpl_preview(file_path, data)
        svg_path = svg_dir / f"{file_path.stem}.svg"
        svg_content = build_preview_svg(parsed)
        svg_path.write_text(svg_content, encoding="utf-8")
        preview_version = md5(svg_content.encode("utf-8")).hexdigest()[:10]
        preview_width, preview_height, _min_x, _min_y = estimate_canvas_size(parsed)
        raster_scale = PRINTER_DPI / DPL_POSITION_UNITS_PER_INCH
        preview_dot_width = int(round(preview_width * raster_scale))
        preview_dot_height = int(round(preview_height * raster_scale))
        font_summary = ", ".join(f"{font}:{count}" for font, count in parsed.font_counts.most_common())
        note = "Original DPL preview"
        if parsed.missing_graphics:
            missing = ", ".join(sorted(parsed.missing_graphics))
            note = f"{note}; missing graphic: {missing}"
        rows.append(
            f"<div class='card' data-name='{escape(file_path.name.lower())}'>"
            f"<div class='name'><a href='svg/{escape(svg_path.name)}'>{escape(file_path.name)}</a></div>"
            f"<a class='preview' href='svg/{escape(svg_path.name)}'>"
            f"<img loading='lazy' src='svg/{escape(svg_path.name)}?v={preview_version}' "
            f"alt='{escape(file_path.name)}'></a>"
            f"<div class='fonts'>{escape(parsed.label_size)} ({preview_dot_width}x{preview_dot_height} dots) | "
            f"{escape(font_summary or 'none')} | {escape(note)}</div>"
            "</div>"
        )

    rows.append(
        "</div><script>"
        "function filterCards(value){const q=value.toLowerCase();"
        "document.querySelectorAll('.card').forEach(c=>c.hidden=!c.dataset.name.includes(q));}"
        "</script></body></html>"
    )
    (output_dir / "index.html").write_text("".join(rows), encoding="utf-8")
    return output_dir


def main() -> int:
    args = parse_args()
    input_path = normalize_input_path(args.path)

    if not input_path.exists():
        print(f"Input path not found: {input_path}")
        return 1

    files = sorted(collect_target_files(input_path, recursive=args.recursive))
    if args.limit > 0:
        files = files[: args.limit]

    if not files:
        print("No supported files found. Supported extensions: .max .txt .dpl .prn")
        return 1

    preview_root = input_path if input_path.is_dir() else input_path.parent
    output_dir = write_preview_outputs(preview_root, files)
    print(f"Previewed files: {len(files)}")
    print(f"Preview folder: {output_dir}")
    print(f"Open: {output_dir / 'index.html'}")
    print("Reminder: use this preview for screening only, then print real samples and scan-verify 1D / 2D codes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
