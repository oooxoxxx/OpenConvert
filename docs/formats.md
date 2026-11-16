# 支援的格式

本文件由 `openconvert/core/targets.py` 的宣告整理而成，`openconvert-cli formats` 會列出同一份清單。
若兩者不一致，以程式碼為準。

需要外部引擎的目標只有兩類：**FFmpeg**（影片、音訊）與 **LibreOffice**（Office 排版轉換）。
下載 **Full（自足）版本**時兩者都已內含，不需要另外安裝；**Lite 版本**則需要自行安裝，
或在 `tools/` 放入對應的執行檔（搜尋順序：設定頁指定 → 內附 `tools/` → 系統 PATH → 常見安裝位置）。

## 來源檔案

| 類型 | 副檔名 |
| --- | --- |
| 影片 | `.mp4` `.mkv` `.webm` `.mov` `.avi` `.m4v` `.flv` `.wmv` `.ts` `.mts` `.m2ts` `.mpg` `.mpeg` `.ogv` `.3gp` `.3g2` `.vob` |
| 音訊 | `.mp3` `.m4a` `.m4b` `.aac` `.wav` `.flac` `.ogg` `.opus` `.wma` `.aiff` `.aif` `.alac` `.ac3` `.caf` `.amr` |
| 圖片 | `.png` `.jpg` `.jpeg` `.webp` `.bmp` `.tif` `.tiff` `.gif` `.ico` `.avif` `.heic` `.heif` |
| 文字 | `.txt` `.md` `.markdown` |
| 網頁 | `.html` `.htm` |
| Office 文件 | `.docx` `.doc` `.odt` `.rtf` `.pptx` `.ppt` `.odp` |
| 試算表 | `.xlsx` `.xlsm` `.xls` `.ods` |
| 資料 | `.csv` `.tsv` `.json` `.yaml` `.yml` `.toml` |
| 字幕 | `.srt` `.vtt` `.ass` `.ssa` |
| 字型 | `.ttf` `.otf` `.woff` `.woff2` |
| PDF | `.pdf` |
| 電子書 | `.epub` `.cbz` |

`.gif` 同時被視為圖片與影片來源：可以用圖片方式處理單格，也可以當影片來源轉成 MP4。

## 目標格式

「代號」是命令列 `-t` 與程式內部使用的識別字；GUI 顯示的是「名稱」。
「需求」欄標示該目標需要的**外部引擎**或是否為**合併型**（把符合條件的檔案收成一個輸出）。

### 影片

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `mp4` | MP4 影片 | `.mp4` | FFmpeg | H.264 + AAC，相容性最好 |
| `mkv` | MKV 影片 | `.mkv` | FFmpeg | H.264 + AAC，可容納多字幕軌 |
| `webm` | WebM 影片 | `.webm` | FFmpeg | VP9 + Opus，適合網頁 |
| `mov` | MOV 影片 | `.mov` | FFmpeg | Apple QuickTime 容器 |
| `m4v` | M4V 影片 | `.m4v` | FFmpeg | H.264 + AAC，Apple 裝置常用 |
| `avi` | AVI 影片 | `.avi` | FFmpeg | MPEG-4 + MP3，相容老舊播放器 |
| `flv` | FLV 影片 | `.flv` | FFmpeg | H.264 + AAC，舊式網頁播放器 |
| `wmv` | WMV 影片 | `.wmv` | FFmpeg | Windows Media 格式 |
| `ogv` | OGV 影片 | `.ogv` | FFmpeg | Theora + Vorbis，開源容器 |
| `ts` | TS 影片 | `.ts` | FFmpeg | H.264 + AAC，串流與錄影常用 |
| `video-gif` | GIF 動畫 | `.gif` | FFmpeg | 無聲動圖，建議縮小解析度 |
| `video-frames` | 抽出影格（PNG） | `.png` | FFmpeg | 依指定影格率輸出 PNG，另存到新資料夾（多輸出） |

