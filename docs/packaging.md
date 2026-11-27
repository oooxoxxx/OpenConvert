# 打包與發佈

本文件說明如何把 OpenConvert 打包成不需要 Python 環境的可執行版本，以及發佈流程。

## 發佈形態：模組化 + 精簡引擎

自 0.4.0 起，發佈檔**不含任何引擎**，只有主程式（約 90 MB）。引擎（FFmpeg、LibreOffice）
是獨立的「模組」，由程式在需要時從本專案的 GitHub Release 資產下載：

- 引擎清單與 SHA-256：`openconvert/modules/manifest.json`
- 引擎資產：GitHub Release 標籤 `engines-v2`
- 安裝位置：程式旁的 `modules/`（內容視為**暫存**，可隨時刪除、重下即還原）；
  不可寫時退回到使用者資料夾 `engines/`
- **系統優先**：電腦上已安裝 FFmpeg／LibreOffice 時直接用系統的，不下載模組
- 雜湊不符、沒有網路或平台未提供時，會給明確錯誤並中止，不會執行未經驗證的內容

### 精簡版引擎（0.5.0 起）

| 模組 | 完整版 | 精簡版 | 做法 |
| --- | --- | --- | --- |
| FFmpeg | 195 MB | **32.5 MB** | 自製建置：`--disable-autodetect`，只編譯 libx264／libmp3lame／libopus／libvorbis／libtheora／libvpx |
| LibreOffice | 373 MB（解壓 1.5 GB） | **269.6 MB**（解壓 721 MB） | 官方安裝樹剝離：移除 gallery／help／字典／範本／autotext／Basic／Python／其他語言（只留 zh-TW＋en） |

兩者都經過完整轉換測試（FFmpeg 18 項、LibreOffice 10 項與系統版頁數比對）；
LibreOffice 的移除清單完整記錄在模組內的 `STRIP-MANIFEST.txt`。

## 為什麼是 onedir 而不是 onefile

