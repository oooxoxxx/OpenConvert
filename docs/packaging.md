# 打包與發佈

本文件說明如何把 OpenConvert 打包成不需要 Python 環境的可執行版本，以及發佈流程。

## 發佈形態：模組化

自 0.4.0 起，發佈檔**不含任何引擎**，只有主程式（約 90 MB）。引擎（FFmpeg、LibreOffice）
是獨立的「模組」，由程式在需要時從本專案的 GitHub Release 資產下載：

- 引擎清單與 SHA-256：`openconvert/modules/manifest.json`
- 引擎資產：GitHub Release 標籤 `engines-v1`
- 安裝位置：程式旁的 `tools/`；不可寫時退回到使用者資料夾 `engines/`
- 雜湊不符、沒有網路或平台未提供時，會給明確錯誤並中止，不會執行未經驗證的內容

這樣的好處：發佈檔小、不用 GPL 元件也能用大多數功能、需要什麼才下載什麼。

## 為什麼是 onedir 而不是 onefile

- 啟動快：onefile 每次執行都要把 PySide6 解壓到暫存目錄（數秒）。
- 可放外部工具：使用者可把引擎模組或自備的 `ffmpeg.exe` 放進 `OpenConvert/tools/`。
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
  _internal/             # Python、Qt、Pillow、pypdfium2、模組清單等
```

驗證：

```powershell
dist\OpenConvert\OpenConvert.exe
dist\OpenConvert\OpenConvertCLI.exe formats
dist\OpenConvert\OpenConvertCLI.exe modules list
```

- 視窗應正常開啟，側邊欄五個頁面可切換。
- 「設定 → 引擎模組」應列出 FFmpeg 與 LibreOffice（未安裝）。
- `OpenConvertCLI.exe` 應列出十個格式類別，且不需引擎的功能可直接轉檔：

  ```powershell
  dist\OpenConvert\OpenConvertCLI.exe convert sample.png -t jpg -o out
  dist\OpenConvert\OpenConvertCLI.exe convert sample.png -t avif -o out
  dist\OpenConvert\OpenConvertCLI.exe convert movie.srt -t sub-vtt -o out
  dist\OpenConvert\OpenConvertCLI.exe convert data.csv -t data-json -o out
  dist\OpenConvert\OpenConvertCLI.exe convert font.ttf -t font-woff2 -o out
  ```

## 引擎模組

### 使用者怎麼取得

- **GUI**：設定 → 引擎模組 →「下載」；或在轉換時按提示下載（有進度條、可取消）。
- **CLI**：

  ```powershell
  OpenConvertCLI.exe modules list
  OpenConvertCLI.exe modules install ffmpeg
  OpenConvertCLI.exe modules install libreoffice
  OpenConvertCLI.exe modules remove ffmpeg
  ```

安裝後的結構：

```
tools/ffmpeg/ffmpeg.exe
tools/ffmpeg/ffprobe.exe
tools/libreoffice/program/soffice.exe
tools/THIRD-PARTY-NOTICES.txt        # 自動產生的授權聲明
```

### 開發者／發佈：維護引擎資產

1. 更新 `openconvert/modules/manifest.json`（新的引擎版本、網址與 SHA-256）。
2. 手動執行 `.github/workflows/engines.yml`（`workflow_dispatch`），它會：
   - 在 Windows 與 Linux runner 上用 `scripts/fetch_tools.py --collect assets` 下載並驗證引擎；
   - 把壓縮檔上傳到 `engines-v1` Release（`gh release upload --clobber`）。
3. 由於 manifest 內含 SHA-256，任何來源檔變動都會讓下載失敗，這是刻意的保護。

本地預覽清單與狀態：

```powershell
python scripts\fetch_tools.py --list
python scripts\fetch_tools.py --only ffmpeg          # 安裝到 tools/
python scripts\fetch_tools.py --collect assets\      # 只下載＋驗證
```

**支援的平台**：目前 Windows x64 有 FFmpeg 與 LibreOffice，Linux x64 只有 FFmpeg。
其他平台（macOS、arm64）會回報「此平台未提供」，不會偷偷下載來路不明的檔案。

### 授權（下載模組時自動處理）

- FFmpeg 使用 BtbN 的 **GPL 建置**（`--enable-gpl --enable-libx264 --enable-libx265`）。
- LibreOffice 為 **MPL-2.0**。
- 安裝模組後，`tools/THIRD-PARTY-NOTICES.txt` 會列出授權、版本、網址與原始碼取得方式。
- OpenConvert 本身的程式碼仍為 MIT；引擎都是獨立程式，以子程序呼叫，不與本專案連結。
- 沒有安裝模組時，發佈檔**不含**任何 GPL／MPL 元件。

### 也可以不透過模組

使用者可以自行安裝系統版 FFmpeg／LibreOffice，或手動放入：

```
tools/ffmpeg/ffmpeg.exe                 # 或 tools/ffmpeg.exe、tools/bin/...
tools/libreoffice/program/soffice.exe
```

搜尋順序是「設定頁指定 → 模組／`tools/` → 系統 PATH → 常見安裝位置」，
設定頁會以「（模組）」標示由 OpenConvert 管理的引擎。

LibreOffice 的無介面轉換每次都使用獨立的 `-env:UserInstallation` 暫時設定檔，
因此模組版不會與使用者自己安裝的版本互相鎖定或污染設定。

## 版本號

版本號只在 `openconvert/__init__.py` 的 `__version__` 與 `pyproject.toml` 的 `version` 兩處，
發版前請同步更新，並在 `CHANGELOG.md` 補上該版本小節。

## 發佈流程（Windows）

1. 確認 `engines-v1` Release 存在且 manifest 的 SHA-256 與資產一致（必要時執行 `engines.yml`）。
2. 更新版本號與 `CHANGELOG.md`。
3. 跑完 `pytest`、`ruff check`、`ruff format --check`。
4. 建立標籤並推送：

   ```powershell
   git tag v0.4.0
   git push origin v0.4.0
   ```

5. `.github/workflows/release-windows.yml` 會自動：
   - 檢查標籤與程式版本一致
   - 建置 PyInstaller 產物並壓成 `OpenConvert-0.4.0-windows-x64.zip`
   - 建立 GitHub Release 並附上 ZIP

若只是要驗證流程，可用 `workflow_dispatch` 手動執行（只上傳 artifact、不建立 Release）。

## 簽章與 SmartScreen

未簽章的執行檔在 Windows 上會出現 SmartScreen 警告。若要正式散布，建議：

- 使用程式碼簽章憑證（EV 憑證可立即取得信譽）；
- 或提供 SHA-256 檢查碼，讓使用者自行比對：

  ```powershell
  Get-FileHash OpenConvert-0.4.0-windows-x64.zip -Algorithm SHA256
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
| 影片轉換說找不到 FFmpeg | `modules install ffmpeg`，把 `ffmpeg.exe` 放進 `tools/`，或在「設定」頁指定路徑 |
| 模組下載失敗 | 檢查網路；確認 `engines-v1` Release 存在；manifest 的 SHA-256 與來源檔不符時會刻意中止 |
| 防毒誤報 | 送交廠商誤報回報；不要用 UPX 壓縮（spec 已關閉） |
