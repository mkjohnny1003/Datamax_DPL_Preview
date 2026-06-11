# Datamax DPL Preview

[中文](#中文說明) | [English](#english)

## 中文說明

這是一套獨立的 Python 工具，可將 Datamax DPL 標籤檔案轉換為 HTML/SVG
預覽圖庫。此工具以 Datamax-O'Neil I-4310e Mark II 300 dpi 的實際 DPL
檔案為基礎開發。

工具以 bytes 模式讀取檔案，避免破壞 DPL 控制字元。它不會將資料傳送到
印表機，也不會修改原始標籤檔案。

### 功能

- 批次預覽 `.MAX`、`.DPL`、`.PRN` 與 `.TXT` 檔案
- 支援 DPL 文字、可縮放字型、線條、外框與標籤座標偏移
- 支援 Code 39 與 Code 128 預覽
- 支援 QR Code 與 Data Matrix 預覽
- 支援 Datamax ASCII 十六進位內嵌圖形與圖形呼叫
- 使用代表性測試資料模擬 MES 變數
- 產生可搜尋的 HTML 圖庫，每張標籤另有 SVG 檔案
- Windows 批次檔支援拖曳檔案或資料夾執行

### 系統需求

- Python 3.10 或更新版本
- `requirements.txt` 內的條碼套件為選用相依套件

```powershell
python -m pip install -r requirements.txt
```

未安裝選用套件時，工具仍可執行，但部分條碼類型會使用替代的視覺圖樣。

### 使用方式

預覽專案內附的合成範例：

```powershell
python datamax_dpl_preview.py samples
```

遞迴預覽資料夾內的標籤：

```powershell
python datamax_dpl_preview.py "C:\path\to\labels" --recursive
```

Windows 使用者也可以雙擊 `Run_DPL_Preview.bat` 後輸入路徑，或將標籤檔案
或資料夾拖曳到批次檔上。

產生的預覽圖庫位於：

```text
<輸入資料夾>\DPL_Preview\index.html
```

### 適用範圍與準確性

本專案是用於快速視覺檢查的工具，不是完整的印表機模擬器。Datamax
印表機韌體、下載字型、紙張校正、列印濃度及機械公差都可能影響實際列印
結果。重要標籤仍應使用目標印表機實際列印，並掃描驗證 1D/2D 條碼。

此 repository 僅包含合成標籤範例。提交問題時，請勿公開量產標籤、客戶
資料、專有字型、印表機驅動程式或原廠手冊。

### 測試

```powershell
python -m unittest discover -s tests -v
```

### 授權

MIT

## English

This standalone Python tool renders Datamax DPL label files into an HTML/SVG
preview gallery. It was developed against DPL files used by a
Datamax-O'Neil I-4310e Mark II at 300 dpi.

The tool reads input as bytes to preserve DPL control characters. It does not
send data to a printer and does not modify the source label files.

### Features

- Batch preview for `.MAX`, `.DPL`, `.PRN`, and `.TXT` files
- DPL text records, scalable fonts, lines, boxes, and label offsets
- Code 39 and Code 128 preview
- QR Code and Data Matrix preview
- Embedded Datamax ASCII-hex graphics and graphic calls
- MES-style variable substitution using representative sample values
- Searchable HTML gallery with one SVG file per label
- Drag-and-drop file or folder support through the Windows batch file

### Requirements

- Python 3.10 or newer
- Optional barcode dependencies from `requirements.txt`

```powershell
python -m pip install -r requirements.txt
```

Without the optional packages, the tool still runs, but some barcode types use
fallback visual patterns.

### Usage

Preview the included synthetic sample:

```powershell
python datamax_dpl_preview.py samples
```

Preview a folder recursively:

```powershell
python datamax_dpl_preview.py "C:\path\to\labels" --recursive
```

Windows users can also double-click `Run_DPL_Preview.bat` and enter a path, or
drag a label file or folder onto the batch file.

The generated gallery is written to:

```text
<input folder>\DPL_Preview\index.html
```

### Scope And Accuracy

This project is a visual screening tool, not a complete printer emulator.
Datamax printer firmware, downloaded fonts, media calibration, print darkness,
and mechanical tolerances can change the physical result. Always validate
critical labels on the target printer and scan-test 1D/2D codes.

This repository intentionally contains only synthetic label samples. Do not
publish production labels, customer data, proprietary fonts, printer drivers,
or vendor manuals in bug reports.

### Tests

```powershell
python -m unittest discover -s tests -v
```

### License

MIT
