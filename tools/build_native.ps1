param(
    [switch]$AuditOnly,
    [string]$Configuration = 'Release',
    # A second, parallel build (another agent, a debug tree) must not share the CMake
    # binary dir: MSBuild keeps per-target .tlog files there and a concurrent CL.exe
    # fails with "MSB6003 ... CL.read.1.tlog ... being used by another process".
    # Pass -BuildDir to get an isolated tree; the default keeps the historical paths.
    [string]$BuildDir = '',
    # Force a full recompile. Needed when a stale object outlives a source edit: restoring a file
    # with Copy-Item keeps its old mtime and MSBuild then skips it, so a test binary can be older
    # than the code it is supposed to measure.
    [switch]$Clean
)
# Native tools write progress to stderr; keep that from terminating the script.
$ErrorActionPreference = 'Continue'
# The host shell can carry case-duplicated environment variables (NO_PROXY and
# no_proxy in the same block). MSBuild's CL.exe task copies the environment into a
# Hashtable keyed case-insensitively, so the duplicate aborts the build with
#   MSB6001: Item has already been added. Key: 'NO_PROXY' Key being added: 'no_proxy'
# Deleting one name is not enough: the block itself holds two entries, and which one
# .NET removes depends on its case-insensitive dictionary. Collapse every name that
# differs only by case first, then remove the proxy spellings outright.
$groups = @{}
foreach ($key in [System.Environment]::GetEnvironmentVariables().Keys) {
    $upper = $key.ToUpperInvariant()
    if (-not $groups.ContainsKey($upper)) { $groups[$upper] = @() }
    $groups[$upper] += $key
}
foreach ($upper in $groups.Keys) {
    $names = $groups[$upper]
    for ($i = 1; $i -lt $names.Count; $i++) {
        [System.Environment]::SetEnvironmentVariable($names[$i], $null)
    }
}
foreach ($name in 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'ALL_PROXY', 'FTP_PROXY') {
    [System.Environment]::SetEnvironmentVariable($name, $null)
}
# Reused MSBuild nodes keep the environment they were started with, so disable reuse.
$env:MSBUILDDISABLENODEREUSE = '1'
$repo = Split-Path -Parent $PSScriptRoot
$cmake = (Get-Command cmake -ErrorAction SilentlyContinue).Source
if (-not $cmake) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $install = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($install) { $cmake = Join-Path $install 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe' }
    }
}
if (-not $cmake -or -not (Test-Path -LiteralPath $cmake)) { throw 'CMake not found. Install CMake and Visual Studio 2022 C++ Build Tools.' }
$ctest = Join-Path (Split-Path -Parent $cmake) 'ctest.exe'
$folder = if ($AuditOnly) { 'native' } else { 'native-desktop' }
$desktop = if ($AuditOnly) { 'OFF' } else { 'ON' }
if ($BuildDir) {
    $build = if ([System.IO.Path]::IsPathRooted($BuildDir)) { $BuildDir } else { Join-Path $repo $BuildDir }
} else {
    $build = Join-Path $repo "build\$folder"
}
# PowerShell passes its raw environment block to children, duplicates and all, so the
# de-duplication above only fixes this process. CMake, and MSBuild under it, must be
# started with an environment built from the collapsed dictionary instead.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = ($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $psi.EnvironmentVariables.Clear()
    foreach ($key in [System.Environment]::GetEnvironmentVariables().Keys) {
        $value = [System.Environment]::GetEnvironmentVariable($key)
        if ($null -ne $value) { $psi.EnvironmentVariables[$key] = $value }
    }
    $process = [System.Diagnostics.Process]::Start($psi)
    # Read both streams synchronously: event handlers on a returned .NET object are
    # brittle inside a PowerShell function, and a build log of this size fits fine.
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($stdout) { Write-Host $stdout.TrimEnd() }
    if ($stderr) { Write-Host $stderr.TrimEnd() }
    # Write-Host, not Write-Output: anything on the pipeline would join the return
    # value and turn `-ne 0` into an array comparison that always looks falsy.
    return $process.ExitCode
}

if ((Invoke-Native $cmake @('-S', (Join-Path $repo 'native'), '-B', $build, '-G', 'Visual Studio 17 2022', '-A', 'x64', "-DPVZ_ENABLE_DESKTOP=$desktop")) -ne 0) {
    throw 'Native configure failed.'
}
$buildArgs = @('--build', $build, '--config', $Configuration, '--parallel', '4')
if ($Clean) { $buildArgs += '--clean-first' }
$buildArgs += @('--', '/nodeReuse:false')
if ((Invoke-Native $cmake $buildArgs) -ne 0) {
    throw 'Native build failed.'
}
if ((Invoke-Native $ctest @('--test-dir', $build, '-C', $Configuration, '--output-on-failure')) -ne 0) {
    throw 'Native tests failed.'
}
Write-Output "Built and tested: $(Join-Path $build "$Configuration\PvZ2SHUTTLE.exe")"
