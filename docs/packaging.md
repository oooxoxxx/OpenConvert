# 打包與發佈

本文件說明如何把 OpenConvert 打包成不需要 Python 環境的可執行版本，以及發佈流程。

## 為什麼是 onedir 而不是 onefile

- 啟動快：onefile 每次執行都要把 PySide6 解壓到暫存目錄（數秒）。
- 可放外部工具：使用者可把 `ffmpeg.exe`／`ffprobe.exe` 放進 `OpenConvert/tools/`。
- 防毒誤判較少：onefile 的自我解壓行為常被標記。

## 本機建置

```powershell
.venv\Scripts\activate
pip install -e ".[dev]"
pyinstaller packaging\openconvert.spec --noconfirm
```

產物：

```
dist/OpenConvert/
  OpenConvert.exe        # 圖形介面
  OpenConvertCLI.exe     # 命令列（與 GUI 共用函式庫）
  tools/                 # 可自行放入 ffmpeg.exe / ffprobe.exe
  _internal/             # Python、Qt、Pillow、pypdfium2 等
```

驗證：

```powershell
dist\OpenConvert\OpenConvert.exe
dist\OpenConvert\OpenConvertCLI.exe formats
```

- 視窗應正常開啟，側邊欄五個頁面可切換。
- 「設定」頁應顯示 FFmpeg 與 LibreOffice 狀態；若系統已安裝，會顯示版本。
- `OpenConvertCLI.exe` 應列出十個格式類別，且可實際轉檔：

  ```powershell
  dist\OpenConvert\OpenConvertCLI.exe formats
  dist\OpenConvert\OpenConvertCLI.exe convert sample.png -t jpg -o out
  dist\OpenConvert\OpenConvertCLI.exe convert sample.png -t avif -o out       # 新圖片格式
  dist\OpenConvert\OpenConvertCLI.exe convert movie.srt -t sub-vtt -o out     # 字幕
  dist\OpenConvert\OpenConvertCLI.exe convert data.csv -t data-json -o out    # 資料
  dist\OpenConvert\OpenConvertCLI.exe convert font.ttf -t font-woff2 -o out   # 字型
  dist\OpenConvert\OpenConvertCLI.exe convert report.docx -t docx-pdf -o out  # 需要 LibreOffice
  ```

### 內含 FFmpeg 的可攜式版本

若你（在法律允許的前提下）要散布含 FFmpeg 的版本：

1. 把 `ffmpeg.exe`、`ffprobe.exe` 放進 `dist/OpenConvert/tools/`。
2. 確認你遵守 FFmpeg 的授權（LGPL 或 GPL，視建置選項而定），並附上授權文字與原始碼取得方式。

本專案的 MIT 授權只涵蓋 OpenConvert 自己的程式碼。CI 產物**不含** FFmpeg。

### LibreOffice

LibreOffice 安裝體積大、平台相依性高，不適合做成可攜式工具；請使用者自行安裝。
OpenConvert 會在啟動轉換前偵測，找不到時只有 Office 相關目標會回報明確訊息，
其餘格式（圖片、PDF、字幕、資料、字型…）完全不受影響。

## 版本號

版本號只在 `openconvert/__init__.py` 的 `__version__` 與 `pyproject.toml` 的 `version` 兩處，
發版前請同步更新，並在 `CHANGELOG.md` 補上該版本小節。

## 發佈流程（Windows）

1. 更新版本號與 `CHANGELOG.md`。
2. 跑完 `pytest`、`ruff check`、`ruff format --check`。
3. 建立標籤並推送：

   ```powershell
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. `.github/workflows/release-windows.yml` 會自動：
   - 檢查標籤與程式版本一致
   - 建置 PyInstaller 產物
   - 壓成 `OpenConvert-0.2.0-windows-x64.zip`
   - 建立 GitHub Release 並附上 ZIP

也可以從 Actions 頁面手動觸發（`workflow_dispatch`），此時只上傳 artifact、不建立 Release。

## 簽章與 SmartScreen

未簽章的執行檔在 Windows 上會出現 SmartScreen 警告。若要正式散布，建議：

- 使用程式碼簽章憑證（EV 憑證可立即取得信譽）；
- 或提供 SHA-256 檢查碼，讓使用者自行比對：

  ```powershell
  Get-FileHash OpenConvert-0.2.0-windows-x64.zip -Algorithm SHA256
  ```

## 其他平台

macOS 與 Linux 目前沒有自動打包流程，但 spec 檔可重複使用：

```bash
pyinstaller packaging/openconvert.spec --noconfirm
```

- macOS：需要 `.app` bundle（可在 spec 加入 `BUNDLE`），且未簽章／未公證的 App 會被 Gatekeeper 阻擋。
- Linux：建議另外提供 `.deb`／AppImage，並確認 Qt 的 xcb 相依套件已列在依賴中。

## 常見問題

| 症狀 | 原因與處理 |
| --- | --- |
| 啟動即關閉、沒有訊息 | 用 `console=True` 重新建置一次看 traceback，或從命令列執行 `OpenConvert.exe` |
| 找不到 Qt 平台外掛 | 確認 `_internal/PySide6/plugins/platforms/` 存在；不要手動搬動 `_internal` 內的檔案 |
| PDF → 圖片失敗，提示 pypdfium2 | spec 的 `collect_dynamic_libs("pypdfium2_raw")` 未被執行，重新建置 |
| 影片轉換說找不到 FFmpeg | 把 `ffmpeg.exe` 放進 `tools/`，或在「設定」頁指定路徑 |
| 防毒誤報 | 送交廠商誤報回報；不要用 UPX 壓縮（spec 已關閉） |
