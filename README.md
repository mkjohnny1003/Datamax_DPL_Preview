# Datamax DPL Preview

A standalone Python tool that renders Datamax DPL label files into an HTML/SVG
preview gallery. It was developed against DPL files used by a
Datamax-O'Neil I-4310e Mark II at 300 dpi.

The tool reads input as bytes to preserve DPL control characters. It does not
send data to a printer and does not modify the source label files.

## Features

- Batch preview for `.MAX`, `.DPL`, `.PRN`, and `.TXT` files
- DPL text records, scalable fonts, lines, boxes, and label offsets
- Code 39 and Code 128 preview
- QR Code and Data Matrix preview
- Embedded Datamax ASCII-hex graphics and graphic calls
- MES-style variable substitution using representative sample values
- Searchable HTML gallery with one SVG file per label
- Drag-and-drop folder support through the Windows batch file

## Requirements

- Python 3.10 or newer
- Optional barcode dependencies from `requirements.txt`

```powershell
python -m pip install -r requirements.txt
```

Without the optional packages, the tool still runs but some barcode types use
fallback visual patterns.

## Usage

Preview the included synthetic sample:

```powershell
python datamax_dpl_preview.py samples
```

Preview a folder recursively:

```powershell
python datamax_dpl_preview.py "C:\path\to\labels" --recursive
```

You can also double-click `Run_DPL_Preview.bat`, enter a path, or drag a label
file/folder onto it.

The generated gallery is written to:

```text
<input folder>\DPL_Preview\index.html
```

## Scope And Accuracy

This project is a visual screening tool, not a complete printer emulator.
Datamax printer firmware, downloaded fonts, media calibration, print darkness,
and mechanical tolerances can change the physical result. Always validate
critical labels on the target printer and scan-test 1D/2D codes.

The repository intentionally contains only synthetic label samples. Do not
publish production labels, customer data, proprietary fonts, printer drivers,
or vendor manuals with bug reports.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## License

MIT
