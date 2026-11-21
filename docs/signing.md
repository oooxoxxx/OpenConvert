# Windows 程式碼簽章

未簽章的執行檔從網路下載後執行，Windows 會用 **SmartScreen** 顯示
「Windows 已保護您的電腦」（ Unknown publisher / 不安全的軟體）。
要消除這個警告，唯一有效的方法是用**程式碼簽章憑證**簽署 `OpenConvert.exe` 與
`OpenConvertCLI.exe`。

這份文件說明：

1. 簽章能做什麼、不能做什麼（誠實版）
2. 憑證選項與費用
3. OpenConvert 的 Release 流程如何自動簽章（已內建）
4. 你需要設定哪些 GitHub Secrets
5. 如何驗證簽章

---

## 1. 簽章能做什麼、不能做什麼

| | 未簽章 | 有簽章（OV／Trusted Signing） | 有簽章（EV） |
| --- | --- | --- | --- |
| 「Unknown publisher」警告 | 會出現 | 不會出現（顯示發行者名稱） | 不會出現 |
| SmartScreen 提示 | 幾乎一定出現 | 剛開始仍可能出現，隨下載次數累積信譽後消失 | 幾乎不會出現 |
| 憑證存放 | — | 雲端（Trusted Signing）或硬體 token | 硬體 token（強制） |

**誠實的結論**：

- 沒有憑證就沒有辦法消除警告——**自簽憑證沒有用**（使用者電腦根本不信任它）。
- 一般（OV）憑證簽章後，SmartScreen 仍可能提示一段時間，直到累積足夠下載信譽；
  EV 憑證與 Microsoft 的 Artifact Signing（原 Trusted Signing）信譽累積較快。
- 簽章必須**加上時間戳**，否則憑證過期後簽章就失效（我們的流程已內建）。

## 2. 憑證選項

### 選項 A（建議）：Azure Artifact Signing（原 Trusted Signing）

微軟官方的雲端簽章服務，**不需要硬體 token、不用保管金鑰**，最適合 GitHub Actions：

- 費用：Basic 層 **每月約 US$9.99** + 每次簽章少量計費
- 需要 Azure 訂閱與**身份驗證**（個人可用證件；公司用統一編號／商業登記）
- 簽章時由微軟的憑證簽署，SmartScreen 信譽較好

設定步驟（一次）：

1. 建立 Azure 訂閱（若沒有）。
2. Azure Portal → 建立 **Artifact Signing**（原 Trusted Signing）帳戶
   （搜尋 "Artifact Signing" 或 "Trusted Signing"；選離你近的區域，例如 East Asia）。
3. 在帳戶內申請**身份驗證**（Identity Validation）——個人身分或組織，需數個工作天審核。
4. 審核通過後建立**憑證設定檔**（Certificate Profile），例如名稱 `OpenConvert`。
5. Azure Entra ID → 建立**應用程式註冊**（App Registration），
   並給它在 Artifact Signing 帳戶的 **Code Signing Practitioner** 角色。
6. 建立用戶端密碼（Client Secret），記下以下五個值：

| GitHub Secret 名稱 | 內容 |
| --- | --- |
| `AZURE_TENANT_ID` | Entra 租用戶（目錄）ID |
| `AZURE_CLIENT_ID` | 應用程式（用戶端）ID |
| `AZURE_CLIENT_SECRET` | 用戶端密碼的「值」（不是密碼 ID） |
| `AZURE_SIGNING_ENDPOINT` | 簽章端點，例如 `eastasia.codesigning.azure.net/`（區域依你的帳戶） |
| `AZURE_SIGNING_ACCOUNT` | Artifact Signing 帳戶名稱 |
| `AZURE_SIGNING_CERT_PROFILE` | 憑證設定檔名稱 |

到 GitHub 儲存庫 → Settings → Secrets and variables → Actions → New repository secret，
逐一新增。設定完成後，之後的 Release（推 `v*` 標籤）就會自動簽章。

### 選項 B：向 CA 購買 OV／EV 憑證

- 供應商：Certum（Open Source 開發者方案較便宜）、SSL.com、Sectigo、DigiCert…
- 費用：OV 約 US$200–400／年、EV 約 US$300–700／年
- 2023 年起 OV／EV 憑證的私鑰**強制放在硬體 token 或雲端簽章服務**，
  在 CI 自動簽章需要選「雲端簽章」供應方案（例如 SSL.com eSigner、Certum SimplySign）。
