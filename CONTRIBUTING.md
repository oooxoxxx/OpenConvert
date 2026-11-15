# 貢獻指南

感謝你想讓 OpenConvert 更好。這個專案以「真的能用」為標準：功能要有測試、錯誤要被處理、
介面不能只是擺設。請在送 PR 前確認下面的檢查都通過。

## 開發環境

```powershell
git clone <this-repository>
cd OpenConvert
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux：source .venv/bin/activate
pip install -e ".[dev]"
```

- Python 3.10 以上（開發與 CI 使用 3.13）
- 影片／音訊相關測試需要 `ffmpeg` 與 `ffprobe` 在 `PATH` 上
- Linux 執行 GUI 需要 `libxcb-cursor0` 等 Qt 相依套件；CI 使用 `xvfb-run`

## 送出前必跑

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
```

- 沒有 `ffmpeg` 時，相關測試會自動 skip，不算失敗；但 PR 會跑在有 FFmpeg 的 CI 上。
- 修 bug 請附上能重現問題的測試；新增功能請附上成功與失敗路徑的測試。
- 不接受「先跳過測試」或 `pytest.mark.skip` 掩蓋問題的 PR。

## 程式分層規則

| 目錄 | 可以依賴 | 不可以依賴 |
| --- | --- | --- |
| `openconvert/core/` | 標準函式庫、platformdirs | Qt、GUI、converters |
| `openconvert/converters/` | core、Pillow、pypdf、pypdfium2、subprocess | Qt、GUI |
| `openconvert/runner.py` | core、converters、PySide6 | GUI 頁面 |
| `openconvert/gui/` | 全部 | — |

也就是說：**Qt 只能出現在 `runner.py` 與 `gui/`**。這樣命令列、測試與未來的服務化才能重複使用引擎。

其他慣例：

- 使用者看得到的文字一律用繁體中文；程式註解與 docstring 也用繁體中文。
- 錯誤訊息分兩層：`user_message`（給使用者看）與 `detail`（給開發者看）。
- 不要引入 GPL／AGPL 的執行期依賴；新增依賴前先確認授權並更新 README 的授權表。
- 不要內嵌 FFmpeg 或任何 GPL 二進位檔。

## 新增一種轉換格式

1. 在 `openconvert/core/targets.py` 宣告 `TargetSpec`（代號、名稱、類別、輸出副檔名、可接受的來源類型）。
   - 逐檔轉換：只填 `kinds`。
   - 合併型（多檔案合成一個輸出）：加上 `group_kinds` 與 `group_min`。
2. 在對應的轉換器（`converters/media.py`、`image.py`、`pdf.py`、`ebook.py`）加入實作；
   需要新轉換器時在 `converters/__init__.py` 註冊。
3. 在 `tests/` 補上：成功轉換、輸出副檔名正確、錯誤輸入有清楚訊息。
4. 更新 `docs/formats.md` 與 `CHANGELOG.md`。

`tests/helpers.py` 會檢查「輸出副檔名必須等於 `TargetSpec.extension`」，這條不變式請不要繞過。

## 輸出安全

任何輸出都必須經過 `core/paths.py` 的 `resolve_output()`／`resolve_output_dir()`：

- 不得覆蓋來源檔案
- 預設不得覆蓋既有檔案（改用 `名稱 (1).ext`）
- 失敗或取消時要清掉自己產生的半成品（用 `ctx.track()` 登記）

## Commit 與 PR

- Commit 訊息用祈使句、聚焦單一變更，例如：
  - `feat: 新增 PDF 轉 JPEG 的 DPI 選項`
  - `fix: 修正 BMP 目標仍顯示影像品質選項`
  - `docs: 補上 FFmpeg 偵測順序`
- 一個 PR 只做一件事；格式化與重構請與行為變更分開。
- PR 描述請寫：問題是什麼、怎麼改、怎麼驗證（指令與結果）。
- 不要提交：`.venv/`、`build/`、`dist/`、`*.spec` 產物、暫存截圖、任何凭證或 token。

## 回報問題

請附上：

- 作業系統與版本、OpenConvert 版本（「關於」頁可看到）
- FFmpeg 是否可用（「設定」頁會顯示版本）
- 重現步驟、預期結果、實際結果
- 相關錯誤訊息或「轉換紀錄」內容（請先移除個人路徑）

## 授權

送出 PR 即表示你同意以本專案的 MIT 授權釋出你的貢獻。
