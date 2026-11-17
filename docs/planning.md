# OpenConvert — 產品規劃與技術研究

> 本文件記錄專案啟動前的技術選型、風險評估與範圍界定。
> 所有結論均以「可離線運作、免費、開源、不依賴付費 API」為前提。

---

## 1. 問題定義

一般使用者手上經常出現「格式不相容」的情況：

- 手機錄的 `.mov` 無法在剪輯軟體開啟
- 下載的 `.webp` 圖片在舊版 Word 中顯示不出來
- 十幾份 PDF 需要合併成一份
- 掃描漫畫是 `.cbz`，閱讀器只吃 `.epub`
- 想先確認一支影片的解析度、編碼、位元率再決定怎麼轉

現有方案的問題：

| 方案類型 | 問題 |
|---|---|
| 線上轉換網站 | 必須上傳私人檔案、有大小限制、藏廣告、可能保留檔案 |
| 商業桌面軟體 | 付費、訂閱制、安裝肥大、常捆綁額外套件 |
| 命令列工具（FFmpeg） | 功能完整但對一般使用者門檻過高 |

**定位**：把成熟開源引擎包進一個看得懂、拖進去就能用的桌面程式。

---

## 2. 技術選型評估

### 2.1 程式語言：Python 3.13

| 評估項 | 結論 |
|---|---|
| 生態完整度 | 影像 / PDF / 電子書 / 媒體控制都有成熟套件 |
| 打包可行性 | PyInstaller 可產出單一 Windows 執行檔 |
| 跨平台 | Windows / macOS / Linux 同一份程式碼 |
| 效能 | 重運算全部委外給 FFmpeg / Pillow（C 實作），Python 只做協調，不是瓶頸 |
| 風險 | 執行檔體積較大（PySide6 約 80–150 MB），可接受 |

**決策：採用 Python 3.13 + 型別註記。**

### 2.2 GUI 框架：PySide6

| 候選 | 優點 | 缺點 | 結論 |
|---|---|---|---|
| **PySide6 (Qt 6)** | 官方 Qt 綁定、LGPL、原生外觀、拖放/執行緒/樣式完整、CSS 主題成熟 | 體積大 | **採用** |
| PyQt6 | 功能相同 | GPL 或商業授權，與 MIT 專案不相容 | 排除 |
| Tkinter | 內建、極輕 | 外觀過時、高 DPI 與主題支援差 | 排除 |
| Electron/Tauri | 網頁 UI 彈性高 | 需另外維護 JS 堆疊，體積與記憶體更高 | 排除 |
| Flet / NiceGUI | 開發快 | 需內嵌 WebView，離線打包較不穩定 | 排除 |

**決策：PySide6，授權 LGPL-3.0（動態連結使用，符合要求）。**

### 2.3 媒體引擎：FFmpeg / FFprobe

- 事實上的業界標準，涵蓋幾乎所有容器與編碼。
- `-progress pipe:1` 提供機器可讀的進度輸出，適合做進度條。
- **授權注意事項（重要）**：
  - FFmpeg 本體為 LGPL-2.1+；若編譯時加上 `--enable-gpl`（多數預編譯「full」版都是）則整份變成 **GPL**。
  - 本專案為 MIT 授權。若直接將 GPL 版 FFmpeg 打包進發行檔，會讓整個發行物受 GPL 約束。
- **決策**：
  1. **不內嵌** FFmpeg 執行檔。
  2. 執行時依序尋找：使用者自訂路徑 → 應用程式 `tools/` 目錄 → 系統 `PATH` → 常見安裝路徑。
  3. 找不到時，在介面上明確說明並提供官方下載連結，由使用者自行安裝。
  4. 若日後要隨附，必須改用 **LGPL 版建置**（例如 BtbN 的 `-lgpl` 資產）並附上授權與原始碼取得方式。

### 2.4 影像處理：Pillow

- 覆蓋 PNG / JPEG / WebP / BMP / TIFF / GIF / ICO，讀寫皆為 C 實作，速度快。
- Pillow 11.3 起**原生支援 AVIF**（含透明度與動畫），不需額外外掛。
- HEIC／HEIF 由 `pillow-heif`（BSD-3-Clause）提供，註冊後即為 Pillow 的一般格式。
- APNG 動畫由 Pillow 內建的 PNG 外掛支援。
- **決策：Pillow 為影像轉換主引擎，不引入 ImageMagick**（ImageMagick 需額外安裝、命令列介面複雜、Windows 發行版有政策限制風險）。CMYK / PSD 仍不在支援範圍。

