# OpenConvert

免費、開源、離線優先的通用檔案轉換工具，支援影片、音訊、圖片、PDF、電子書、Office 文件、試算表、資料、字幕、字型與壓縮。

- **不上傳任何檔案**：所有轉換都在你的電腦上完成，不需要網路，也不需要帳號。
- **不需要付費 API**：只使用 FFmpeg、Pillow、pypdf、fontTools 等開源元件。
- **圖形介面 + 命令列**：桌面使用者拖放即可轉換，腳本與伺服器可用 `openconvert convert`。

目前版本 **0.2.0（Beta）**，共 82 個目標格式，已通過 169 個自動化測試（引擎、GUI 煙霧測試、CLI 端對端）。

---

## 功能

| 分類 | 內容 |
| --- | --- |
| 影片 | MP4／MKV／WebM／MOV／M4V／AVI／FLV／WMV／OGV／TS／GIF 動畫，可調整品質與最大解析度 |
| 影片進階 | 抽出影格（PNG）、整批圖片合成 MP4 |
| 音訊 | MP3／M4A／M4B／AAC／WAV／FLAC／OGG／Opus／AIFF／WMA／AC3，可從影片直接抽出音軌 |
| 圖片 | PNG／JPEG／WebP／AVIF／HEIC／BMP／TIFF／ICO／GIF／APNG，支援透明背景、等比例縮放、多張合併為 PDF |
| PDF | 合併、抽取頁碼範圍、每頁輸出 PNG／JPEG、抽出純文字、轉成 CBZ（可選解析度） |
| 電子書 | CBZ ⇄ EPUB、CBZ → PDF、EPUB → 純文字、文字／Markdown／HTML → EPUB（自動分章） |
| 文件 | Markdown ⇄ HTML、HTML／DOCX → 純文字或 Markdown、DOCX → HTML |
| Office（需 LibreOffice） | DOCX／DOC／ODT／RTF／PPTX／ODP → PDF，DOC ⇄ DOCX、DOCX ⇄ ODT、XLS ⇄ XLSX、XLSX ⇄ ODS |
| 資料 | CSV／TSV／JSON／XLSX／YAML／TOML 互相轉換（可指定工作表） |
| 字幕 | SRT／WebVTT／ASS 互轉，自動辨識 Big5／GB18030 等編碼 |
| 字型 | TTF／OTF／WOFF／WOFF2 互轉（無損） |
| 壓縮 | 把整批檔案打包成 ZIP 或 tar.gz |
| 檔案資訊 | FFprobe 中繼資料、圖片尺寸、PDF 頁數、文字編碼、字型家族… |
| 批次 | 佇列、逐檔進度、整體進度、單筆取消／全部取消 |
| 錯誤處理 | 人性化錯誤訊息、失敗原因記錄、自動清除半成品 |
| 紀錄 | 轉換歷史、輸出位置、開啟資料夾、清除紀錄 |

完整格式清單與選項說明見 [`docs/formats.md`](docs/formats.md)。

## 系統需求

- Windows 10/11、macOS 12+ 或 Linux（X11／Wayland）
- Python 3.10 以上（原始碼執行）；打包版不需要安裝 Python
- **FFmpeg**：影片與音訊轉換、檔案資訊功能需要。
- **LibreOffice**：Office 文件與試算表的進階轉換（例如 DOCX → PDF）需要。

FFmpeg 與 LibreOffice 都是**外部程式，不隨本專案散布**；沒有安裝時，其餘格式仍可正常使用，
只有需要它們的目標會回報明確訊息。

### FFmpeg／LibreOffice 安裝

```powershell
# Windows
winget install Gyan.FFmpeg
winget install TheDocumentFoundation.LibreOffice
# macOS
brew install ffmpeg
brew install --cask libreoffice
# Debian / Ubuntu
sudo apt install ffmpeg libreoffice
```

本程式依下列順序尋找 FFmpeg，找不到時「設定」頁會顯示狀態並允許手動指定：

