# 支援的格式

本文件由 `openconvert/core/targets.py` 的宣告整理而成，`openconvert-cli formats` 會列出同一份清單。
若兩者不一致，以程式碼為準。

## 來源檔案

| 類型 | 副檔名 |
| --- | --- |
| 影片 | `.mp4` `.mkv` `.webm` `.mov` `.avi` `.m4v` `.flv` `.wmv` `.ts` `.mpg` `.mpeg` |
| 音訊 | `.mp3` `.m4a` `.aac` `.wav` `.flac` `.ogg` `.opus` `.wma` `.aiff` `.alac` |
| 圖片 | `.png` `.jpg` `.jpeg` `.webp` `.bmp` `.tif` `.tiff` `.gif` `.ico` `.avif` `.heic` |
| PDF | `.pdf` |
| 電子書 | `.epub` `.cbz` |

`.gif` 同時被視為圖片與影片來源：可以用圖片方式處理單格，也可以當影片來源轉成 MP4。

## 目標格式

「代號」是命令列 `-t` 與程式內部使用的識別字；GUI 顯示的是「名稱」。

### 影片（需要 FFmpeg）

| 代號 | 名稱 | 輸出 | 說明 |
| --- | --- | --- | --- |
| `mp4` | MP4 影片 | `.mp4` | H.264 + AAC，相容性最好 |
| `mkv` | MKV 影片 | `.mkv` | H.264 + AAC，可容納多字幕軌 |
| `webm` | WebM 影片 | `.webm` | VP9 + Opus，適合網頁 |
| `mov` | MOV 影片 | `.mov` | Apple QuickTime 容器 |
| `avi` | AVI 影片 | `.avi` | 舊式容器，相容老舊播放器 |
| `video-gif` | GIF 動畫 | `.gif` | 無聲動圖，建議縮小解析度 |

### 音訊（需要 FFmpeg）

| 代號 | 名稱 | 輸出 | 說明 |
| --- | --- | --- | --- |
| `mp3` | MP3 音訊 | `.mp3` | 最通用的音訊格式 |
| `m4a` | M4A 音訊 | `.m4a` | AAC 音訊，Apple 裝置常用 |
| `aac` | AAC 音訊 | `.aac` | 原始 AAC 串流 |
| `wav` | WAV 音訊 | `.wav` | 無壓縮，檔案較大 |
| `flac` | FLAC 音訊 | `.flac` | 無損壓縮 |
| `ogg` | OGG 音訊 | `.ogg` | Vorbis 音訊 |
| `opus` | Opus 音訊 | `.opus` | 低流量下音質最好 |

音訊目標同時接受影片來源，也就是可以直接「抽出音軌」。

### 圖片

| 代號 | 名稱 | 輸出 | 說明 |
| --- | --- | --- | --- |
| `png` | PNG 圖片 | `.png` | 支援透明背景 |
| `jpg` | JPEG 圖片 | `.jpg` | 有損壓縮，適合照片 |
| `webp` | WebP 圖片 | `.webp` | 檔案小、支援透明 |
| `bmp` | BMP 圖片 | `.bmp` | 未壓縮點陣圖 |
| `tiff` | TIFF 圖片 | `.tiff` | 印刷與掃描常用（LZW 壓縮） |
| `ico` | ICO 圖示 | `.ico` | Windows 圖示，輸出多種尺寸 |
| `image-gif` | GIF 圖片 | `.gif` | 單格或動畫 GIF |
| `img-pdf` | 合併為 PDF | `.pdf` | 多張圖片合成一份 PDF（合併型） |

透明處理：轉成 JPEG／BMP 等不支援透明的格式時，透明區域會填上白色背景。

### PDF

| 代號 | 名稱 | 輸出 | 說明 |
| --- | --- | --- | --- |
| `pdf-merge` | 合併 PDF | `.pdf` | 兩份以上 PDF 依序合併（合併型） |
| `pdf-extract` | 抽取頁面 | `.pdf` | 用頁碼範圍產生新 PDF，留空表示全部頁面 |
| `pdf-png` | PDF → PNG | `.png` | 每頁輸出一張 PNG（多輸出） |
| `pdf-jpg` | PDF → JPEG | `.jpg` | 每頁輸出一張 JPEG（多輸出） |

頁碼範圍語法：`1-3,7`、`5`、`2-`（第 2 頁到最後）。超出範圍或格式錯誤會回報清楚的錯誤訊息。

### 電子書

| 代號 | 名稱 | 輸出 | 說明 |
| --- | --- | --- | --- |
| `epub` | EPUB 電子書 | `.epub` | 可由 CBZ 轉換，或由整批圖片產生（圖片為合併型） |
| `cbz` | CBZ 漫畫 | `.cbz` | 可由 EPUB 轉換，或由整批圖片產生（圖片為合併型） |

EPUB 由本專案自行產生（`zipfile` + XHTML／OPF／NCX），不依賴 EbookLib，避免 AGPL 授權影響。
EPUB → CBZ 會依 spine 順序取出圖片；檔案損壞、不是 ZIP、或裡面沒有圖片時會回報明確錯誤，
不會產生打不開的輸出。含 DRM 的商業 EPUB 不在支援範圍。

## 選項

| 選項 | 適用目標 | 說明 |
| --- | --- | --- |
| 品質 | 影片、音訊（GIF 動畫除外） | `high`／`balanced`／`small` 對應不同 CRF 與位元率 |
| 最大尺寸 | 影片、圖片 | 依比例縮到最大邊長；`0` 表示原始尺寸 |
| 影像品質 | `jpg`、`webp` | 有損壓縮品質 1–100（預設 90） |
| GIF 影格率 | `video-gif` | 5–30 fps（預設 12） |
| 頁碼範圍 | `pdf-extract` | 例如 `1-3,7` |
| PDF 解析度 | `pdf-png`、`pdf-jpg` | 72／150／300／600 DPI（預設 150） |
| 輸出資料夾 | 全部 | 留空表示與來源檔案相同資料夾 |

命令列的對應參數為 `--quality`、`--max-size`、`--pages`、`--dpi`；`--overwrite` 需明確指定才會覆蓋既有檔案。

## 分組規則（合併型 vs 逐檔）

- **逐檔**：每個來源檔案產生一個輸出（例如 3 張圖片 → 3 個 JPEG）。
- **合併型**：符合條件的檔案合成一個輸出（例如 5 張圖片 → 1 份 PDF）。
- `pdf-merge` 需要至少 2 份 PDF；其他合併型目標 1 個檔案即可。
- 佇列中若同時有符合與不符合的檔案，符合的會合併，其餘各自獨立轉換。

## 輸出命名

- 預設輸出到來源資料夾，`photo.png → photo.jpg`。
- 輸出檔名與來源相同時（例如 `photo.png → photo.png` 重新壓縮），改名為 `photo_converted.png`。
- 同名檔案已存在時自動編號：`photo (1).jpg`、`photo (2).jpg`。
- PDF → 圖片等多輸出轉換會建立新資料夾，例如 `report_pages/`，避免與既有檔案混在一起。
- 檔名中的非法字元會被清理，但中文、日文、韓文檔名會原樣保留。