### 2.5 PDF：pypdf + pypdfium2

- `pypdf`（BSD）：合併、拆分、抽頁、加密、旋轉、中繼資料。**純 Python、無外部依賴**。
- `pypdf` **無法將 PDF 頁面點陣化為圖片**（它只解析結構，不渲染）。
- `pypdfium2`（BSD-3-Clause / Apache-2.0）：Google PDFium 的 Python 綁定，負責「PDF → 圖片」。
- **決策：兩者並用。** 優點是渲染品質與 Chrome 相同，且完全離線。

### 2.6 電子書：EbookLib

- `EbookLib`（AGPL-3.0）可建立 / 讀取 EPUB。
- **授權注意**：AGPL 對「散布」有較強要求。由於本專案會散布執行檔，需評估。
- 替代方案：**自行以 `zipfile` + XHTML 樣板產生 EPUB**。EPUB 本質就是 ZIP + `mimetype` + `META-INF/container.xml` + OPF + XHTML，實作量不大且完全可控。
- **決策**：
  - 第一階段以自製 EPUB 產生器為主（無授權負擔、行為可預測、可寫單元測試）。
  - `EbookLib` 僅作為**開發期參考與選用後端**，不列入發行依賴。
  - CBZ 就是 ZIP，直接用標準庫處理。

### 2.7 文件、資料與其他格式（0.2.0「全能」版）

- **純文字／Markdown ⇄ HTML**：`Markdown`（BSD-3）、`beautifulsoup4`（MIT）、`markdownify`（MIT）皆為寬鬆授權。
- **DOCX 讀取**：`python-docx`（MIT），只讀不寫，段落／清單／表格可轉成 Markdown 或純文字。
- **試算表與資料**：`openpyxl`（MIT）、`PyYAML`（MIT）、`tomli-w` / `tomli`（MIT）。
- **字幕**：SRT／VTT／ASS 格式簡單，自行以正規表達式實作，不新增依賴。
- **字型**：`fonttools`（MIT）負責 TTF／OTF／WOFF／WOFF2 互轉；WOFF2 需要 `brotli`（MIT）。
- **壓縮**：標準庫 `zipfile` / `tarfile`。
- **Office 排版轉換（DOCX／PPTX／XLSX… → PDF）**：外部引擎 `LibreOffice`（MPL-2.0）。
  - **決策**：與 FFmpeg 相同定位 —— **不內嵌、不散布**，由使用者自行安裝；偵測不到時只有 Office 目標失敗並顯示明確訊息。
  - 每次轉換使用獨立的 `-env:UserInstallation` 暫時設定檔，避免與已開啟的 LibreOffice 互相鎖定。
  - 不引入 `unoconv` / `docx2pdf`（前者需常駐服務，後者依賴 Word／COM）。
- **掃描型 PDF 的 OCR**：不在支援範圍（需再引入 Tesseract 等引擎，體積與平台複雜度高）。

### 2.7b 自足化：內附 FFmpeg 與 LibreOffice（0.3.0）

- **目標**：使用者拿到執行檔後，電腦上不需要先安裝任何東西就能完整轉換。
- **取捨**：H.264（MP4／MKV／MOV…）需要 FFmpeg 的 `libx264`，而那是 GPL 元件。
  為了「選了就能播」的品質底線，決定使用 **GPL 完整版**，並在發佈檔中附上授權與原始碼取得方式。
  OpenConvert 自己的程式碼維持 MIT（FFmpeg 為獨立子程序，不連結）。
- **LibreOffice**：以官方 MSI 的 `msiexec /a` 管理員安裝模式解壓縮，取得不註冊的可攜目錄；
  轉換時使用獨立的 `-env:UserInstallation`，不與使用者已安裝的版本互相影響。
- **可重現性**：`packaging/tools.lock.json` 固定引擎版本與 SHA-256。FFmpeg 指向 BtbN 有日期的
  autobuild（資產不變），LibreOffice 指向官方穩定版 MSI（同版本檔案不變）。
- **發行形態**：Lite（約 90 MB，不含引擎）與 Full（約 500 MB，完全自足）並行。
- **尚未支援**：macOS 的 FFmpeg／LibreOffice 與各平台的 arm64；`fetch_tools.py` 會明確拒絕，
  不會下載未經驗證的來源。

### 2.8 打包：PyInstaller

