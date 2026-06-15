# Datamax DPL Preview

[中文](#中文) | [English](#english)

## 中文

`Datamax DPL Preview` 是一個以 Python 撰寫的 Datamax DPL 預覽工具，目標是把
`.MAX`、`.DPL`、`.PRN`、`.TXT` 標籤檔快速轉成可視化預覽，方便工程師批次檢查版面。

這個版本是依照 `Datamax-O'Neil I-4310e Mark II`、`300 dpi` 的現場資料持續校準，
目前同時提供：

- 大量檔案 HTML/SVG 預覽頁
- 單檔 / 貼上 DPL 內容的 Windows GUI 預覽器

工具全程以 `bytes` 讀取來源檔，避免破壞 DPL 控制碼，不會修改原始標籤檔。

### 特色

- 支援 `.MAX`、`.DPL`、`.PRN`、`.TXT`
- 支援文字、scalable fonts、line、box、graphic call、ASCII-hex graphic
- 支援 Code 39、Code 128、QR Code、Data Matrix 預覽
- 支援常見 MES / DSLabel 變數替代顯示
- 支援 `labelindex.csv`、檔名尺寸規則、DSLabel 規則推測標籤大小
- GUI 可直接開檔、開資料夾、貼上 DPL、縮放、套用手動標籤尺寸、輸出 SVG
- GUI 預覽優先共用 web 版 SVG 渲染路徑，再由 Edge / Chrome headless 轉圖，降低 EXE 與網頁版的顯示落差

### 專案內容

- `datamax_dpl_preview.py`
  - 批次掃描資料夾，輸出 `DPL_Preview/index.html` 與每張標籤的 SVG
- `datamax_dpl_preview_gui.py`
  - Windows GUI 預覽器
- `Run_DPL_Preview.bat`
  - 批次產生 HTML/SVG 預覽
- `Run_DPL_Preview_GUI.bat`
  - 啟動 GUI 預覽器
- `datamax_dpl_preview_gui.spec`
  - PyInstaller 打包設定

### 安裝需求

- Python 3.10 以上
- 建議安裝 `requirements.txt`
- GUI 若要接近 web 版排版結果，建議系統安裝 Microsoft Edge 或 Google Chrome

```powershell
python -m pip install -r requirements.txt
```

若未安裝選用套件，程式仍可運作，但部分條碼會使用 fallback 圖樣。

### 使用方式

批次預覽整個資料夾：

```powershell
python datamax_dpl_preview.py "C:\path\to\labels" --recursive
```

輸出位置：

```text
<input folder>\DPL_Preview\index.html
```

啟動 GUI 預覽器：

```powershell
python datamax_dpl_preview_gui.py
```

Windows 也可以直接雙擊：

- `Run_DPL_Preview.bat`
- `Run_DPL_Preview_GUI.bat`

### PyInstaller 打包

保留 console 的打包方式：

```powershell
python -m PyInstaller datamax_dpl_preview_gui.spec --distpath dist --workpath build
```

輸出檔案：

```text
dist\Datamax_DPL_Preview_Viewer.exe
```

### 準確度與限制

這是視覺檢查工具，不是 Datamax 韌體等級的完整模擬器。

仍可能影響實際列印結果的因素包括：

- 印表機內下載字型
- 印表機 darkness / speed / calibration
- 實體標籤材質
- 機械誤差
- 某些未隨 DPL 檔一起保存的外部 graphic / image 資源

對於正式量產標籤，仍必須：

- 實機列印樣張
- 掃描驗證 1D barcode / 2D code

### 公開發佈注意事項

此 repository 應只保留工具本身與合成樣本。

不要公開：

- 客戶正式標籤檔
- 工廠現場資料
- 專有字型檔
- Seagull / 廠商驅動套件
- Vendor manual PDF
- 任何含 MES / SN / LOT 真實資料的測試檔

### 測試

```powershell
python -m unittest discover -s tests -v
```

### 授權

MIT

## English

`Datamax DPL Preview` is a Python-based visual preview tool for Datamax DPL
label files. It converts `.MAX`, `.DPL`, `.PRN`, and `.TXT` files into
previewable output so engineers can inspect layouts quickly without modifying
the source data.

This version has been iteratively calibrated against a
`Datamax-O'Neil I-4310e Mark II` at `300 dpi` and currently provides:

- an HTML/SVG batch preview gallery
- a Windows GUI viewer for single files or pasted DPL

The tool reads files as `bytes` to preserve DPL control characters. It does
not modify the original label files.

### Features

- Supports `.MAX`, `.DPL`, `.PRN`, and `.TXT`
- Renders text, scalable fonts, lines, boxes, graphic calls, and ASCII-hex graphics
- Previews Code 39, Code 128, QR Code, and Data Matrix
- Expands common MES / DSLabel variables into representative sample values
- Infers label size from `labelindex.csv`, filename-based rules, and DSLabel rules
- GUI viewer supports file open, folder browse, pasted DPL, zoom, manual label size, and SVG export
- GUI preview reuses the same SVG rendering path as the web preview and then rasterizes through Edge / Chrome headless when available

### Project Files

- `datamax_dpl_preview.py`
  - batch HTML/SVG preview generator
- `datamax_dpl_preview_gui.py`
  - Windows GUI viewer
- `Run_DPL_Preview.bat`
  - launch batch HTML/SVG preview generation
- `Run_DPL_Preview_GUI.bat`
  - launch the GUI viewer
- `datamax_dpl_preview_gui.spec`
  - PyInstaller build spec

### Requirements

- Python 3.10 or newer
- Recommended: install dependencies from `requirements.txt`
- Recommended for GUI fidelity: Microsoft Edge or Google Chrome installed

```powershell
python -m pip install -r requirements.txt
```

Without optional packages, the tool still runs, but some barcode types fall
back to simplified visual patterns.

### Usage

Generate a recursive preview for a label folder:

```powershell
python datamax_dpl_preview.py "C:\path\to\labels" --recursive
```

Output location:

```text
<input folder>\DPL_Preview\index.html
```

Run the GUI viewer:

```powershell
python datamax_dpl_preview_gui.py
```

On Windows you can also double-click:

- `Run_DPL_Preview.bat`
- `Run_DPL_Preview_GUI.bat`

### PyInstaller Packaging

Console-preserving build command:

```powershell
python -m PyInstaller datamax_dpl_preview_gui.spec --distpath dist --workpath build
```

Output executable:

```text
dist\Datamax_DPL_Preview_Viewer.exe
```

### Scope And Accuracy

This is a visual screening tool, not a full Datamax firmware emulator.

Physical output can still differ because of:

- downloaded printer fonts
- print darkness, speed, and calibration
- label stock material
- mechanical tolerances
- external graphics or images that were not stored inside the DPL job

For production labels, always:

- print real samples
- scan-verify 1D barcodes and 2D codes

### Publishing Notes

This repository should contain only the tool itself and synthetic samples.

Do not publish:

- production label files
- plant data
- proprietary font files
- Seagull or vendor driver packages
- vendor manual PDFs
- any test files containing real MES / SN / LOT data

### Tests

```powershell
python -m unittest discover -s tests -v
```

### License

MIT
