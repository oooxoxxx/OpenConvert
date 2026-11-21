# 產生 OpenConvert 的自簽程式碼簽章憑證並匯出。
#
# 用途：本機執行一次，把輸出的 PFX base64 設成 GitHub Secret（CODE_SIGNING_PFX、
# CODE_SIGNING_PFX_PASSWORD），Release 流程就會用同一張憑證簽署每個版本的執行檔。
# 公開憑證（.cer）交給使用者安裝到「受信任的根憑證授權單位」與「信任的發行者」，
# 該機器上執行 OpenConvert 就不會出現未知的簽發者。
#
# 誠實提醒：自簽憑證不會消除 SmartScreen 警告（Windows 不信任自簽憑證）。
# 要對一般使用者消除警告，需要向 CA 購買 OV／EV 憑證，或使用 Azure Artifact Signing。
#
# 用法：
#   powershell -File scripts\create_signing_cert.ps1 -OutDir .\secrets
#   powershell -File scripts\create_signing_cert.ps1 -Subject "CN=OpenConvert" -Password "你的密碼"

param(
    # 憑證主體（建議填你自己的名字或組織）
    [string]$Subject = "CN=OpenConvert, O=OpenConvert Project",
    # 輸出資料夾（PFX／CER 會放在這裡）
    [string]$OutDir = ".",
    # PFX 密碼；不填時自動產生隨機密碼
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"

if (-not $Subject.StartsWith("CN=")) {
    $Subject = "CN=$Subject"
}

if (-not $Password) {
    # 產生 24 字元隨機密碼
    $bytes = New-Object byte[] 18
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $Password = [Convert]::ToBase64String($bytes)
}

$out = Resolve-Path $OutDir -ErrorAction SilentlyContinue
if (-not $out) {
    $out = New-Item -ItemType Directory -Path $OutDir
}

Write-Host "建立自簽程式碼簽章憑證：$Subject"
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyUsage DigitalSignature `
    -KeyUsageProperty Sign `
    -KeyExportPolicy Exportable `
    -KeySpec Signature `
    -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddYears(3) `
    -CertStoreLocation "Cert:\CurrentUser\My"

$secure = ConvertTo-SecureString -String $Password -Force -AsPlainText

$pfx_path = Join-Path $out "openconvert-codesign.pfx"
Export-PfxCertificate -Cert $cert -FilePath $pfx_path -Password $secure | Out-Null

$cer_path = Join-Path $out "openconvert-codesign.cer"
Export-Certificate -Cert $cert -FilePath $cer_path | Out-Null

$pfx_base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($pfx_path))
$secret_path = Join-Path $out "CODE_SIGNING_PFX.base64.txt"
[IO.File]::WriteAllText($secret_path, $pfx_base64)

$thumb = $cert.Thumbprint
Write-Host ""
Write-Host "完成。產生以下檔案："
Write-Host "  $pfx_path    （私密金鑰，不要公開）"
Write-Host "  $cer_path    （公開憑證，交給使用者安裝）"
Write-Host "  $secret_path （PFX 的 base64，GitHub Secret 用）"
Write-Host ""
Write-Host "GitHub Secrets 設定（Settings → Secrets and variables → Actions）："
Write-Host "  CODE_SIGNING_PFX          = $secret_path 的內容（base64）"
Write-Host "  CODE_SIGNING_PFX_PASSWORD = 你設定的密碼"
if (-not $args[0]) {
    Write-Host "  （PFX 密碼：$Password）"
}
Write-Host ""
Write-Host "憑證指紋（Thumbprint）：$thumb"
Write-Host ""
Write-Host "提醒：自簽憑證不會消除 SmartScreen 警告。"
Write-Host "使用者需要安裝 $cer_path 到「受信任的根憑證授權單位」與「信任的發行者」，"
Write-Host "該機器上才會不出現未知的簽發者。一般使用者仍會看到 SmartScreen。"
Write-Host ""
Write-Host "測試簽章（本機）："
Write-Host '  $cert = Get-ChildItem Cert:\CurrentUser\My\' + $thumb
Write-Host '  Set-AuthenticodeSignature .\某檔案.exe $cert'
