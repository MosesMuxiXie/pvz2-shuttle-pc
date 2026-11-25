# S7 打包：干净构建 -> install 树 -> LICENSES.md -> zip -> sha256 -> 无源码树冒烟
#
# 用法（在仓库根目录）：
#   pwsh -File tools/package.ps1              # 构建 + 打包 + 解压冒烟
#   pwsh -File tools/package.ps1 -SkipBuild    # 复用 build/package 的产物，只重打包
#   pwsh -File tools/package.ps1 -IncludeAssets  # 额外把 assets/ 软链到暂存树（不进 zip）
#
# 产物：
#   dist/PvZ2SHUTTLE-<ver>/            暂存树（= zip 的内容）
#   dist/PvZ2SHUTTLE-<ver>-win64.zip   发布包
#   dist/PvZ2SHUTTLE-<ver>-sha256.txt  校验文件
#
# 为什么 assets 不进 zip：assets 是 4.4 GB 的模组素材（从用户自己的 OBB/资源包提取），
# 不是本仓库产出的东西。包里有 content/ + generated/ + exe 就能跑无渲染的路径，
# 渲染路径通过 PVZ_ASSET_ROOT 或 assets/ 目录指向用户自己的素材。

[CmdletBinding()]
param(
    [string]$Configuration = "Release",
    [string]$OutDir = "dist",
    [switch]$SkipBuild,
    [switch]$IncludeAssets
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # 仓库根
Set-Location $root

# cmake 常常不在 PATH 上（本机就是），按 build_native.ps1 的同一条搜索链找它：
# PATH -> vswhere 的 VS 安装目录 -> 明确报错。代理变量要清掉，否则 FetchContent 走代理。
foreach ($name in 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'ALL_PROXY', 'FTP_PROXY') {
    [System.Environment]::SetEnvironmentVariable($name, $null)
}
$env:MSBUILDDISABLENODEREUSE = '1'
$cmake = (Get-Command cmake -ErrorAction SilentlyContinue).Source
if (-not $cmake) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $install = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($install) { $cmake = Join-Path $install 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe' }
    }
}
if (-not $cmake -or -not (Test-Path -LiteralPath $cmake)) {
    throw 'CMake not found. Install CMake and Visual Studio 2022 C++ Build Tools.'
}
Write-Host "cmake=$cmake"

function Step([string]$name, [scriptblock]$body) {
    Write-Host ""
    Write-Host "=== $name" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "$name 失败（exit $LASTEXITCODE）"
    }
}

# 版本号的唯一来源就是 CMakeLists 里的 project(... VERSION x)
$cmakeText = Get-Content (Join-Path $root "native/CMakeLists.txt") -Raw
$m = [regex]::Match($cmakeText, 'project\(PvZ2SHUTTLE\s+VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)')
if (-not $m.Success) { throw "native/CMakeLists.txt 里找不到 project(... VERSION)" }
$version = $m.Groups[1].Value
$dataVersion = [regex]::Match($cmakeText, 'set\(PVZ_DATA_VERSION\s+"([^"]+)"')
$dataVersion = if ($dataVersion.Success) { $dataVersion.Groups[1].Value } else { "unknown" }
Write-Host "version=$version data=$dataVersion"

$buildDir = Join-Path $root "build/package"
$stage = Join-Path $root "$OutDir/PvZ2SHUTTLE-$version"
$zip = Join-Path $root "$OutDir/PvZ2SHUTTLE-$version-win64.zip"

# The artwork tree is not in the repository and `PVZ_ASSET_SOURCE` is a CACHE variable, so a build
# directory created before that tree was seen keeps the stale value (that is how the first package
# run ended up with no `assets/ui` and failed the `--menu` smoke on a missing Chinese font).
# `$root` is repo/pvz2-shuttle-pc, so the workspace root is two levels up.
$assetSource = Join-Path (Split-Path -Parent (Split-Path -Parent $root)) "PvZ2SHUTTLE/assets"
if (-not (Test-Path -LiteralPath (Join-Path $assetSource "ui/font_zh.ttc"))) {
    throw "找不到素材树 $assetSource（至少要有 ui/font_zh.ttc，否则包里的 --menu 跑不起来）"
}
Write-Host "assets=$assetSource"
Step "配置（$Configuration, desktop, 不建测试）" {
    & $cmake -S native -B $buildDir -G "Visual Studio 17 2022" -A x64 `
        "-DPVZ_ENABLE_DESKTOP=ON" "-DBUILD_TESTING=OFF" "-DPVZ_DATA_VERSION=$dataVersion" `
        "-DPVZ_ASSET_SOURCE=$assetSource"
}

if (-not $SkipBuild) {
    Step "构建" { & $cmake --build $buildDir --config $Configuration --clean-first }
} else {
    Write-Host "（-SkipBuild：复用 $buildDir）" -ForegroundColor Yellow
}

Step "安装到暂存树" {
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    & $cmake --install $buildDir --config $Configuration --prefix $stage
    # freetype 的 CMakeLists 无条件安装开发文件（ft2build.h / freetype.lib / *.cmake / pkgconfig），
    # 混进发行树只会让人以为这是个 SDK。安装完按名删掉，不跟上游 CMake 的选项较劲。
    foreach ($devDir in @("include", "lib")) {
        $path = Join-Path $stage $devDir
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
            Write-Host "  去掉开发文件 $devDir/"
        }
    }
}

