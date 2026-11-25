param([string]$Assets='', [switch]$Launcher)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$exe=Join-Path $repo 'build\native-desktop\Release\PvZ2SHUTTLE.exe'
if(-not (Test-Path -LiteralPath $exe)){throw 'Build the preview first: .\tools\build_native.ps1'}
if(-not $Assets){$Assets=Join-Path $repo '..\..\PvZ2SHUTTLE\assets'}
$Assets=(Resolve-Path -LiteralPath $Assets).Path
if($Launcher){& $exe --launcher $Assets}
else{& $exe --play (Join-Path $repo 'content') $Assets}
if($LASTEXITCODE -ne 0){throw "Native preview failed (exit $LASTEXITCODE)."}