### 音訊

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `mp3` | MP3 音訊 | `.mp3` | FFmpeg | 最通用的音訊格式 |
| `m4a` | M4A 音訊 | `.m4a` | FFmpeg | AAC 音訊，Apple 裝置常用 |
| `m4b` | M4B 有聲書 | `.m4b` | FFmpeg | AAC 有聲書容器，可記住播放位置 |
| `aac` | AAC 音訊 | `.aac` | FFmpeg | 原始 AAC 串流 |
| `wav` | WAV 音訊 | `.wav` | FFmpeg | 無壓縮，檔案較大 |
| `flac` | FLAC 音訊 | `.flac` | FFmpeg | 無損壓縮 |
| `ogg` | OGG 音訊 | `.ogg` | FFmpeg | Vorbis 音訊 |
| `opus` | Opus 音訊 | `.opus` | FFmpeg | 低流量下音質最好 |
| `aiff` | AIFF 音訊 | `.aiff` | FFmpeg | Apple 無壓縮音訊 |
| `wma` | WMA 音訊 | `.wma` | FFmpeg | Windows Media 音訊 |
| `ac3` | AC3 音訊 | `.ac3` | FFmpeg | 電影常用的環繞音效格式 |

音訊目標同時接受影片來源，也就是可以直接「抽出音軌」。

### 圖片

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `png` | PNG 圖片 | `.png` | — | 支援透明背景 |
| `jpg` | JPEG 圖片 | `.jpg` | — | 有損壓縮，適合照片 |
| `webp` | WebP 圖片 | `.webp` | — | 檔案小、支援透明 |
| `avif` | AVIF 圖片 | `.avif` | — | 新世代格式，壓縮率最佳、支援透明 |
| `heic` | HEIC 圖片 | `.heic` | — | iPhone 預設照片格式（由 pillow-heif 提供） |
| `bmp` | BMP 圖片 | `.bmp` | — | 未壓縮點陣圖 |
| `tiff` | TIFF 圖片 | `.tiff` | — | 印刷與掃描常用（LZW 壓縮） |
| `ico` | ICO 圖示 | `.ico` | — | Windows 圖示，輸出多種尺寸 |
| `image-gif` | GIF 圖片 | `.gif` | — | 單格或動畫 GIF |
| `apng` | APNG 動畫 | `.png` | — | 可保留動畫與透明的 PNG |
| `images-video` | 圖片轉影片 | `.mp4` | FFmpeg + 合併型 | 整批圖片合成一支 MP4 |
| `img-pdf` | 合併為 PDF | `.pdf` | 合併型 | 多張圖片合成一份 PDF |

透明處理：轉成 JPEG／BMP 等不支援透明的格式時，透明區域會填上白色背景。
動畫（GIF／WebP／APNG）在互轉時會保留影格；轉成不支援動畫的格式時只取第一格。

### PDF

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `pdf-merge` | 合併 PDF | `.pdf` | 合併型 | 兩份以上 PDF 依序合併 |
| `pdf-extract` | 抽取頁面 | `.pdf` | — | 用頁碼範圍產生新 PDF，留空表示全部頁面 |
| `pdf-png` | PDF → PNG | `.png` | — | 每頁輸出一張 PNG（多輸出） |
| `pdf-jpg` | PDF → JPEG | `.jpg` | — | 每頁輸出一張 JPEG（多輸出） |
| `pdf-txt` | PDF → 純文字 | `.txt` | — | 抽出文字層；掃描檔沒有文字層時會回報明確錯誤 |
| `pdf-cbz` | PDF → CBZ | `.cbz` | — | 每頁轉成 JPEG 後打包成漫畫壓縮檔 |

頁碼範圍語法：`1-3,7`、`5`、`2-`（第 2 頁到最後）。超出範圍或格式錯誤會回報清楚的錯誤訊息。

### 電子書

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `epub` | EPUB 電子書 | `.epub` | 合併型（圖片時） | 可由 CBZ、整批圖片、TXT／Markdown／HTML 產生 |
| `cbz` | CBZ 漫畫 | `.cbz` | 合併型（圖片時） | 可由 EPUB 或整批圖片產生 |
| `book-pdf` | CBZ → PDF | `.pdf` | — | 把整本漫畫壓縮檔轉成 PDF |
| `epub-txt` | EPUB → 純文字 | `.txt` | — | 依閱讀順序抽出文字，不保留排版 |

