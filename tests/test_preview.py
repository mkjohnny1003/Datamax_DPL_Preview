from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datamax_dpl_preview import (
    LabelElement,
    ParsedLabel,
    barcode_runs,
    datamatrix_matrix,
    decode_graphic_rows,
    estimate_barcode_width,
    estimate_canvas_size,
    extract_label_paper_sizes,
    font_style,
    label_size_candidates,
    load_datamax_profile,
    mm_to_units,
    parse_datamatrix,
    parse_dpl_preview,
    parse_graphic_call,
    render_element_svg,
    expand_preview_text,
)


class GraphicRowTests(unittest.TestCase):
    def test_datamax_ascii_graphic_rows_expand_repeat_and_trim_width(self) -> None:
        width, rows = decode_graphic_rows(
            [
                "800200F0FFFF",
                "0000FF02",
                "8002000F1234",
                "FFFF",
            ]
        )

        self.assertEqual(width, 16)
        self.assertEqual(rows, ["00F0", "00F0", "00F0", "000F"])

    def test_graphic_call_uses_dpl_multipliers_and_full_row_column(self) -> None:
        parsed = ParsedLabel(path=Path("dummy.MAX"))
        parsed.graphics["F97082DD"] = (64, 28, ["F" * 16] * 28)
        element = parse_graphic_call("1Y1100000070162F97082DD", parsed)

        self.assertIsNotNone(element)
        assert element is not None
        self.assertEqual(element.x, 162)
        self.assertEqual(element.y, 7)
        self.assertEqual(element.w, 21)
        self.assertEqual(element.h, 9)


class BarcodeWidthTests(unittest.TestCase):
    def test_code128_width_grows_with_content(self) -> None:
        short_width = estimate_barcode_width("e", "1234", 2, 1)
        long_width = estimate_barcode_width("e", "123456789012", 2, 1)

        self.assertGreater(long_width, short_width)

    def test_code39_uses_wide_and_narrow_dots(self) -> None:
        narrow_width = estimate_barcode_width("A", "0123456789", 2, 1)
        wider_width = estimate_barcode_width("A", "0123456789", 3, 1)

        self.assertGreater(wider_width, narrow_width)

    def test_code128_generates_real_bar_runs(self) -> None:
        runs = barcode_runs("e", "0123456789", 2, 2)

        self.assertTrue(runs)
        self.assertTrue(any(is_bar for is_bar, _run_width in runs))


class TwoDimensionalBarcodeTests(unittest.TestCase):
    def test_qr_uses_dpl_module_size_and_lower_left_position(self) -> None:
        element = parse_datamatrix(
            "1W1D3300001100346B00T<V6>,C<V10>,L<V7>,Q<QTY>",
            {},
        )

        self.assertIsNotNone(element)
        assert element is not None
        self.assertEqual(element.kind, "qrcode")
        self.assertEqual((element.x, element.y), (346, 110))
        self.assertGreater(element.w, 21)
        self.assertEqual(element.w, element.h)
        self.assertEqual(element.meta["cell_x_dots"], 3)
        self.assertEqual(element.meta["cell_y_dots"], 3)

    def test_qr_render_does_not_center_or_paint_an_opaque_background(self) -> None:
        element = parse_datamatrix("1W1D3300001100346ABC", {})

        self.assertIsNotNone(element)
        assert element is not None
        svg = render_element_svg(element, canvas_height=250)

        self.assertIn("translate(346,119)", svg)
        self.assertNotIn("fill='#ffffff'", svg)

    def test_datamatrix_requested_dimensions_are_respected(self) -> None:
        element = parse_datamatrix(
            "1W1c44000005001302000036036<V1>,<V2>",
            {},
        )

        self.assertIsNotNone(element)
        assert element is not None
        self.assertEqual(element.kind, "datamatrix")
        self.assertEqual((element.x, element.y), (130, 50))
        self.assertEqual((element.w, element.h), (48, 48))
        self.assertEqual(element.meta["rows"], 36)
        self.assertEqual(element.meta["columns"], 36)

    def test_datamatrix_auto_size_uses_encoded_payload(self) -> None:
        element = parse_datamatrix(
            "1W1c44000004001282000000000<V1>,<V2>,<V3>,<QTY>",
            {"V1": "Device_No", "V2": "W_Lot", "V3": "Today,yyyy/MM/dd"},
        )

        self.assertIsNotNone(element)
        assert element is not None
        self.assertGreater(element.meta["modules"], 10)
        self.assertEqual(
            element.meta["modules"],
            len(datamatrix_matrix(element.text)),
        )


