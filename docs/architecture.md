# OpenConvert — 架構設計

## 分層

```
┌──────────────────────────────────────────────┐
│  GUI (PySide6)                               │
│  pages / widgets / theme                     │
│  只負責顯示與使用者輸入，不含轉換邏輯           │
└───────────────┬──────────────────────────────┘
                │ Qt signals / slots
┌───────────────▼──────────────────────────────┐
│  Application layer                           │
│  ConversionQueue (QThreadPool)               │
│  Job model + 狀態機                           │
└───────────────┬──────────────────────────────┘
                │ 純 Python 呼叫
┌───────────────▼──────────────────────────────┐
│  Converter layer                             │
│  media / image / pdf / ebook / document /    │
│  data / subtitle / font / archive             │
│  統一介面：convert(ctx) -> list[Path]         │
└───────────────┬──────────────────────────────┘
                │ subprocess / 函式庫
┌───────────────▼──────────────────────────────┐
│  Engines                                     │
│  FFmpeg · LibreOffice（外部程式）             │
│  Pillow · pypdf · pypdfium2 · fontTools ·    │
│  python-docx · openpyxl · Markdown · bs4 ·   │
│  PyYAML／tomli-w · zipfile／tarfile           │
└──────────────────────────────────────────────┘
```

**核心規則：`core/` 與 `converters/` 完全不知道 Qt 的存在。**
這讓轉換引擎可以被 CLI、測試或日後的 Web 前端重用，也讓單元測試不需要啟動 GUI。

## 目錄結構

```
openconvert/
├── __init__.py          # 版本號
├── __main__.py          # python -m openconvert
├── cli.py               # 無 GUI 的批次模式
├── app.py               # QApplication 啟動、主題、單一實例
├── runner.py            # QThreadPool 佇列與訊號（GUI 與引擎的橋樑）
├── core/
│   ├── errors.py        # 例外階層
│   ├── kinds.py         # 檔案類型判定（副檔名 → MediaKind）
│   ├── targets.py       # 目標宣告（82 個目標、分組規則、預設選擇）
│   ├── job.py           # Job 資料模型與狀態
│   ├── paths.py         # 輸出路徑、唯一檔名、安全檢查
│   ├── settings.py      # 使用者設定（JSON 持久化）
│   ├── history.py       # JSONL 轉換紀錄
│   ├── inspect.py       # 檔案資訊摘要
│   ├── modules.py       # 引擎模組管理（下載、驗證、安裝、移除）
│   ├── textio.py        # 文字編碼偵測與讀寫
│   ├── sorting.py       # 檔名自然排序
│   ├── imaging.py       # Pillow 引擎初始化（HEIF 註冊）
│   ├── ffmpeg.py        # 尋找 ffmpeg/ffprobe、執行與進度解析
│   ├── office.py        # 尋找 LibreOffice、無介面轉換
│   └── resources.py     # 資源路徑（原始碼 / PyInstaller）
├── modules/
│   └── manifest.json    # 引擎模組清單（用途、授權、SHA-256）
├── converters/
│   ├── base.py          # Converter 抽象基底 + ConvertContext
│   ├── media.py         # 影片 + 音訊 + 抽影格 + 圖片轉影片
│   ├── image.py         # 圖片
│   ├── pdf.py           # PDF
│   ├── ebook.py         # CBZ / EPUB
│   ├── document.py      # Markdown / HTML / DOCX / Office
│   ├── data.py          # CSV / JSON / XLSX / YAML / TOML
│   ├── subtitle.py      # SRT / VTT / ASS
│   ├── font.py          # TTF / OTF / WOFF / WOFF2
│   ├── archive.py       # ZIP / tar.gz
│   └── markup.py        # Markdown／HTML 共用工具
├── gui/
│   ├── main_window.py
│   ├── theme.py         # 深色 / 淺色 QSS
│   ├── icons.py         # 內嵌 SVG 圖示
│   ├── pages/
│   │   ├── convert.py
│   │   ├── inspect.py
│   │   ├── history.py
│   │   ├── settings.py
│   │   └── about.py
│   └── widgets/
│       ├── drop_zone.py
│       ├── job_table.py
│       ├── toast.py
│       └── sidebar.py
└── tests/               # 見 tests/
```

## Job 狀態機

```
        ┌─────────┐
        │ PENDING │
        └────┬────┘
             │ start
        ┌────▼────┐   cancel    ┌───────────┐
        │ RUNNING ├────────────►│ CANCELLED │
        └────┬────┘             └───────────┘
             │ ok        fail
        ┌────▼────┐   ┌──▼─────┐
        │  DONE   │   │ FAILED │
        └─────────┘   └────────┘
             │ 不支援格式
        ┌────▼────┐
        │ SKIPPED │
        └─────────┘
```

