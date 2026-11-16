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

### 自足（Full）版本

Full 版本把 FFmpeg 與 LibreOffice 放進 `tools/`，使用者完全不需要安裝任何其他東西。
兩個產物只差在 `tools/`：

| | Lite | Full |
| --- | --- | --- |
| `tools/` | 無 | FFmpeg（GPL 版，含 libx264／libx265）+ LibreOffice |
| ZIP 大小 | 約 90 MB | 約 500 MB |
| 需要先安裝 | FFmpeg／LibreOffice | 什麼都不用 |

建置方式（在 PyInstaller 之後）：

```powershell
python scripts\fetch_tools.py --dest dist\OpenConvert\tools
```

`fetch_tools.py` 的行為：

1. 讀取 `packaging/tools.lock.json` 取得**固定版本**的網址與 SHA-256。
2. 下載到 `.cache/tools/`（已有且雜湊相符就重用，不會重抓）。
3. **驗證 SHA-256**；不符就中止，並提示用 `--update-lock` 重新產生。
4. 解壓縮：ZIP／tar.xz 直接解開，LibreOffice MSI 用 `msiexec /a`（管理員安裝模式，只解壓不註冊）。
5. 依下列結構放到 `tools/`，並寫入 `tools/THIRD-PARTY-NOTICES.txt`：

```
tools/ffmpeg/ffmpeg.exe
tools/ffmpeg/ffprobe.exe
tools/libreoffice/program/soffice.exe
tools/THIRD-PARTY-NOTICES.txt
```

其他常用選項：

```powershell
python scripts\fetch_tools.py --only ffmpeg        # 只放 FFmpeg
python scripts\fetch_tools.py --check              # 只驗證快取檔的雜湊
python scripts\fetch_tools.py --platform linux-x64 # 指定平台（預設為目前平台）
```

**支援的平台**：目前鎖定 Windows x64 的 FFmpeg 與 LibreOffice，以及 Linux x64 的 FFmpeg。
其他平台（macOS、arm64）執行時會回報「沒有固定的下載來源」，不會偷偷下載來路不明的檔案。

### 授權（散布 Full 版本前務必確認）

- FFmpeg 使用 BtbN 的 **GPL 建置**（`--enable-gpl --enable-libx264 --enable-libx265`），
  因此 Full 版本含有 GPL 元件。`THIRD-PARTY-NOTICES.txt` 會列出授權、版本、網址與原始碼取得方式。
- LibreOffice 為 **MPL-2.0**，同樣需要保留授權聲明。
- OpenConvert 本身的程式碼仍為 MIT；FFmpeg 與 LibreOffice 都是獨立程式，以子程序呼叫，不與本專案連結。
- Lite 版本**不含**任何 GPL／MPL 元件。

### 讓 Lite 版本自足

不想散布大型 Full 版本時，使用者（或你自己）也可以手動放入：

```
tools/ffmpeg.exe                 # 或 tools/ffmpeg/ffmpeg.exe、tools/bin/...
tools/libreoffice/program/soffice.exe
```

OpenConvert 的搜尋順序是「設定頁指定 → 內附 `tools/` → 系統 PATH → 常見安裝位置」，
所以放了就會優先使用，設定頁會顯示「（內附）」。

LibreOffice 的無介面轉換每次都使用獨立的 `-env:UserInstallation` 暫時設定檔，
因此內附的 LibreOffice 不會與使用者自己安裝的版本互相鎖定或污染設定。

## 版本號

版本號只在 `openconvert/__init__.py` 的 `__version__` 與 `pyproject.toml` 的 `version` 兩處，
發版前請同步更新，並在 `CHANGELOG.md` 補上該版本小節。

## 發佈流程（Windows）

1. 更新版本號與 `CHANGELOG.md`。
2. 跑完 `pytest`、`ruff check`、`ruff format --check`。
3. 建立標籤並推送：

   ```powershell
   git tag v0.3.0
   git push origin v0.3.0
   ```

4. `.github/workflows/release-windows.yml` 會自動：
   - 檢查標籤與程式版本一致
   - 建置 PyInstaller 產物並壓成 `OpenConvert-0.3.0-windows-x64.zip`（Lite）
   - 下載並內嵌引擎後壓成 `OpenConvert-0.3.0-windows-x64-full.zip`（Full）
   - 驗證 Full 產物確實含 `ffmpeg.exe`、`ffprobe.exe` 與 `soffice.exe`
   - 建立 GitHub Release 並附上兩個 ZIP

   Full 版本每次都要下載約 550 MB 的引擎；若只是要驗證流程，可用 `workflow_dispatch`
   手動執行（只上傳 artifact、不建立 Release）。

也可以從 Actions 頁面手動觸發（`workflow_dispatch`），此時只上傳 artifact、不建立 Release。

## 簽章與 SmartScreen

未簽章的執行檔在 Windows 上會出現 SmartScreen 警告。若要正式散布，建議：

- 使用程式碼簽章憑證（EV 憑證可立即取得信譽）；
- 或提供 SHA-256 檢查碼，讓使用者自行比對：

  ```powershell
  Get-FileHash OpenConvert-0.3.0-windows-x64-full.zip -Algorithm SHA256
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