- 若你的憑證可匯出成 **PFX**，OpenConvert 的 Release 流程也支援：
  設定 `CODE_SIGNING_PFX`（PFX 檔的 base64 內容）與 `CODE_SIGNING_PFX_PASSWORD`。

### 選項 C：自簽憑證（零費用，有明確限制）

**誠實說明**：自簽憑證**不會**消除一般使用者下載後的 SmartScreen 警告——
Windows 不信任自簽憑證鏈。我們實測：簽章成功後 `Get-AuthenticodeSignature`
回報「A certificate chain processed, but terminated in a root certificate which
is not trusted by the trust provider」（根憑證不受信任）。

它**能**做到的：

- 檔案完整性（簽章後被竄改即失效）
- 顯示簽發者資訊（OpenConvert 的自簽憑證）
- 在**安裝過我們憑證的機器**上，不出現未知的簽發者（適合受控環境、親友分發）

產生憑證（本機執行一次，Windows 內建 PowerShell 即可）：

```powershell
cd OpenConvert
powershell -ExecutionPolicy Bypass -File scripts\create_signing_cert.ps1 -Subject "CN=你的名字" -OutDir .\secrets
```

腳本會產生：

| 檔案 | 用途 |
| --- | --- |
| `openconvert-codesign.pfx` | 私密金鑰（**不要公開**） |
| `openconvert-codesign.cer` | 公開憑證（交給使用者安裝） |
| `CODE_SIGNING_PFX.base64.txt` | GitHub Secret `CODE_SIGNING_PFX` 的內容 |

GitHub Secrets：`CODE_SIGNING_PFX` = base64 檔案的內容、`CODE_SIGNING_PFX_PASSWORD` =
你設定的密碼。設定後 Release 會自動用**同一張憑證**簽署每個版本，
並把公開憑證 `openconvert-codesign.cer` 一起放進 ZIP。

讓警告在使用者機器上消失（每台機器都要做一次）：

1. 從 ZIP 取出 `openconvert-codesign.cer`。
2. 以**系統管理員** PowerShell 執行：

   ```powershell
   certutil -addstore Root openconvert-codesign.cer
   certutil -addstore TrustedPublisher openconvert-codesign.cer
   ```

3. 之後執行 OpenConvert 不會出現未知的簽發者（SmartScreen 首次仍可能提示）。

## 3. Release 流程如何簽章（已內建）

`.github/workflows/release-windows.yml` 在 PyInstaller 之後、打包 ZIP 之前會：

1. 若設定了 **Azure Artifact Signing** 的 secrets → 用
   `Azure/artifact-signing-action` 簽署兩個執行檔（SHA256 + RFC3161 時間戳）。
2. 否則若設定了 **PFX** secrets → 用 signtool 簽署（同樣加時間戳）。
3. 兩者都沒設定 → **跳過簽章**，產物與之前相同（不會讓 Release 失敗）。
4. 每次都會印出簽章狀態（`Get-AuthenticodeSignature`）供檢查。

## 4. 驗證簽章

下載 Release 後：

- 檔案總管 → 右鍵 `OpenConvert.exe` → 內容 → **數位簽章**索引標籤 →
  應顯示簽發者與「這個數位簽章是有效的」。
- 命令列：

  ```powershell
  Get-AuthenticodeSignature .\OpenConvert.exe | Format-List
  # 或
  signtool verify /pa /all OpenConvert.exe
  ```

## 5. 常見問題

| 症狀 | 說明 |
| --- | --- |
| 簽章後 SmartScreen 還是警告 | OV 憑證需要累積信譽；多簽幾個版本、累積下載量後會消失。EV／Artifact Signing 較快 |
| `No certificates were found` | Artifact Signing 的身份驗證未完成，或 App Registration 沒有 Signer 角色 |
| 簽章過期後被警告 | 沒有加時間戳。我們的流程一律加上 RFC3161 時間戳 |
| 要簽 ZIP 檔本身 | Authenticode 只支援 EXE／MSI／CAB；ZIP 內的 EXE 已簽章即足夠 |