- `--onedir` 啟動快、較不易被防毒誤判；`--onefile` 單檔方便但每次啟動要解壓。
- **決策**：發行 `--onedir` 的 ZIP（主要）與 `--onefile`（次要）。GUI 程式用 `--windowed` 避免跳出主控台視窗。

### 2.9 CI：GitHub Actions

- `windows-latest` / `ubuntu-latest` / `macos-latest` 執行 `pytest`。
- Windows 額外產出 PyInstaller 成品並上傳 artifact。
- 全部使用官方 action，無付費需求。

---

## 3. 第一階段功能範圍

| # | 功能 | 引擎 | 狀態 |
|---|---|---|---|
| 1 | 影片轉檔（mp4 / mkv / webm / mov / avi / gif） | FFmpeg | 第一階段 |
| 2 | 音訊轉檔（mp3 / m4a / aac / wav / flac / ogg / opus） | FFmpeg | 第一階段 |
| 3 | 圖片轉檔（png / jpg / webp / bmp / tiff / gif / ico） | Pillow | 第一階段 |
| 4 | PDF 合併 / 抽頁 / 拆分 / 圖片轉 PDF / PDF 轉圖片 | pypdf + pypdfium2 | 第一階段 |
| 5 | 電子書 CBZ ⇄ EPUB、圖片轉 CBZ | 標準庫 + 自製 EPUB | 第一階段 |
| 6 | 媒體資訊檢視 | FFprobe | 第一階段 |
| 7 | 批次處理 | 佇列 + 執行緒池 | 第一階段 |
| 8 | 進度顯示 | FFmpeg `-progress` / 逐檔回報 | 第一階段 |
| 9 | 錯誤提示與轉換紀錄 | 例外處理 + JSONL 紀錄 | 第一階段 |

## 3.1 第二階段功能範圍（0.2.0）

| # | 功能 | 引擎 | 狀態 |
|---|---|---|---|
| 10 | AVIF／HEIC／APNG 圖片 | Pillow + pillow-heif | 已完成 |
| 11 | 影片：M4V／FLV／WMV／OGV／TS、抽影格、圖片轉影片 | FFmpeg | 已完成 |
| 12 | 音訊：M4B／AIFF／WMA／AC3 | FFmpeg | 已完成 |
| 13 | PDF → 純文字、PDF → CBZ | pypdf + pypdfium2 | 已完成 |
| 14 | 文字／Markdown／HTML → EPUB、EPUB → 純文字、CBZ → PDF | 標準庫 + 自製 EPUB | 已完成 |
| 15 | Markdown ⇄ HTML、HTML／DOCX → 純文字或 Markdown、DOCX → HTML | Markdown + bs4 + python-docx | 已完成 |
| 16 | Office／試算表 ⇄ PDF 等排版轉換 | LibreOffice（外部程式） | 已完成 |
| 17 | CSV／TSV／JSON／XLSX／YAML／TOML 互轉 | openpyxl + PyYAML + tomli-w | 已完成 |
| 18 | 字幕 SRT／VTT／ASS 互轉 | 自製 | 已完成 |
| 19 | 字型 TTF／OTF／WOFF／WOFF2 互轉 | fontTools + brotli | 已完成 |
| 20 | ZIP／tar.gz 打包 | 標準庫 | 已完成 |

## 3.2 第三階段功能範圍（0.3.0）

| # | 功能 | 做法 | 狀態 |
|---|---|---|---|
| 21 | 完全自足（不依賴電腦上任何其他軟體） | 內附 FFmpeg + LibreOffice（Full 版本） | 已完成 |
| 22 | 引擎下載與驗證工具 | `scripts/fetch_tools.py` + `packaging/tools.lock.json`（固定版本 + SHA-256） | 已完成 |
| 23 | 內附版本優先 | 搜尋順序改為「指定 → 內附 → PATH → 常見位置」 | 已完成 |
| 24 | Lite／Full 兩種發行 | 同一次建置，Full 額外放入 `tools/` | 已完成 |

### 明確排除（避免範圍失控）

- 雲端上傳、帳號系統、線上同步 — 與隱私原則衝突。
- DRM 破解、商業光碟複製 — 法律風險。
- 即時串流轉播、螢幕錄影 — 非「檔案轉換」核心。
- AI 相關功能 — 與「不依賴付費 API」原則衝突。

## 3.3 第五階段功能範圍（0.4.0）