EPUB 由本專案自行產生（`zipfile` + XHTML／OPF／NAV），不依賴 AGPL 授權的第三方 EPUB 函式庫。
文字轉 EPUB 時會依 Markdown／HTML 的 H1／H2 標題分章，並產生目錄；純文字則以段落切分。
EPUB → CBZ 會依 spine 順序取出圖片；檔案損壞、不是 ZIP、或裡面沒有圖片時會回報明確錯誤，
不會產生打不開的輸出。含 DRM 的商業 EPUB 不在支援範圍。

### 文件

不需要外部引擎的轉換（Markdown／HTML／DOCX 之間）由本專案直接完成；
標示 **LibreOffice** 的目標需要使用者另外安裝 LibreOffice（與 FFmpeg 相同，不隨專案散布）。

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `md-html` | Markdown → HTML | `.html` | — | 支援表格、程式碼區塊與標題 |
| `html-md` | HTML → Markdown | `.md` | — | 保留標題、清單、連結與表格 |
| `html-txt` | HTML → 純文字 | `.txt` | — | 去除標籤，保留段落 |
| `docx-txt` | DOCX → 純文字 | `.txt` | — | 段落、清單與表格依序輸出 |
| `docx-md` | DOCX → Markdown | `.md` | — | 標題、清單、粗斜體與表格 |
| `docx-html` | DOCX → HTML | `.html` | — | 保留標題與段落結構 |
| `md-pdf` | Markdown → PDF | `.pdf` | LibreOffice | 先轉 HTML 再排版成 PDF |
| `html-pdf` | HTML → PDF | `.pdf` | LibreOffice | 網頁排版成 PDF |
| `txt-pdf` | TXT → PDF | `.pdf` | LibreOffice | 純文字排版成 PDF |
| `docx-pdf` | DOCX → PDF | `.pdf` | LibreOffice | 保留原始排版 |
| `doc-pdf` | DOC → PDF | `.pdf` | LibreOffice | 舊版 Word 檔 |
| `doc-docx` | DOC → DOCX | `.docx` | LibreOffice | 升級成新版 Word 格式 |
| `docx-odt` | DOCX → ODT | `.odt` | LibreOffice | 轉成 LibreOffice Writer 格式 |
| `odt-docx` | ODT → DOCX | `.docx` | LibreOffice | 轉成 Word 格式 |
| `odt-pdf` | ODT → PDF | `.pdf` | LibreOffice | LibreOffice Writer 文件 |
| `rtf-pdf` | RTF → PDF | `.pdf` | LibreOffice | 富文字文件 |
| `pptx-pdf` | PPTX → PDF | `.pdf` | LibreOffice | 簡報轉 PDF |
| `odp-pdf` | ODP → PDF | `.pdf` | LibreOffice | LibreOffice 簡報 |
| `xlsx-pdf` | XLSX → PDF | `.pdf` | LibreOffice | 試算表轉 PDF |
| `xls-pdf` | XLS → PDF | `.pdf` | LibreOffice | 舊版 Excel |
| `xls-xlsx` | XLS → XLSX | `.xlsx` | LibreOffice | 升級成新版 Excel |
| `xlsx-ods` | XLSX → ODS | `.ods` | LibreOffice | 轉成 LibreOffice 試算表 |
| `ods-xlsx` | ODS → XLSX | `.xlsx` | LibreOffice | 轉成 Excel 活頁簿 |
| `ods-pdf` | ODS → PDF | `.pdf` | LibreOffice | LibreOffice 試算表 |

### 資料

表格型來源（CSV／TSV／XLSX）第一列視為欄位名稱；結構型來源（JSON／YAML／TOML）盡量保留巢狀結構。
CSV 輸出使用 UTF-8 BOM，方便 Excel 直接開啟而不亂碼。

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `data-json` | 轉成 JSON | `.json` | — | CSV／TSV／XLSX／YAML／TOML → JSON |
| `data-csv` | 轉成 CSV | `.csv` | — | JSON／XLSX／TSV／YAML → CSV |
| `data-xlsx` | 轉成 XLSX | `.xlsx` | — | CSV／TSV／JSON → Excel 活頁簿 |
| `data-yaml` | 轉成 YAML | `.yaml` | — | JSON／TOML／XLSX → YAML |
| `data-toml` | 轉成 TOML | `.toml` | — | JSON／YAML → TOML |