- 啟動快：onefile 每次執行都要把 PySide6 解壓到暫存目錄（數秒）。
- 可放外部工具：使用者可把引擎模組或自備的 `ffmpeg.exe` 放進 `OpenConvert/modules/`。
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
modules/ffmpeg/ffmpeg.exe
modules/ffmpeg/ffprobe.exe
modules/libreoffice/program/soffice.exe
modules/THIRD-PARTY-NOTICES.txt        # 自動產生的授權聲明
```

### 開發者／發佈：維護引擎資產

引擎資產由兩個 workflow 產生並上傳到 `engines-v2` Release：

1. **`ffmpeg-min.yml`**：以 BtbN 的 builder 映像交叉編譯精簡 FFmpeg
   （`--disable-autodetect` + 6 個外部函式庫），建置系統以 commit 釘選確保可重現。
2. **`engines.yml`**：在 Windows runner 上執行 `scripts/build_libreoffice_module.py`，
   下載官方 MSI（SHA-256 驗證）→ 解壓 → 剝離 → 打包成精簡版 ZIP。

更新引擎版本的流程：

1. 更新 `openconvert/modules/manifest.json`（新的版本、網址與 SHA-256）。
2. 執行對應的 workflow；資產會上傳到引擎 Release（`--clobber`）。
3. 由於 manifest 內含 SHA-256，任何來源檔變動都會讓下載失敗，這是刻意的保護。

本地預覽清單與狀態：

```powershell
python scripts\fetch_tools.py --list
python scripts\fetch_tools.py --only ffmpeg          # 安裝到 modules/
python scripts\build_libreoffice_module.py --out assets   # 手動製作剝離版
```

**支援的平台**：目前 Windows x64 有 FFmpeg（精簡）與 LibreOffice（剝離），Linux x64 有 FFmpeg（精簡）。
其他平台（macOS、arm64）會回報「此平台未提供」，不會偷偷下載來路不明的檔案。

### 授權（下載模組時自動處理）

- FFmpeg 精簡版為 **GPL 建置**（`--enable-gpl --enable-libx264`）。
- LibreOffice 精簡版為 **MPL-2.0**（官方安裝樹剝離，移除清單見 `STRIP-MANIFEST.txt`）。
- 安裝模組後，`THIRD-PARTY-NOTICES.txt` 會列出授權、版本、網址與原始碼取得方式。
- OpenConvert 本身的程式碼仍為 MIT；引擎都是獨立程式，以子程序呼叫，不與本專案連結。
- 沒有安裝模組時，發佈檔**不含**任何 GPL／MPL 元件。

### 也可以不透過模組

使用者可以自行安裝系統版 FFmpeg／LibreOffice（**優先使用**），或手動放入：

```
modules/ffmpeg/ffmpeg.exe                 # 或 modules/ffmpeg.exe、modules/bin/...
modules/libreoffice/program/soffice.exe
```

搜尋順序是「設定頁指定 → 系統已安裝 → 模組／`tools/` → 常見安裝位置」，
設定頁會以「（模組）」標示由 OpenConvert 管理的引擎。

LibreOffice 的無介面轉換每次都使用獨立的 `-env:UserInstallation` 暫時設定檔，
因此模組版不會與使用者自己安裝的版本互相鎖定或污染設定。

## 版本號

版本號只在 `openconvert/__init__.py` 的 `__version__` 與 `pyproject.toml` 的 `version` 兩處，
發版前請同步更新，並在 `CHANGELOG.md` 補上該版本小節。

## 發佈流程（Windows）

1. 確認 `engines-v2` Release 存在且 manifest 的 SHA-256 與資產一致
   （必要時執行 `ffmpeg-min.yml` 與 `engines.yml`）。
2. 若要簽章：先依 [`docs/signing.md`](signing.md) 設定 GitHub Secrets。
3. 更新版本號與 `CHANGELOG.md`。
4. 跑完 `pytest`、`ruff check`、`ruff format --check`。
5. 建立標籤並推送：

   ```powershell
   git tag v0.10.1
   git push origin v0.10.1
   ```

6. `.github/workflows/release-windows.yml` 會自動：
   - 檢查標籤與程式版本一致
   - 建置 PyInstaller 產物並壓成 `OpenConvert-0.10.1-windows-x64.zip`
   - 簽章兩個執行檔（已設定憑證 secrets 時）
   - 建立 GitHub Release 並附上 ZIP

若只是要驗證流程，可用 `workflow_dispatch` 手動執行（只上傳 artifact、不建立 Release）。

## 簽章與 SmartScreen

Release 流程已內建**自動簽章**：設定好憑證 secrets 之後，打包 ZIP 前會自動簽署
`OpenConvert.exe` 與 `OpenConvertCLI.exe`（SHA256 + RFC3161 時間戳），
並在記錄中印出簽章狀態。未設定憑證時自動跳過，行為與未簽章相同。

- 支援方式：**Azure Artifact Signing**（原 Trusted Signing，建議）與可匯出的 **PFX** 憑證
- 完整說明（費用、申請、GitHub Secrets 設定、常見錯誤）見 [`docs/signing.md`](signing.md)
- 使用者端驗證：右鍵內容 → 數位簽章，或 `signtool verify /pa /all OpenConvert.exe`
- SHA-256 檢查碼：`Get-FileHash OpenConvert-0.10.1-windows-x64.zip -Algorithm SHA256`

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
| 影片轉換說找不到 FFmpeg | `modules install ffmpeg`、放入 `modules/`，或安裝系統版 FFmpeg（系統版會優先使用） |
| 模組下載失敗 | 檢查網路；確認 `engines-v2` Release 存在；manifest 的 SHA-256 與來源檔不符時會刻意中止 |
| 防毒誤報 | 送交廠商誤報回報；不要用 UPX 壓縮（spec 已關閉） |