1. 「設定」頁指定的路徑
2. 程式目錄下的 `tools/`（可攜式擺放 `ffmpeg.exe`／`ffprobe.exe`）
3. 系統 `PATH`
4. 常見安裝位置（`C:\ffmpeg\bin`、Chocolatey、WinGet Links 等）
5. WinGet Packages 目錄掃描（處理安裝後 PATH 尚未更新的情況）

LibreOffice 以相同方式尋找 `soffice`：設定頁指定路徑 → 系統 `PATH` →
常見安裝位置（Windows `C:\Program Files\LibreOffice\program`、macOS `/Applications/LibreOffice.app`、Linux 發行套件）。

## 安裝

```powershell
git clone <this-repository>
cd OpenConvert
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux：source .venv/bin/activate
pip install -e .
```

## 使用

### 圖形介面

```powershell
openconvert
```

1. 拖放檔案到視窗（或按「加入檔案」）。
2. 在「目標格式」選擇要轉成的格式；下方選項會依格式自動顯示。
3. 需要時指定輸出資料夾（預設與來源相同）。
4. 按「開始轉換」，在佇列中查看進度；可隨時取消單筆或全部。

### 命令列

```powershell
# 列出所有目標格式
openconvert-cli formats

# 影片轉 MP4（品質平衡）
openconvert-cli convert clip.mov -t mp4 -o out

# 整個資料夾的圖片轉 JPEG，最長邊縮到 1920
openconvert-cli convert photos\ -t jpg --max-size 1920 -o out

# 抽取 PDF 第 1-3 與第 7 頁
openconvert-cli convert report.pdf -t pdf-extract --pages 1-3,7

# 合併多份 PDF
openconvert-cli convert a.pdf b.pdf c.pdf -t pdf-merge -o out

# PDF 抽出文字、轉成漫畫壓縮檔
openconvert-cli convert report.pdf -t pdf-txt -o out
openconvert-cli convert comic.pdf -t pdf-cbz --dpi 200 -o out

# Markdown 轉 HTML；DOCX 轉 Markdown
openconvert-cli convert notes.md -t md-html -o out
openconvert-cli convert report.docx -t docx-md -o out

# DOCX 轉 PDF（需要 LibreOffice）
openconvert-cli convert report.docx -t docx-pdf -o out

# CSV 轉 JSON；試算表指定工作表後轉 CSV
openconvert-cli convert data.csv -t data-json -o out
openconvert-cli convert book.xlsx -t data-csv --sheet 成績 -o out

# 字幕轉換；字型轉 WOFF2；打包整批檔案
openconvert-cli convert movie.srt -t sub-vtt -o out
openconvert-cli convert font.ttf -t font-woff2 -o out
openconvert-cli convert photos\ -t zip -o out

# 影片抽出每秒 2 張影格；整批圖片合成 30fps 影片
openconvert-cli convert clip.mp4 -t video-frames --fps 2 -o out
openconvert-cli convert frames\ -t images-video --fps 30 --frame-seconds 3 -o out

# 檢視檔案中繼資料（JSON）
openconvert-cli probe clip.mp4
```

`convert` 的結束碼：`0` 全部成功、`1` 有轉換失敗、`2` 參數或輸入有誤、`3` 找不到 FFmpeg 或 LibreOffice。

## 檔案安全規則

- **絕不覆蓋原始檔**：輸出檔名若與來源相同，會加上 `_converted`。
- **預設不覆蓋既有檔案**：同名輸出自動編號為 `名稱 (1).jpg`、`名稱 (2).jpg`。
- 覆寫必須由使用者在「設定」明確開啟，命令列則需加 `--overwrite`。
- 多輸出轉換（PDF → 圖片）一律建立新的輸出資料夾，不與既有檔案混在一起。
- 轉換失敗或中途取消時，本次產生的輸出會被刪除，不留下半成品。

## 設定與資料位置