Step "生成 LICENSES.md（从 NOTICE.md）" {
    $notice = Join-Path $root "NOTICE.md"
    if (-not (Test-Path $notice)) { throw "缺 NOTICE.md，拒绝出包" }
    $header = @(
        "# LICENSES — 本发行包的第三方组件与权利声明",
        "",
        "本文件由 ``tools/package.ps1`` 从仓库根的 ``NOTICE.md`` 逐字生成，不要手工编辑。",
        "重新生成：``pwsh -File tools/package.ps1``。",
        "",
        "构建：PvZ2SHUTTLE $version（数据包 $dataVersion）。",
        "源代码许可：MIT（见仓库 LICENSE）。随包素材的版权与再分发条件见下。",
        ""
    ) -join "`n"
    $bodyText = (Get-Content $notice -Raw) -replace "`r`n", "`n"
    # 只保留一张表头（NOTICE 的首行标题换成 LICENSES 的）
    $bodyText = $bodyText -replace '^# NOTICE — [^\n]*\n', ''
    $text = $header + $bodyText
    [IO.File]::WriteAllText((Join-Path $stage "LICENSES.md"), $text, (New-Object Text.UTF8Encoding $false))
    Write-Host ("LICENSES.md {0} B" -f (Get-Item (Join-Path $stage "LICENSES.md")).Length)
}

if ($IncludeAssets) {
    Step "挂 assets（不进 zip，仅暂存树）" {
        $assets = Join-Path (Split-Path -Parent (Split-Path -Parent $root)) "PvZ2SHUTTLE/assets"
        if (-not (Test-Path $assets)) { throw "找不到素材目录 $assets" }
        $link = Join-Path $stage "assets"
        if (-not (Test-Path $link)) {
            New-Item -ItemType Junction -Path $link -Target $assets | Out-Null
        }
        Write-Host "junction: $link -> $assets"
    }
}

Step "打 zip" {
    New-Item -ItemType Directory -Force -Path (Join-Path $root $OutDir) | Out-Null
    if (Test-Path $zip) { Remove-Item $zip -Force }
    # 只压暂存树里的真实文件（junction 会被 Compress-Archive 跟进去，所以 assets 用
    # -IncludeAssets 时改为排除）
    $items = Get-ChildItem $stage -Force | Where-Object {
        -not ($_.LinkType -eq "Junction")
    }
    Compress-Archive -Path $items.FullName -DestinationPath $zip -CompressionLevel Optimal
    $h = Get-FileHash $zip -Algorithm SHA256
    $line = "$($h.Hash.ToLower())  $(Split-Path -Leaf $zip)"
    $sumFile = Join-Path $root "$OutDir/PvZ2SHUTTLE-$version-sha256.txt"
    [IO.File]::WriteAllText($sumFile, $line + "`n", (New-Object Text.UTF8Encoding $false))
    Write-Host ("{0}  {1:N1} MB" -f $line, ((Get-Item $zip).Length / 1MB))
}

Step "无源码树冒烟（解压到临时目录再跑）" {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("pvz-pkg-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $exe = Join-Path $tmp "PvZ2SHUTTLE.exe"
        if (-not (Test-Path $exe)) { throw "包里没有 PvZ2SHUTTLE.exe" }
        $content = Join-Path $tmp "content"
        if (-not (Test-Path $content)) { throw "包里没有 content/" }

        # 四条命令覆盖四类路径：版本串、世界地图（读 world_gates.json）、一场真战斗（读 content 关卡 +
        # generated 表）、一屏 UI（读 assets/ui 的中文字体）。`--menu` 的输出是 `{"choice":...}`，
        # 不是 "menu"，第一版断言写错字面量，把一条本来通过的用例判成了失败。
        $menuShot = Join-Path $tmp "menu-smoke.png"
        $checks = @(
            @{ name = "--version"; args = @("--version"); expect = "PvZ2SHUTTLE " },
            @{ name = "--worldmap"; args = @("--worldmap", $content); expect = '"worlds"' },
            @{ name = "--run-level beach_23"; args = @("--run-level", $content, "beach_23", "--seconds", "60"); expect = "beach_23" },
            @{ name = "--menu --frames 2"; args = @("--menu", $content, "--frames", "2", "--snapshot", $menuShot); expect = '"choice"' }
        )
        foreach ($c in $checks) {
            Push-Location $tmp
            try {
                $out = & $exe @($c.args) 2>&1 | Out-String
                $code = $LASTEXITCODE
            } finally { Pop-Location }
            if ($code -ne 0) { throw ("{0} exit={1}`n{2}" -f $c.name, $code, $out) }
            if ($out -notmatch [regex]::Escape($c.expect)) {
                throw ("{0} 输出里没有 '{1}'`n{2}" -f $c.name, $c.expect, $out)
            }
            Write-Host ("  [ok] {0} exit=0" -f $c.name)
        }
        if (-not (Test-Path $menuShot) -or (Get-Item $menuShot).Length -lt 1000) {
            throw "主菜单截图没生成或过小：$menuShot"
        }
        Write-Host ("  [ok] 主菜单截图 {0:N0} B" -f (Get-Item $menuShot).Length)
        # 子目录相对路径：exe 自己找不到 generated/ 或 content/ 时报错，这里当断言
        $gen = Join-Path $tmp "generated"
        $n = (Get-ChildItem $gen -Filter *.json -File).Count
        if ($n -lt 30) { throw "generated/ 只有 $n 个 json，包不完整" }
        Write-Host "  [ok] generated/ $n 个 json"
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "打包完成：$zip" -ForegroundColor Green