| # | 功能 | 做法 | 狀態 |
|---|---|---|---|
| 25 | 引擎模組化 | `core/modules.py` + `openconvert/modules/manifest.json` | 已完成 |
| 26 | 按需下載 | GUI 設定頁卡片、轉換時詢問、CLI `modules install` | 已完成 |
| 27 | 完整性 | manifest 內 SHA-256；不符即中止並刪除半成品 | 已完成 |
| 28 | 引擎資產發佈 | `engines.yml` 把驗證過的壓縮檔上傳到 `engines-v1` Release | 已完成 |
| 29 | 移除 Full 版本 | 發佈檔不含引擎，體積回到約 90 MB | 已完成 |

取捨：模組需要網路才能第一次使用；對完全離線的機器，可用 `modules install` 在有網路的機器
下載後把 `tools/` 一併複製過去（模組是純檔案，沒有登錄或全域狀態）。

---

## 4. 關鍵設計原則

1. **絕不覆蓋原始檔**
   - 若輸出目標與來源相同，自動改到 `outputs/` 或加上序號。
   - 預設不覆蓋既有檔案，改產生 `名稱 (1).ext`。
   - 覆蓋行為必須由使用者在設定中明確開啟，且仍不允許覆蓋「原始檔」。

2. **失敗要說人話**
   - FFmpeg 的 stderr 會被截取並轉成可讀訊息，而不是直接丟一整段技術輸出。
   - 每個工作保留完整錯誤日誌，可從介面開啟。

3. **UI 執行緒絕不阻塞**
   - 所有轉換在背景執行緒執行。
   - 進度以訊號回傳，UI 只更新顯示。

4. **可取消**
   - 每個工作有獨立的取消旗標；FFmpeg 會被終止，並清理半成品檔案。

5. **離線優先**
   - 除了「開啟 FFmpeg 下載頁」與「檢查更新」外，程式不會發送任何網路請求。
   - 沒有任何遙測。

---

## 5. 風險與對策

| 風險 | 影響 | 對策 |
|---|---|---|
| 使用者機器沒有 FFmpeg | 影片/音訊功能不可用 | 啟動時偵測，介面明確提示並提供安裝指引；圖片/PDF/電子書功能仍可用 |
| 路徑含中文或空白 | 轉換失敗 | 全程使用 `pathlib.Path`，subprocess 以 list 傳參不經過 shell |
| 檔名衝突 | 覆蓋資料 | 唯一檔名產生器 + 單元測試 |
| 大型檔案記憶體爆掉 | 當機 | 媒體走串流（FFmpeg 子程序），PDF 抽頁用 `pypdf` 逐頁寫入，圖片逐張處理 |
| 打包後找不到資源 | 啟動失敗 | 資源路徑統一由 `resources.py` 解析，同時支援原始碼與 PyInstaller |
| 防毒誤判 | 使用者不敢執行 | 提供 `--onedir`、不混淆、程式碼完全公開、CI 產物可驗證 |

---

## 6. 驗證方式

第一階段的「完成」定義：

1. `pytest` 全綠，且測試會**實際產生檔案並驗證內容**（不是只驗證函式被呼叫）。
2. 手動在 Windows 上以 `python -m openconvert` 啟動，完成一次影片、圖片、PDF、CBZ→EPUB 轉換。
3. `python -m openconvert --version` 與 `--help` 可運作。
4. CI 在乾淨環境可重現測試結果。

---

## 7. 目前狀態（0.1.0，2026-11-15）

| 驗證項目 | 狀態 | 說明 |
| --- | --- | --- |
| pytest | 完成 | 102 個測試，含真實檔案產出、內容比對、錯誤路徑 |
| 靜態檢查 | 完成 | `ruff check` 與 `ruff format --check` 全綠 |
| GUI 實際操作 | 完成 | 離屏 Qt 平台啟動、加入檔案、PNG → JPEG 轉換成功；另以截圖檢視深色／淺色版面 |
| 引擎手動驗證 | 完成 | 凍結版 CLI 實際轉出 JPEG、PDF → PNG、MP4 → MP3、圖片 → EPUB |
| 打包版啟動 | 完成 | `dist/OpenConvert/OpenConvert.exe` 可啟動且不閃退（含 GUI 與 CLI 兩支執行檔） |
| CI 重現 | 完成 | [執行紀錄](https://github.com/oooxoxxx/OpenConvert/actions/runs/43669505859)：Linux（3.10／3.13）、macOS、Windows 測試與 Windows 打包共 5 個 job 全數通過 |

尚未完成（刻意留到後續版本）：安裝程式（MSI／`.app`／AppImage）、macOS 簽章與公證、
失敗工作一鍵重試、輸出檔名樣板。
