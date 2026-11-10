# Build PvZ2SHUTTLE Windows package
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$ErrorActionPreference = "Continue"

$py = "C:\Users\xiemu\.dsh\dsh-runtimes\dsh-next-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "== 1/3 validate content and assets =="
& $py tools\validate_all.py 2>&1 | ForEach-Object { Write-Host $_ }
$code = $LASTEXITCODE
if ($code -ne 0) { throw "validate_all failed ($code)" }

Write-Host "== 2/3 PyInstaller =="
$pyArgs = @("-m","PyInstaller","--noconfirm","--clean","--windowed","--name","PvZ2SHUTTLE",
            "--icon","assets\ui\app_icon.png",
            "--add-data","assets;assets","--add-data","content;content",
            "--hidden-import","pygame","--collect-submodules","game","main.py")
& $py @pyArgs 2>&1 | ForEach-Object { Write-Host $_ }
$code = $LASTEXITCODE
if ($code -ne 0) { throw "PyInstaller failed ($code)" }

Write-Host "== 3/3 assemble release =="
$out = Join-Path $root "dist\PvZ2SHUTTLE"
Copy-Item "README.md" $out -ErrorAction SilentlyContinue
Copy-Item "game\DESIGN.md" (Join-Path $out "DESIGN.md") -ErrorAction SilentlyContinue
$ver = Get-Content VERSION -ErrorAction SilentlyContinue
"PvZ 2 SHUTTLE Windows Remake $ver" | Out-File (Join-Path $out "BUILD.txt") -Encoding utf8
if (Test-Path (Join-Path $root "dist\PvZ2SHUTTLE-Windows.zip")) { Remove-Item (Join-Path $root "dist\PvZ2SHUTTLE-Windows.zip") -Force }
Compress-Archive -Path "$out\*" -DestinationPath (Join-Path $root "dist\PvZ2SHUTTLE-Windows.zip") -Force
Write-Host "done: dist\PvZ2SHUTTLE\PvZ2SHUTTLE.exe"
exit 0