| 平台 | 設定 | 紀錄 |
| --- | --- | --- |
| Windows | `%APPDATA%\OpenConvert\settings.json` | `%LOCALAPPDATA%\OpenConvert\` |
| macOS | `~/Library/Application Support/OpenConvert/` | 同左 |
| Linux | `~/.config/OpenConvert/` | `~/.local/share/OpenConvert/` |

可用環境變數 `OPENCONVERT_CONFIG_DIR`、`OPENCONVERT_DATA_DIR` 覆寫（可攜式版本與測試使用）。

## 從原始碼開發

```powershell
pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q        # 169 tests
.venv\Scripts\ruff.exe check .               # lint
.venv\Scripts\ruff.exe format --check .      # 格式檢查
```

GUI 測試需要 `QT_QPA_PLATFORM=offscreen`（CI 已設定）。要在沒有螢幕的環境檢查版面，可執行：

```powershell
.venv\Scripts\python.exe scripts\preview.py out\screenshots
```

會輸出深色／淺色共 11 張視窗截圖。

架構與分層規則見 [`docs/architecture.md`](docs/architecture.md)，設計取捨見 [`docs/planning.md`](docs/planning.md)。

## 打包

```powershell
pip install -e ".[dev]"
pyinstaller packaging\openconvert.spec --noconfirm
```

產物位於 `dist/OpenConvert/`（`--onedir`，啟動較快、也方便使用者把 `ffmpeg.exe` 放進 `tools/`），
內含圖形介面 `OpenConvert.exe` 與命令列 `OpenConvertCLI.exe`。建置細節見 [`docs/packaging.md`](docs/packaging.md)。

## 專案結構

```
openconvert/
  core/         # 與 GUI 無關：型別判定、目標宣告、FFmpeg、LibreOffice、設定、紀錄、路徑安全
  converters/   # 實際轉換實作（media / image / pdf / ebook / document / data / subtitle / font / archive）
  gui/          # PySide6 介面：主視窗、頁面、元件、主題
  runner.py     # QThreadPool 佇列，GUI 與引擎的橋樑
  cli.py        # 命令列介面（不需要 Qt）
tests/          # pytest：core、converters、CLI、GUI
docs/           # 規劃、架構、格式、打包
scripts/        # 開發輔助工具（截圖預覽）
```

## 授權與第三方元件

本專案以 **MIT** 授權釋出，詳見 [`LICENSE`](LICENSE)。

| 元件 | 授權 | 用途 |
| --- | --- | --- |
| PySide6 / Qt | LGPL-3.0 | 圖形介面（動態連結，未修改 Qt） |
| Pillow | HPND | 圖片讀寫與縮放 |
| pillow-heif | BSD-3-Clause | HEIC／HEIF 讀寫 |
| pypdf | BSD-3-Clause | PDF 結構操作（合併、抽頁、抽出文字） |
| pypdfium2 | Apache-2.0 / BSD-3-Clause | PDF 點陣化（PDF → 圖片／CBZ） |
| python-docx | MIT | 讀取 DOCX |
| openpyxl | MIT | 讀寫 XLSX |
| PyYAML / tomli-w / tomli | MIT | YAML／TOML 讀寫 |
| Markdown | BSD-3-Clause | Markdown → HTML |
| beautifulsoup4 / markdownify | MIT | HTML 解析與轉 Markdown |
| fonttools | MIT | 字型格式轉換 |
| brotli | MIT | WOFF2 壓縮 |
| platformdirs | MIT | 跨平台設定路徑 |
| FFmpeg | LGPL/GPL（**外部程式**） | 影片、音訊編碼與探測 |
| LibreOffice | MPL-2.0（**外部程式**） | Office 文件排版與轉換 |

FFmpeg 與 LibreOffice **不內嵌**於本專案，由使用者自行安裝；因此本專案的 MIT 授權不會被它們的授權污染。
若你散布包含 FFmpeg 或 LibreOffice 的組合包，需自行遵守其授權條款。

## 貢獻

歡迎回報問題與送 PR，請先閱讀 [`CONTRIBUTING.md`](CONTRIBUTING.md) 與 [`CHANGELOG.md`](CHANGELOG.md)。
