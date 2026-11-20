# 變更紀錄

本檔案格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號遵循 [語意化版本](https://semver.org/lang/zh-TW/)。

## [Unreleased]

### 預計

- 轉換失敗後一鍵重試
- 拖放排序與輸出檔名樣板
- 影片裁剪與字幕嵌入
- 掃描型 PDF 的離線 OCR（可做成模組）
- macOS 的引擎模組
- 字幕嵌入（燒錄）與 HEVC／AV1 編碼（需更新精簡 FFmpeg 的啟用清單）
- XML／SQLite／Parquet 資料模組、7z／RAR 壓縮模組
- JPEG XL、EXR 等影像格式

## [0.6.0] - 2026-11-20

「補洞與常用缺口」：新增 13 個目標（總數 82 → 95），全部使用現有引擎，並修復 ODS 資料轉換。
測試 194 → 217 個。

### 新增

- **影片**：合併影片（多支 → 一支 MP4，參數一致時無損串接、不同時自動補邊重編碼）、
  截取片段（起訖時間，可填秒數或 `1:30`）、影片旋轉／翻轉（90／180／270／水平／垂直）。
- **音訊**：合併音訊（多檔 → 一份 MP3，取樣率不同會自動重採樣）。
- **圖片**：旋轉（90／180／270）、翻轉（水平／垂直）、置中裁切比例（16:9／4:3／1:1／3:2），
  輸出 PNG 無損操作（動畫只處理第一格並明確記錄）。
- **PDF**：加密（AES-128，無 `cryptography` 時退回 RC4-128 並記錄）、解除密碼
  （密碼錯誤給明確訊息）、壓縮（重寫內容串流＋移除重複物件，逐頁回報）。
- **電子書**：EPUB → PDF（文字章節組成 HTML 後交由 LibreOffice 排版；
  純圖片漫畫 EPUB 自動改走圖片組 PDF，頁數正確）。
- **文件**：Markdown → DOCX、HTML → DOCX（HTML 在 LibreOffice 屬 Writer/Web 模組，
  匯出 DOCX 必須明確指定 `MS Word 2007 XML` 濾器——已處理）。
- **GUI**：影片旋轉、圖片旋轉／翻轉、裁切比例、片段起訖、PDF 密碼等選項欄位。

### 修正

- **ODS 資料轉換實為損壞**：`ods → csv/json` 之前交給 openpyxl 會失敗；
  現在直接解析 OpenDocument XML（支援數值／日期／布林／合併儲存格／重複儲存格與工作表選擇），
  不需要 LibreOffice。
- `office.version_of` 在 Windows 改問 `soffice.com`（`soffice.exe --version` 沒有輸出）。

### 其他

- 新增執行期相依 `cryptography`（Apache-2.0／BSD，PDF AES 加密用；無此套件時退回 RC4-128）。

## [0.5.0] - 2026-11-18

**模組精簡化 + 系統優先**。引擎模組大幅縮小，且電腦上已裝有引擎時直接用系統的、不下載。
測試 192 → 194 個。

### 新增

- **精簡版 FFmpeg 模組**：以 BtbN 的建置系統自製，只編譯 OpenConvert 用到的
  libx264／libmp3lame／libopus／libvorbis／libtheora／libvpx（`--disable-autodetect`），
  **下載體積從 195 MB 降到 32.5 MB**。18 項轉換（各容器、抽音軌、GIF、影格、圖片轉影片）
  全部實測通過，編碼器與完整版一致。
- **剝離版 LibreOffice 模組**：從官方 MSI 解開後移除圖庫／help／字典／範本／autotext／
  Basic／Python／其他語言資源（只留 zh-TW＋en），**下載體積從 373 MB 降到 269.6 MB**
  （解壓後 1.5 GB → 721 MB）。10 項 Office 轉換與系統版**頁數逐一比對一致**，
  中文字可正常抽取；移除清單完整記錄在壓縮檔內的 `STRIP-MANIFEST.txt`。
- **`scripts/build_libreoffice_module.py`**：剝離流程腳本（CI 與本機共用）。
- **`ffmpeg-min.yml` workflow**：以 BtbN builder 映像交叉編譯精簡 FFmpeg（釘選建置系統版本）。

### 變更

- **引擎搜尋順序改為「系統優先」**：設定頁指定 → **系統已安裝**（PATH／常見位置）→
  模組（`modules/`，不可寫時退回使用者資料夾）→（相容）舊的 `tools/`。
  電腦上已裝有 FFmpeg／LibreOffice 時直接用系統的，**不會下載模組**。
- 模組安裝目標從 `tools/` 改為 **`modules/`**，內容視為暫存（可隨時刪除、重下即還原）；
  0.4.0 裝在 `tools/` 的引擎仍會被偵測到，不需重裝。
- 引擎資產改放在 **`engines-v2`** Release；manifest 對應更新。
- `office.version_of` 在 Windows 改問 `soffice.com`（`soffice.exe --version` 沒有輸出）。

## [0.4.0] - 2026-11-17

**完全模組化**：引擎不再內附，改為「需要什麼下載什麼」，全部從 GitHub 取得並以 SHA-256 驗證。
測試 185 → 192 個。

### 新增

- **引擎模組管理 `core/modules.py`**：讀取 `openconvert/modules/manifest.json`、
  下載（有進度、可取消）、SHA-256 驗證、解壓（ZIP／tar.xz／MSI）、安裝、狀態查詢與移除。
- **模組清單 `openconvert/modules/manifest.json`**：每個模組的用途、授權、各平台下載網址、
  SHA-256 與大小。下載來源是**我們自己的 GitHub Release 資產**（`engines-v1` 標籤）。
- **設定頁「引擎模組」卡片**：顯示每個模組的狀態／大小／授權，可下載（含進度條）、移除。
- **轉換時按需詢問**：選了需要引擎的格式但尚未安裝時，會詢問是否現在下載，下載完成後自動繼續。
- **CLI**：`openconvert modules list|install <id>|remove <id>`；`convert` 在缺少引擎時會提示安裝指令。
- **安裝位置**：優先程式旁的 `tools/`（可攜式）；不可寫時退回到使用者資料夾 `engines/`。
- **授權聲明自動產生**：安裝模組後寫入 `tools/THIRD-PARTY-NOTICES.txt`。
- **`scripts/fetch_tools.py`**：改為包裝模組管理核心，並新增 `--collect`（收集引擎資產供發佈）與 `--list`。
- **`engines.yml` workflow**：手動執行，把引擎資產上傳到 `engines-v1` Release（Windows 與 Linux）。

### 變更

- **移除 Full（預先內附引擎）版本**；發佈只剩輕量 ZIP，引擎全部走模組下載。
- `FFmpegTools.bundled`／`OfficeTools.bundled` 更名為 `managed`（由 OpenConvert 管理的引擎）。
- 引擎搜尋順序改為：設定指定 → **已安裝模組／tools/** → 系統 PATH → 常見安裝位置。
- LibreOffice 無介面轉換加上 `--nofirststartwizard`。
- `resources.app_dir()` 從原始碼執行時回傳專案根目錄，讓 `tools/` 位置語意一致。

### 授權

- FFmpeg 模組為 **GPL-3.0-or-later**（含 libx264／libx265），LibreOffice 模組為 **MPL-2.0**；
  兩者都重新寄放於本專案的 GitHub Release 資產，並附授權與原始碼取得方式。
- OpenConvert 本身維持 **MIT**；引擎皆為獨立子程序，不與本專案連結。
- 沒有安裝任何模組時，發佈檔**不含** GPL／MPL 元件。

## [0.3.0] - 2026-11-16

「完全自足」版本：推出內含外部引擎的 **Full** 版本，電腦上不需要先安裝 FFmpeg 或 LibreOffice
也能完整轉換；原本的 **Lite** 版本（約 90 MB）繼續提供。測試 171 → 185 個。

### 新增

- **Full 版本（自足）**：安裝包內附 FFmpeg 與 LibreOffice，離線即可完成影片、音訊與 Office 排版轉換。
- **建置工具 `scripts/fetch_tools.py`**：依 `packaging/tools.lock.json` 的固定版本與 SHA-256
  下載引擎、驗證雜湊、解壓縮並放進 `tools/`。
- **`packaging/tools.lock.json`**：FFmpeg（BtbN GPL 版，含 libx264／libx265，pin 到有日期的 autobuild）
  與 LibreOffice（官方 MSI，pin 版本 26.2.7）的下載來源與雜湊。
- **尋找順序**：兩個引擎都改為「使用者指定 → **安裝包內附** → 系統 PATH → 常見安裝位置」，
  內附版本一律優先，不受電腦上其他版本影響。
- **設定頁**：FFmpeg 與 LibreOffice 狀態會標示「（內附）」。
- **隨附授權聲明**：打包時自動產生 `tools/THIRD-PARTY-NOTICES.txt`（FFmpeg GPL、LibreOffice MPL）。
- **Release 流程**：同時產出 Lite 與 Full 兩個 ZIP，並在打包後驗證 Full 內含引擎。

### 變更

- `app_dir()` 從原始碼執行時改為回傳**專案根目錄**（原本是套件目錄），讓 `tools/` 的位置
  在原始碼與打包兩種情境下語意一致。
- `FFmpegTools` 與 `OfficeTools` 新增 `bundled` 欄位，用來區分內附與系統版本。
- LibreOffice 無介面轉換額外加上 `--nofirststartwizard`，首次啟動更穩定。

### 授權

- **FFmpeg 為 GPL-3.0-or-later**（含 libx264／libx265），隨 Full 版本散布；對應原始碼與建置腳本
  取得方式已寫入 `tools/THIRD-PARTY-NOTICES.txt`。**LibreOffice 為 MPL-2.0**。
- OpenConvert 本身的原始碼仍為 MIT；FFmpeg 與 LibreOffice 都是獨立程式（以子程序呼叫），
  不與本專案連結。

## [0.2.0] - 2026-11-15

「全能」版本：把可離線轉換的格式一次補齊，目標數從 20 個增加到 82 個，測試從 102 個增加到 169 個。

### 新增

- **新檔案類型**：文字（TXT／Markdown）、網頁（HTML）、Office 文件（DOCX／DOC／ODT／RTF／PPTX／PPT／ODP）、
  試算表（XLSX／XLSM／XLS／ODS）、資料（CSV／TSV／JSON／YAML／TOML）、字幕（SRT／VTT／ASS／SSA）、字型（TTF／OTF／WOFF／WOFF2）。
- **文件轉換**：Markdown ⇄ HTML、HTML／DOCX → 純文字或 Markdown、DOCX → HTML；
  需要完整排版的目標（DOCX／MD／HTML／TXT／ODT／RTF／PPTX／ODP／XLSX／XLS／ODS → PDF 等）透過 **LibreOffice** 完成。
- **資料轉換**：CSV／TSV／JSON／XLSX／YAML／TOML 互相轉換，可指定工作表。
- **字幕轉換**：SRT／WebVTT／ASS 互轉，自動辨識 UTF-8／Big5／GB18030 等編碼。
- **字型轉換**：TTF／OTF／WOFF／WOFF2 互轉（無損）。
- **壓縮**：把佇列中的檔案打包成 ZIP 或 tar.gz（接受所有支援的類型）。
- **圖片**：新增 AVIF、HEIC（pillow-heif）、APNG（保留動畫）；動畫 GIF／WebP／APNG 互轉會保留影格。
- **PDF**：新增「PDF → 純文字」與「PDF → CBZ」。
- **電子書**：新增「文字／Markdown／HTML → EPUB」（依標題分章並產生目錄）、「EPUB → 純文字」、「CBZ → PDF」。
- **影片／音訊**：新增 M4V／FLV／WMV／OGV／TS 容器、M4B／AIFF／WMA／AC3 音訊、
  「抽出影格（PNG）」與「圖片轉影片（MP4）」。
- **LibreOffice 偵測**：與 FFmpeg 相同的外部引擎定位（設定頁顯示狀態、可指定路徑、缺少時只有 Office 目標失敗）。
- **GUI**：新增影格率、工作表選項與 LibreOffice 設定卡。
- **CLI**：新增 `--fps`、`--frame-seconds`、`--sheet`、`--office`。
- **檔案資訊頁**：文字／資料／字幕顯示行數、字元數、編碼與預覽；字型顯示家族、樣式與字符數；Office 檔案顯示格式與內部項目數。

### 修正

- 動畫圖片在轉換前被 `convert()` 壓成單張，導致 GIF／APNG 動畫全部消失；改為動畫路徑不做色彩模式轉換。
- ASS 輸出時斜體／粗體標籤內的大括號被自己的跳脫邏輯破壞；改為先跳脫原文再插入標籤。
- EPUB → 純文字時把 `<title>` 當成內文；改為忽略 `<head>`。
- 合併型目標的可用性判斷會誤擋「文字 → EPUB」（來源不是圖片時不該要求組員數量）。
- `tar.gz` 目標遇到同名檔案時輸出 `archive.tar (1).gz`；改為 `archive (1).tar.gz`。

### 授權

- 新增的執行期相依全部為寬鬆授權（MIT／BSD）：python-docx、openpyxl、PyYAML、tomli-w、Markdown、
  beautifulsoup4、markdownify、fonttools、brotli、pillow-heif。FFmpeg 與 LibreOffice 仍為**外部程式**，不內嵌。

## [0.1.0] - 2026-11-15

第一個可用版本：圖形介面、命令列與轉換引擎皆已完成，102 個自動化測試通過。

### 新增

- **圖形介面**：側邊欄導覽、拖放加入檔案、轉換佇列、逐檔與整體進度、深色／淺色主題、Toast 提示。
- **轉換引擎**
  - 影片：MP4／MKV／WebM／MOV／AVI／GIF 動畫（H.264／VP9、品質預設、最大解析度）
  - 音訊：MP3／M4A／AAC／WAV／FLAC／OGG／Opus，可從影片抽出音軌
  - 圖片：PNG／JPEG／WebP／BMP／TIFF／ICO／GIF，透明背景處理、等比例縮放、多張合併 PDF
  - PDF：合併、抽取頁碼範圍、每頁輸出 PNG／JPEG（可選 DPI）
  - 電子書：CBZ ⇄ EPUB、整批圖片產生 EPUB／CBZ（自製 EPUB 產生器，不依賴 AGPL 元件）
- **檔案資訊頁**：FFprobe 中繼資料與串流列表，非影音檔顯示檔案層級資訊。
- **轉換紀錄頁**：歷史列表、狀態、輸出路徑、開啟輸出所在資料夾、清除紀錄。
- **設定頁**：FFmpeg 路徑與狀態、輸出資料夾、併發數、覆寫開關、主題、歷史紀錄開關。
- **命令列**：`convert`、`probe`、`formats` 三個子命令，可完全不啟動 Qt 執行批次轉換。
- **FFmpeg 偵測**：設定指定 → `tools/` → `PATH` → 常見安裝路徑 → WinGet Packages 掃描。
- **輸出安全**：不覆蓋原始檔、預設不覆蓋既有檔（自動編號）、失敗或取消時清除半成品。
- **國際化檔案名稱**：中文／日文／韓文路徑與檔名可正常處理，非法字元自動清理。
- **開發基礎建設**：pytest（引擎、GUI、CLI）、ruff lint／format、GitHub Actions 三平台 CI、
  PyInstaller 打包設定、離屏截圖預覽工具。

### 修正

- `resolve_output()` 曾把目標代號當成副檔名（輸出 `clip.video-gif`），改用 `TargetSpec.extension`。
- 未加入檔案時目標下拉選單為空，改為顯示「請先加入檔案」並停用。
- BMP 等無損格式仍顯示「JPEG 品質」選項；改為僅 `jpg`／`webp` 顯示，並更名為「影像品質」。
- 預設目標曾依名稱排序而選到 BMP；改為依宣告順序，並避免預設與來源同格式（PNG → JPEG）。
- 底部 Toast 會蓋住狀態列文字；改為依內容寬度顯示。
- 設定頁捲動區域在部分主題下出現底色方塊。
- 打包後的命令列在非 UTF-8 主控台（例如 Windows cp1252）輸出中文會直接崩潰；改為統一以 UTF-8 輸出。
- EPUB 轉換進度會在寫入階段倒退；改為單調遞增。