終止狀態（DONE / FAILED / CANCELLED / SKIPPED）不可再轉移；重試會建立新 Job。

## 執行緒模型

- `ConversionQueue` 內含一個 `QThreadPool`，`maxThreadCount` 由設定決定（預設 2）。
- 每個 Job 包成 `QRunnable`；回報訊號透過一個 `QObject`（`JobSignals`）發出。
- 取消使用 `threading.Event`，FFmpeg 子程序會收到 terminate。
- **FFmpeg 併發預設較低**（同一時間最多 2 個），避免一般筆電 CPU 滿載；圖片可開到 4。

## 進度計算

| 轉換器 | 進度來源 |
|---|---|
| 影片 / 音訊 | FFmpeg `-progress pipe:1` 的 `out_time_us ÷ 總時長` |
| 抽影格 / 圖片轉影片 | 同 FFmpeg（以總時長回報） |
| 圖片 | 批次內第 n / 總數（單檔為 0 → 1） |
| PDF 合併 / 抽頁 | 已處理頁數 ÷ 總頁數 |
| PDF → 圖片 / CBZ / 純文字 | 已處理頁數 ÷ 總頁數 |
| EPUB / CBZ | 已處理頁面 ÷ 總頁面 |
| 文件 / 資料 / 字幕 / 字型 / 壓縮 | 各階段的固定進度點（讀取 → 寫入 → 完成） |

## 輸出安全規則

1. `resolve_output()` 保證回傳的路徑**不等於**來源路徑。
2. 預設 `overwrite=False`：若目標存在，產生 `名稱 (1).ext`、`名稱 (2).ext`……
3. 轉換失敗時刪除半成品，不留下 0 byte 或損壞檔案。
4. 多輸出（PDF → 圖片、抽取頁面）輸出到**新目錄**，不與既有檔案混在一起。

## 設定項目

| 鍵 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `theme` | `"dark"` / `"light"` / `"system"` | `system` | 主題 |
| `output_dir` | `str` / `null` | `null` | `null` = 與來源同資料夾 |
| `overwrite` | `bool` | `false` | 是否覆蓋既有輸出 |
| `concurrency` | `int` | `2` | 同時轉換數量 |
| `ffmpeg_path` | `str` / `null` | `null` | 自訂 ffmpeg 路徑 |
| `ffprobe_path` | `str` / `null` | `null` | 自訂 ffprobe 路徑 |
| `office_path` | `str` / `null` | `null` | 自訂 soffice 路徑 |

## 引擎模組（模組化）

引擎不在發佈檔內，由 `core/modules.py` 按 `openconvert/modules/manifest.json` 管理：

```
manifest.json ── 讀取 ──► modules.install(id)
                              │  下載（SHA-256 驗證、可取消）
                              ▼
tools/ffmpeg/{ffmpeg.exe,ffprobe.exe}      # 優先；不可寫時退回 user engines/
tools/libreoffice/program/soffice.exe
tools/THIRD-PARTY-NOTICES.txt              # 安裝後自動產生
```

- `core/resources.py` 的 `module_search_dirs()` 回傳模組可能所在的位置，
  `app_dir()` 在打包後是執行檔所在目錄、從原始碼執行時是專案根目錄，因此 `tools/` 位置一致。
- 引擎搜尋順序：設定頁指定 → **模組／`tools/`** → 系統 PATH → 常見安裝位置。
- `FFmpegTools.managed` 與 `OfficeTools.managed` 標示引擎是否由 OpenConvert 管理，
  設定頁據此顯示「（模組）」。
- GUI 的下載在 `QThread`（`gui/widgets/module_dialog.py`）執行，可取消；轉換頁在需要時
  會以對話框詢問「要不要現在下載」，成功後自動繼續。
- 發佈流程：`engines.yml` 把引擎資產上傳到 `engines-v1` Release；
  應用程式 Release 只含主程式。
| `keep_history` | `bool` | `true` | 是否寫入轉換紀錄 |
| `play_sound` | `bool` | `true` | 完成時提示音 |
| `last_format` | `str` | `"mp4"` | 上次使用的格式 |

## 測試策略

| 層級 | 內容 | 是否需要 GUI |
|---|---|---|
| 單元 | 路徑解析、唯一檔名、類型判定、設定讀寫、EPUB 結構 | 否 |
| 整合 | 真正產生媒體/圖片/PDF 檔案並轉換後驗證 | 否 |
| GUI 煙霧 | 建立 MainWindow、加入檔案、按下開始（不打真的轉換） | 是（offscreen） |

GUI 測試使用 `QT_QPA_PLATFORM=offscreen`，在 CI 上不需要實體螢幕。