class LabelOffsetTests(unittest.TestCase):
    def test_column_and_row_offsets_apply_to_following_fields(self) -> None:
        data = (
            b"[Start]\r\n\x02L\r\nC0014\r\nR0005\r\n"
            b"1W1D3300001100326ABC\r\n"
        )

        parsed = parse_dpl_preview(Path("offset.MAX"), data)

        self.assertEqual(len(parsed.elements), 1)
        self.assertEqual((parsed.elements[0].x, parsed.elements[0].y), (340, 115))

    def test_final_dpl_without_start_marker_is_still_parsed(self) -> None:
        data = (
            b"\x02L\r\n"
            b"1911A1002100022Product Name:\r\n"
            b"1911A10021001200123456789\r\n"
            b"Q0001\r\nE\r\n"
        )

        parsed = parse_dpl_preview(Path("final_dpl.prn"), data)

        self.assertEqual(len(parsed.elements), 2)
        self.assertEqual(parsed.font_counts["A10"], 2)


class LabelSizeRuleTests(unittest.TestCase):
    def test_labelindex_label_paper_extracts_dimensions(self) -> None:
        self.assertEqual(
            extract_label_paper_sizes("[松翰專用]44x44雙排(白)"),
            [(44.0, 44.0)],
        )
        self.assertEqual(
            extract_label_paper_sizes("[聯詠專用] 130*75"),
            [(130.0, 75.0)],
        )

    def test_labelindex_csv_is_used_before_filename_guess(self) -> None:
        candidates = label_size_candidates(Path("AD_6A31DS.MAX"))

        self.assertEqual(
            candidates[0],
            (mm_to_units(44.0), mm_to_units(44.0), "44x44 mm labelindex.csv"),
        )

    def test_filename_dimension_rule_applies_directly(self) -> None:
        candidates = label_size_candidates(Path("AJ_TailDefect_44x44S.MAX"))

        self.assertIn(
            (mm_to_units(44.0), mm_to_units(44.0), "44x44 mm filename rule"),
            candidates,
        )

    def test_dslabel_exact_rule_overrides_small_content_canvas(self) -> None:
        parsed = ParsedLabel(
            path=Path("materials_PASS.MAX"),
            elements=[LabelElement(kind="text", x=10, y=12, w=30, h=8)],
        )

        width, height, _min_x, _min_y = estimate_canvas_size(parsed)

        self.assertEqual(width, mm_to_units(70.0))
        self.assertEqual(height, mm_to_units(30.0))
        self.assertEqual(parsed.label_size, "70x30 mm DSLabel rule")

    def test_canvas_expands_when_dslabel_guess_is_smaller_than_content(self) -> None:
        parsed = ParsedLabel(
            path=Path("JI_TRAY_Label.MAX"),
            elements=[LabelElement(kind="box", x=0, y=0, w=460, h=180)],
        )

        width, height, _min_x, _min_y = estimate_canvas_size(parsed)

        self.assertEqual(width, 464)
        self.assertEqual(height, max(mm_to_units(40.0), 184))
        self.assertIn("expanded to fit content", parsed.label_size)


