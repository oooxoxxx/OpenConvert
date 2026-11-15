# 變更紀錄

本檔案格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號遵循 [語意化版本](https://semver.org/lang/zh-TW/)。

## [Unreleased]

### 預計

- 轉換失敗後一鍵重試
- 拖放排序與輸出檔名樣板
- 影片裁剪與字幕嵌入

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