### 字幕

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `sub-srt` | 轉成 SRT | `.srt` | — | 最通用的字幕格式 |
| `sub-vtt` | 轉成 WebVTT | `.vtt` | — | 網頁播放器使用的字幕格式 |
| `sub-ass` | 轉成 ASS | `.ass` | — | 可指定字型與樣式的進階字幕 |

SRT／VTT 的 `<i>`／`<b>`／`<u>` 標籤會對應成 ASS 的覆寫標籤，反之則去除。
讀取時會自動辨識 UTF-8、UTF-16、Big5（cp950）、GB18030 等常見編碼。

### 字型

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `font-woff` | 轉成 WOFF | `.woff` | — | 網頁字型，相容舊瀏覽器 |
| `font-woff2` | 轉成 WOFF2 | `.woff2` | — | 網頁字型，壓縮率最高（需要 brotli） |
| `font-ttf` | 轉成 TTF | `.ttf` | — | WOFF／WOFF2 → TTF |

WOFF／WOFF2 只是 sfnt 的壓縮容器，轉換為無損。
OTF（CFF 輪廓）無法直接變成 TTF（TrueType 輪廓），遇到時會回報明確錯誤，而不是產出副檔名騙人的檔案。

### 壓縮

| 代號 | 名稱 | 輸出 | 需求 | 說明 |
| --- | --- | --- | --- | --- |
| `zip` | 打包成 ZIP | `.zip` | 合併型 | 把佇列中的檔案合成一個 ZIP |
| `tar-gz` | 打包成 tar.gz | `.tar.gz` | 合併型 | Unix 常見的壓縮封存格式 |

壓縮目標接受任何支援的檔案類型；同名檔案會自動加上序號避免覆蓋。

## 選項

| 選項 | 適用目標 | 說明 |
| --- | --- | --- |
| 品質 | 影片、音訊、`images-video`（GIF 動畫與抽影格除外） | `high`／`balanced`／`small` 對應不同 CRF 與位元率 |
| 最大尺寸 | 影片、圖片、抽影格、圖片轉影片 | 依比例縮到最大邊長；`0` 表示原始尺寸 |
| 影像品質 | `jpg`、`webp`、`avif`、`heic` | 有損壓縮品質 1–100（預設 90） |
| GIF 影格率 | `video-gif` | 5–30 fps（預設 12） |
| 影格率 | `video-frames`、`images-video` | 1–60 fps（預設 30；抽影格預設 1） |
| 頁碼範圍 | `pdf-extract` | 例如 `1-3,7` |
| PDF 解析度 | `pdf-png`、`pdf-jpg`、`pdf-cbz` | 72／150／300／600 DPI（預設 150） |
| 工作表 | `data-*`（來源為 XLSX） | 指定工作表名稱，留空表示第一個工作表 |
| 輸出資料夾 | 全部 | 留空表示與來源檔案相同資料夾 |

命令列的對應參數為 `--quality`、`--max-size`、`--fps`、`--frame-seconds`、`--pages`、`--dpi`、`--sheet`；
`--overwrite` 需明確指定才會覆蓋既有檔案，`--office` 可指定 soffice 執行檔路徑。

## 分組規則（合併型 vs 逐檔）

- **逐檔**：每個來源檔案產生一個輸出（例如 3 張圖片 → 3 個 JPEG）。
- **合併型**：符合條件的檔案合成一個輸出（例如 5 張圖片 → 1 份 PDF）。
- `pdf-merge` 需要至少 2 份 PDF；其他合併型目標 1 個檔案即可。
- 佇列中若同時有符合與不符合的檔案，符合的會合併，其餘各自獨立轉換
  （例如同時放入圖片與 EPUB 要轉 EPUB：圖片合成一本，EPUB 各自處理）。

## 輸出命名

- 預設輸出到來源資料夾，`photo.png → photo.jpg`。
- 輸出檔名與來源相同時（例如 `photo.png → photo.png` 重新壓縮），改名為 `photo_converted.png`。
- 同名檔案已存在時自動編號：`photo (1).jpg`、`photo (2).jpg`；`archive.tar.gz` 會變成 `archive (1).tar.gz`。
- PDF → 圖片、抽影格等多輸出轉換會建立新資料夾，例如 `report_pages/`、`clip_frames/`。
- 檔名中的非法字元會被清理，但中文、日文、韓文檔名會原樣保留。