class DatamaxProfileTests(unittest.TestCase):
    def test_datamax_profile_loader_reads_downloaded_and_resident_fonts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_dir = root / "datamax"
            profile_dir.mkdir()
            (profile_dir / "datamax_Downloaded_fonts_STXWF.txt").write_text(
                "Module: G\r\nS96 Arial96\r\nS95 ArialNarrowB95\r\nAvailable Bytes: 123\r\n",
                encoding="latin-1",
            )
            (profile_dir / "datamax_Resident_fonts_STXWf.txt").write_text(
                "S01 Triumvirate\r\nS00 Tri-Bold\r\n",
                encoding="latin-1",
            )
            (profile_dir / "datamax_All_memory_contents_STXWALL.txt").write_text(
                "Module: G\r\nS96 Arial96\r\nModule: Y\r\nMARKED\r\n",
                encoding="latin-1",
            )
            (profile_dir / "datamax_Firmware_STXv.txt").write_text(
                "VER: I4310e, 10.04_0056\r\n",
                encoding="latin-1",
            )
            (profile_dir / "datamax_Status_SOHA.txt").write_text(
                "NNNNNNNN\r\n",
                encoding="latin-1",
            )
            sample_path = root / "demo.MAX"
            sample_path.write_bytes(b"[Start]\r\n")

            profile = load_datamax_profile(sample_path)

            self.assertIsNotNone(profile)
            assert profile is not None
            self.assertEqual(profile.downloaded_fonts["S96"], "Arial96")
            self.assertEqual(profile.resident_scalable_fonts["S01"], "Triumvirate")
            self.assertEqual(profile.firmware, "VER: I4310e, 10.04_0056")
            self.assertEqual(profile.status_raw, "NNNNNNNN")

    def test_downloaded_font_profile_overrides_svg_font_family(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_dir = root / "datamax"
            profile_dir.mkdir()
            (profile_dir / "datamax_Downloaded_fonts_STXWF.txt").write_text(
                "Module: G\r\nS97 Courier New97\r\nAvailable Bytes: 123\r\n",
                encoding="latin-1",
            )
            (profile_dir / "datamax_Resident_fonts_STXWf.txt").write_text(
                "",
                encoding="latin-1",
            )
            (profile_dir / "datamax_All_memory_contents_STXWALL.txt").write_text(
                "Module: G\r\nS97 Courier New97\r\n",
                encoding="latin-1",
            )
            sample_path = root / "demo.MAX"
            sample_path.write_bytes(b"[Start]\r\n")

            profile = load_datamax_profile(sample_path)

            self.assertIsNotNone(profile)
            assert profile is not None
            style = font_style("S97", profile)
            self.assertEqual(style["family"], "'Courier New', Courier, monospace")


class ScalableTextTests(unittest.TestCase):
    def test_scalable_text_preserves_dpl_width_to_height_ratio(self) -> None:
        data = b"[Start]\r\n1911S960224002700340032TYPE\r\n"

        parsed = parse_dpl_preview(Path("text.MAX"), data)
        svg = render_element_svg(
            parsed.elements[0],
            canvas_height=250,
        )

        self.assertEqual(parsed.elements[0].meta["char_height_dots"], 34)
        self.assertEqual(parsed.elements[0].meta["char_width_dots"], 32)
        self.assertIn("scale(0.9412,1)", svg)


class PreviewVariableTests(unittest.TestCase):
    def test_qa_top_mark_does_not_overlap_fixed_approval_stamp(self) -> None:
        variables = {"V19": "top_mark7"}

        self.assertEqual(expand_preview_text("QA : <V19>", variables), "QA :")

    def test_variable_only_top_marks_use_short_representative_values(self) -> None:
        variables = {"V14": "top_mark", "V15": "top_mark2"}

        self.assertEqual(
            expand_preview_text("<V15> <V14>", variables),
            "01234 56",
        )

    def test_top_mark_in_normal_data_field_keeps_generic_payload(self) -> None:
        variables = {"V17": "top_mark3"}

        self.assertEqual(
            expand_preview_text("Cust.P/N :<V17>", variables),
            "Cust.P/N :0123456789",
        )

    def test_common_mes_fields_use_representative_lengths(self) -> None:
        variables = {"V2": "po_no2", "V6": "patent7", "V18": "top_mark6"}

        self.assertEqual(expand_preview_text("<V2>", variables), "PO12345")
        self.assertEqual(expand_preview_text("THK : <V6>", variables), "THK : 8")
        self.assertEqual(
            expand_preview_text("MPN:<V18>", variables),
            "MPN:MPN12345",
        )


class BoxedTextTests(unittest.TestCase):
    def test_text_inside_box_is_scaled_to_available_width(self) -> None:
        text = LabelElement(
            kind="text",
            x=124,
            y=54,
            w=34,
            h=10,
            text="YT ACC",
            font_code="A06",
            font_px=10,
        )
        box = LabelElement(kind="box", x=122, y=47, w=32, h=17)

        svg = render_element_svg(
            text,
            canvas_height=148,
            boxes=[box],
        )

        self.assertIn("scale(0.8235,1)", svg)


if __name__ == "__main__":
    unittest.main()
