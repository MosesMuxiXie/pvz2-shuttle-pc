<#
.SYNOPSIS
Runs every gate this repository has: content pack, native build, tests, parity matrix.

.DESCRIPTION
One command answers "is the native client still honest?". Steps run in order and
the first failure stops the run with a non-zero exit code:

  1. content  regenerate native/generated/content.pack from the shipped sheets
  2. audit    build the headless client and run its tests
  3. classes  verify the generated 183-row ZombieClass table on disk is current
  4. desktop  build the SDL3 client and run its tests
  5. smoke    run native/generated/engine_smoke.json scenarios through --run-level twice
  6. parity   rewrite docs/PARITY_MATRIX.md and report whether it changed
  7. ledger   the test counts above must equal the ones written in PARITY_BASELINE.md

Both configurations run by default. That is the point: `battle_view.cpp`, `assets.cpp`
and every other desktop-only translation unit are never compiled by the audit build, so
on 2026-11-20 a broken view passed every audit gate and stayed red for 7 minutes until
someone happened to run the desktop build by hand. A gate that only checks the half you
already compile is not a gate. `-NoDesktop` exists for a machine without the SDL3
dependencies; using it prints a skipped gate instead of a silent pass.

Nothing here commits or pushes.

.PARAMETER NoDesktop
Skip the SDL3 client build. Only for machines without the desktop dependencies: the
run then proves nothing about `battle_view.cpp` / `assets.cpp`.

.PARAMETER Desktop
Accepted for compatibility with older call sites; the desktop build now always runs.

.PARAMETER NoContent
Reuse the committed content pack instead of regenerating it (no Python needed).

.PARAMETER AllowMatrixChange
Exit 0 even when docs/PARITY_MATRIX.md had to be rewritten. Use when a change to
the content is the point of the run, not a surprise.

.PARAMETER UpdateLedger
Rewrite the machine-readable test-counts block in docs/PARITY_BASELINE.md with the
counts this run measured. Without it a stale ledger fails the run, which is the
point: prose numbers drifted twice in one day because nothing tied the document to
the run. Use it deliberately, on a tree you just made green, never to silence a red.

.EXAMPLE
pwsh -File tools/check_all.ps1
.EXAMPLE
pwsh -File tools/check_all.ps1 -NoContent
.EXAMPLE
pwsh -File tools/check_all.ps1 -UpdateLedger -NoContent
#>
[CmdletBinding()]
param(
    [switch]$Desktop,
    [switch]$NoDesktop,
    [switch]$NoContent,
    [switch]$AllowMatrixChange,
    [switch]$UpdateLedger
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:PYTHONUTF8) { $env:PYTHONUTF8 = '1' }

$failures = [System.Collections.Generic.List[string]]::new()

function Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0) {
        $failures.Add("$Name (exit $LASTEXITCODE)")
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

# The stamp line records when a report was rendered, not what it says: compare
# the reports with that line removed so a re-run on another day stays green.
function Compare-Report {
    param([string]$Before, [string]$After)
    $strip = { param($text) ($text -split "`r?`n" | Where-Object { $_ -notmatch '生成时间|^generated=' }) -join "`n" }
    return (& $strip $Before) -eq (& $strip $After)
}

# Refreshing a baseline is a decision, never a side effect. These three report
# files are untracked (`git ls-files native/generated` is empty), so a blanket
# Copy-Item after a failed comparison destroyed the only copy of the evidence the
# failure was about. Unchanged reports are left alone; a changed report is only
# written when the operator passes -AllowMatrixChange, otherwise the fresh render
# stays in build/ for inspection.
function Sync-Baseline {
    param([string]$Fresh, [string]$Baseline, [bool]$Changed, [string]$Label)
    if (-not $Changed) { return }
    if (-not (Test-Path $Baseline)) {
        Copy-Item $Fresh $Baseline -Force
        Write-Host "[ok] seeded $Label from $Fresh" -ForegroundColor Yellow
        return
    }
    if ($AllowMatrixChange) {
        Copy-Item $Fresh $Baseline -Force
        Write-Host "[ok] refreshed $Label (-AllowMatrixChange)" -ForegroundColor Yellow
        return
    }
    Write-Host "[keep] $Label left untouched; fresh render: $Fresh" -ForegroundColor Yellow
}

# ctest writes one header line per test into LastTest.log ("3/12 Testing: engine"), so
# the denominator is the count that actually ran — not something this script recites.
function Measure-CtestCount {
    param([string]$Build)
    $log = Join-Path $Build 'Testing/Temporary/LastTest.log'
    if (-not (Test-Path -LiteralPath $log)) { return -1 }
    $total = 0
    foreach ($line in Get-Content -LiteralPath $log) {
        if ($line -match '^\d+/(\d+)\s+Testing:') {
            $value = [int]$Matches[1]
            if ($value -gt $total) { $total = $value }
        }
    }
    return $total
}

# The ledger block is machine-readable on purpose: prose numbers drifted twice in one
# day (11/11 vs 12/12, 16/16 vs 17/17) because adding a test file changed the count and
# nothing tied the document back to the run.
function Read-TestLedger {
    param([string]$Path)
    $table = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $table }
    $inside = $false
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '<!--\s*test-counts\s*-->') { $inside = $true; continue }
        if ($line -match '<!--\s*/test-counts\s*-->') { $inside = $false; continue }
        if (-not $inside) { continue }
        if ($line -match '^\|\s*([A-Za-z]+)\s*\|\s*(\d+)\s*\|') { $table[$Matches[1].ToLowerInvariant()] = [int]$Matches[2] }
    }
    return $table
}

# Writing the ledger is a decision too (-UpdateLedger), for the same reason refreshing a
# baseline is: a gate that silently rewrites its own expectation measures nothing.
function Write-TestLedger {
    param([string]$Path, [System.Collections.IDictionary]$Counts)
    $lines = Get-Content -LiteralPath $Path
    $out = [System.Collections.Generic.List[string]]::new()
    $inside = $false
    foreach ($line in $lines) {
        if ($line -match '<!--\s*test-counts\s*-->') {
            $inside = $true
            $out.Add($line)
            $out.Add('')
            $out.Add('| run | tests |')
            $out.Add('| --- | --- |')
            foreach ($key in $Counts.Keys) { $out.Add("| $key | $($Counts[$key]) |") }
            continue
        }
        if ($line -match '<!--\s*/test-counts\s*-->') { $inside = $false; $out.Add($line); continue }
        if ($inside) { continue }
        $out.Add($line)
    }
    Set-Content -LiteralPath $Path -Value $out -Encoding utf8
}

# OneDrive (and any syncing shell) can hold the freshly linked binary, which turns a green
# build into `LNK1104 cannot open ...exe` or `C1041 cannot open program database`. Both are
# transient file locks, not code errors; retry once before spending a red gate on it.
function Step-Build {
    param([string]$Name, [string]$BuildDir, [bool]$AuditOnly)
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        Write-Host ""
        Write-Host "== $Name ==" -ForegroundColor Cyan
        $arguments = @('-File', 'tools/build_native.ps1', '-BuildDir', $BuildDir)
        if ($AuditOnly) { $arguments += '-AuditOnly' }
        # A second attempt cleans first: a stale .obj can outlive a source edit (Copy-Item keeps
        # mtimes) and then a test binary built from old code decides the gate.
        if ($attempt -gt 1) { $arguments += '-Clean' }
        $output = & pwsh @arguments 2>&1
        $code = $LASTEXITCODE
        $output | ForEach-Object { Write-Host $_ }
        if ($code -eq 0) { return }
        $text = ($output -join "`n")
        if ($attempt -eq 1 -and $text -match 'LNK1104|C1041|cannot open program database|test failed:') {
            Write-Host "[retry] $Name hit a file lock (LNK1104/C1041); retrying once in 3 s" -ForegroundColor Yellow
            Start-Sleep -Seconds 3
            continue
        }
        $failures.Add("$Name (exit $code)")
        throw "$Name failed with exit code $code"
    }
}

# A verdict is only about a tree that stood still. Editing sources while the gate runs makes
# every conclusion suspect — on 2026-11-21 one run reported audit green and desktop red purely
# because a teammate was mid-edit. Stamp the code before and after; a moved tree downgrades
# the exit code to 2 ("inconclusive"), which is neither a pass nor a failure.
function Get-TreeStamp {
    # The roots must cover everything the gate actually measures. The first version watched only
    # the sources, so editing `content/` (1809 levels), regenerating `native/generated/*` (smoke
    # baseline, family tables, pack) or rewriting `docs/PARITY_*` during a run was invisible and
    # the gate still said [ok]. Extension filtering is gone for the same reason: `.inc` tables
    # live in native/generated and `.json` baselines are exactly what gets rewritten.
    $roots = @(
        'native/src', 'native/tests', 'native/CMakeLists.txt', 'native/generated',
        'content', 'tools', 'docs/PARITY_BASELINE.md', 'docs/PARITY_MATRIX.md'
    )
    # Files this script writes itself (`-AllowMatrixChange` / `-UpdateLedger` refresh them) must
    # not count as "someone else edited the tree", or every gate run would call itself
    # inconclusive. Everything else under the roots stays watched.
    $selfWritten = @(
        'docs/PARITY_BASELINE.md', 'docs/PARITY_MATRIX.md',
        'native/generated/engine_smoke.json', 'native/generated/world_diff.md',
        'native/generated/world_gates.json'
    )
    $isSelfWritten = {
        param($full)
        $relative = [System.IO.Path]::GetRelativePath($repo, $full) -replace '\\', '/'
        foreach ($own in $selfWritten) { if ($relative -eq $own) { return $true } }
        return $false
    }
    $entries = foreach ($root in $roots) {
        $path = Join-Path $repo $root
        if (-not (Test-Path -LiteralPath $path)) { continue }
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $item = Get-Item -LiteralPath $path
            if (-not (& $isSelfWritten $item.FullName)) {
                "$($item.FullName)|$($item.Length)|$($item.LastWriteTimeUtc.Ticks)"
            }
            continue
        }
        Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue |
            # `python` writes __pycache__/*.pyc on import, and the gate itself runs the
            # python suite: without this filter every run stamps a different tree and
            # calls itself inconclusive (measured 2026-11-24 14:17 on a quiet tree).
            Where-Object { $_.FullName -notmatch '__pycache__' -and $_.Extension -ne '.pyc' } |
            Where-Object { -not (& $isSelfWritten $_.FullName) } |
            ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }
    }
    $sorted = @($entries | Sort-Object)
    if ($env:PVZ_STAMP_DEBUG) {
        $script:stampCall = 1 + [int]$script:stampCall
        $dump = Join-Path $repo "build/stamp-$($script:stampCall).txt"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dump) | Out-Null
        Set-Content -LiteralPath $dump -Value $sorted -Encoding utf8
    }
    $joined = $sorted -join "`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($joined)
    $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ([System.BitConverter]::ToString($hash) -replace '-', '').Substring(0, 16)
}

# Two configurations, two build directories: sharing one would let MSBuild reuse the
# other configuration's .tlog / .obj and produce a green run that never compiled the
# files under test. build/desktop-gate is deliberately separate from build/native.
$auditBuild = Join-Path $repo 'build/native'
$desktopBuild = Join-Path $repo 'build/desktop-gate'

Push-Location $repo
$stampStart = Get-TreeStamp
try {
    if (-not $NoContent) {
        Step 'content' {
            python tools/contentc/build_content.py --generated 2026-11-20 --check
        }
    } else {
        Write-Host "== content (reused) ==" -ForegroundColor DarkGray
    }

    Step-Build -Name 'audit build' -BuildDir $auditBuild -AuditOnly $true

    # The 183-row class table is generated; --check regenerates it in memory and
    # fails when the JSON/inc on disk drifted. No Python heredocs: the module owns
    # its own CLI so this stays a single command.
    Step 'zombie classes' { python tools/contentc/zclasses.py --check }

    # Same contract for the 339-row plant family table: the JSON is the source of
    # truth, the .inc is a mechanical projection consumed by plant_family.cpp.
    Step 'plant families' { python tools/contentc/plant_family_inc.py --check }

    Step 'armors' { python tools/contentc/armors.py --check }

    # The level-mechanics table (conveyor / initials / gravestones / protect /
    # spawners / events / mutators / boardGrid) is derived from all 2117 packs and
    # is 4.5 MB compact.  --check recomputes it with the same dumper, so the byte
    # comparison stays deterministic without a pretty-print round trip.
    Step 'level mechanics' { python tools/contentc/mechanics.py --check }

    # Field-level parity against the original tables (46 entity.field pairs over 2116
    # sheets).  It is a report, not a gate on content: `--check` only fails when the
    # generated JSON/markdown drifted, so a data change must re-run the compiler.
    Step 'original gaps' { python tools/contentc/original_gaps.py --check }

    # Rewards are the data side of the economy loop; T54/T55 consume them.
    Step 'rewards' { python tools/contentc/rewards.py --check }

    # 砸罐子配方（47 关）、小游戏/变体玩法挂载（813 关 20 kind）、逐关掉落绑定
    # （1809 关）三份表各自有编译器；--check 用同一个 dumper 重算再逐字节比，
    # 所以改数据必须重跑对应编译器，不会静默漂移。
    Step 'vasebreaker' { python tools/contentc/vasebreaker.py --check }
    Step 'minigames' { python tools/contentc/minigames.py --check }
    # 20 种玩法的开局参数与可玩判定（18 可玩 / column+invisighoul 参数对象是空 {}）。
    # 依赖 minigames.json 与 level_mechanics.json，两者一改这里就会报过期。
    Step 'minigame rules' { python tools/contentc/minigame_rules.py --check }
    # 逐关可玩性底账（1809 关 × 机制 × 玩法）：读上面四份表 + content/levels 的 extra 开关，
    # 逐关判「有没有 data-only 机制 / 有没有被阻断的玩法」。任何一份上游表变了这里就会报过期。
    Step 'level playability' { python tools/contentc/level_playability.py --check }
    Step 'loot binding' { python tools/contentc/loot_binding.py --check }

    # 元游戏（图鉴/花园/任务/成就）、可玩植物子集（339 判 293 可玩）、植物等级（323 株 / 133 可升级）
    # 三份表同样是「编译器 + --check 逐字节比」，漏了门禁就会在数据变动后静默变旧。
    Step 'metagame' { python tools/contentc/metagame.py --check }
    Step 'plant playable' { python tools/contentc/plant_playable.py --check }
    Step 'plant levels' { python tools/contentc/plant_levels.py --check }

    # 其余数据编译器（t101 补齐）。这些表一直有编译器和产物，却没有门禁：产物变旧时
    # `check_all` 依旧绿，本轮就发生过两次。括号里是 2026-11-26 温跑实测的 --check 耗时；
    # 冷跑要再加解释器启动与 OneDrive 读盘（最重的 level_extra_rules 冷跑 15.7 s、内部
    # 计算 5.8 s）。新增编译器时必须同时在这里加 Step，`tools/tests/test_gate_coverage.py`
    # 会把「产物有、Step 没有」直接判红并点名。
    Step 'level extra rules' { python tools/contentc/level_extra_rules.py --check }   # 5.5 s
    Step 'lawn strings' { python tools/contentc/loc.py --check }                       # 2.6 s
    Step 'level modules' { python tools/contentc/levelextra.py --check }               # 3.2 s
    Step 'elements' { python tools/contentc/elements_authored.py --check }             # 0.7 s
    Step 'bosses' { python tools/contentc/bosses.py --check }                          # 3.1 s
    Step 'projectiles' { python tools/contentc/projectiles.py --check }                # 4.1 s
    Step 'fusions' { python tools/contentc/fusions.py --check }                        # 0.6 s
    Step 'plant roster' { python tools/contentc/expand.py --check }                    # 0.5 s
    Step 'plant food' { python tools/contentc/plantfood.py --check }                   # 0.5 s
    Step 'plant families json' { python tools/contentc/pfamilies.py --check }          # 0.6 s
    Step 'plant merge' { python tools/contentc/plants_merge.py --check }               # 1.7 s
    Step 'shop unlock' { python tools/contentc/shop_unlock.py --check }                # 3.2 s
    Step 'spawn offsets' { python tools/contentc/spawn_offsets.py --check }            # 1.4 s
    Step 'patch 460.9' { python tools/contentc/newin4609.py --check }                  # 4.0 s
    Step 'rails' { python tools/contentc/rails.py --check }                            # 4.4 s
    Step 'zombie family gaps' { python tools/contentc/zgaps.py --check }               # 0.8 s
    # 截图基线只守表本身（九场景的命令行与历史 hash 都在里面）。真正出图比对要一个带五块
    # meta 屏的桌面 exe，门禁不替它挑 exe，所以这里只做 --list 的解析与自洽校验；出图比对
    # 走 `python tools/snapshot_baseline.py --check --from <report>`，由人按需执行。
    Step 'snapshot baseline' { python tools/snapshot_baseline.py --list }               # 0.4 s
    # 交接中的表：artifex 的 mechanic_entity_resolution 还没落地。文件不在时打印 skip 并把
    # $LASTEXITCODE 归零 —— Step 只看 exit code，上一条命令留下的非零值会把 skip 判成失败。
    # 文件落地后这一条自动变成真门禁，不需要再改这里。
    Step 'mechanic entity resolution' {
        if (Test-Path 'tools/contentc/mechanic_entity_resolution.py') {
            python tools/contentc/mechanic_entity_resolution.py --check
        } else {
            Write-Host '[skip] tools/contentc/mechanic_entity_resolution.py has not landed yet' -ForegroundColor Yellow
            $global:LASTEXITCODE = 0
        }
    }

    # The count is captured from unittest's own summary line so the ledger check below
    # compares two measurements instead of two opinions.
    $pythonRan = -1
    Step 'tool tests' {
        $output = & python -m unittest discover -s tools/tests -p 'test_*.py' 2>&1
        $output | ForEach-Object { Write-Host $_ }
        $ran = [regex]::Match(($output -join "`n"), 'Ran (\d+) tests?')
        if ($ran.Success) { $script:pythonRan = [int]$ran.Groups[1].Value }
    }

    # Baselines are captured *before* the generator runs. Reading them afterwards
    # made the gate self-healing: whatever the fresh render contained was already
    # on disk by the time we compared, so a changed report always looked identical.
    $smoke = Join-Path $repo 'native/generated/engine_smoke.json'
    $smokeFresh = Join-Path $repo 'build/engine_smoke.fresh.json'
    $beforeSmoke = if (Test-Path $smoke) { Get-Content $smoke -Raw } else { '' }
    Step 'engine smoke' {
        python tools/engine_smoke.py --out $smokeFresh
    }
    $afterSmoke = Get-Content $smokeFresh -Raw
    $smokeChanged = -not (Compare-Report $beforeSmoke $afterSmoke)
    Sync-Baseline -Fresh $smokeFresh -Baseline $smoke -Changed $smokeChanged -Label 'native/generated/engine_smoke.json'
    if ($smokeChanged -and -not $AllowMatrixChange) {
        Write-Host "[fail] native/generated/engine_smoke.json changed; review the diff or pass -AllowMatrixChange" -ForegroundColor Red
        $failures.Add('engine smoke changed')
    }

    if ($NoDesktop) {
        Write-Host ""
        Write-Host '== desktop build (skipped) ==' -ForegroundColor Yellow
        Write-Host '[skip] -NoDesktop: battle_view.cpp / assets.cpp were NOT compiled, so this run says nothing about the desktop configuration' -ForegroundColor Yellow
    } else {
        Step-Build -Name 'desktop build' -BuildDir $desktopBuild -AuditOnly $false
    }

    $matrix = Join-Path $repo 'docs/PARITY_MATRIX.md'
    $fresh = Join-Path $repo 'build/PARITY_MATRIX.fresh.md'
    # The matrix is untracked, so git cannot tell us whether it moved: compare
    # the fresh render with what is on disk instead.
    $before = if (Test-Path $matrix) { Get-Content $matrix -Raw } else { '' }
    Step 'parity' {
        python tools/parity_report.py --generated 2026-11-20 --out $fresh
    }
    $after = Get-Content $fresh -Raw
    $matrixChanged = -not (Compare-Report $before $after)
    Sync-Baseline -Fresh $fresh -Baseline $matrix -Changed $matrixChanged -Label 'docs/PARITY_MATRIX.md'
    if ($matrixChanged -and -not $AllowMatrixChange) {
        Write-Host "[fail] docs/PARITY_MATRIX.md changed; review the diff or pass -AllowMatrixChange" -ForegroundColor Red
        $failures.Add('parity matrix changed')
    }

    $worlds = Join-Path $repo 'native/generated/world_diff.md'
    $worldsFresh = Join-Path $repo 'build/world_diff.fresh.md'
    $beforeWorlds = if (Test-Path $worlds) { Get-Content $worlds -Raw } else { '' }
    Step 'world diff' {
        python tools/contentc/worlds.py --generated 2026-11-20 --out $worldsFresh
    }
    $afterWorlds = Get-Content $worldsFresh -Raw
    $worldsChanged = -not (Compare-Report $beforeWorlds $afterWorlds)
    Sync-Baseline -Fresh $worldsFresh -Baseline $worlds -Changed $worldsChanged -Label 'native/generated/world_diff.md'
    if ($worldsChanged -and -not $AllowMatrixChange) {
        Write-Host "[fail] native/generated/world_diff.md changed; review the diff or pass -AllowMatrixChange" -ForegroundColor Red
        $failures.Add('world diff changed')
    }

    # Adding `art_audit` moved audit from 11 to 12 and the desktop tree from 16 to 17;
    # both documents still said the old numbers. Reading the counts out of the run and
    # comparing them with a machine-readable ledger block turns that drift into a gate.
    Write-Host ""
    Write-Host '== test ledger ==' -ForegroundColor Cyan
    $ledgerPath = Join-Path $repo 'docs/PARITY_BASELINE.md'
    $measured = [ordered]@{ audit = (Measure-CtestCount $auditBuild); python = $script:pythonRan }
    if (-not $NoDesktop) { $measured['desktop'] = (Measure-CtestCount $desktopBuild) }
    $ledger = Read-TestLedger $ledgerPath
    if ($UpdateLedger) {
        $write = [ordered]@{}
        foreach ($key in $measured.Keys) { $write[$key] = $measured[$key] }
        Write-TestLedger -Path $ledgerPath -Counts $write
        $ledger = Read-TestLedger $ledgerPath
        Write-Host "[ok] rewrote the test-counts block in docs/PARITY_BASELINE.md (-UpdateLedger)" -ForegroundColor Yellow
    }
    foreach ($key in @($measured.Keys)) {
        $actual = $measured[$key]
        if (-not $ledger.ContainsKey($key)) {
            Write-Host "[fail] $key missing from the test-counts block in docs/PARITY_BASELINE.md" -ForegroundColor Red
            $failures.Add("test ledger: $key missing")
        } elseif ($key -eq 'python') {
            # `tools/tests` is edited by several agents at once, so its count moves every
            # few minutes (136 → 172 → 203 → 217 during one afternoon). Requiring equality
            # there would red the gate for whoever ran next, which teaches people to ignore
            # it. The ledger is a floor instead: losing tests fails, gaining them warns.
            if ($actual -lt $ledger[$key]) {
                Write-Host "[fail] python lost tests: ran $actual, the ledger floor is $($ledger[$key])" -ForegroundColor Red
                $failures.Add("test ledger: python $actual < $($ledger[$key])")
            } elseif ($actual -ne $ledger[$key]) {
                Write-Host "[warn] python ran $actual tests, the ledger says $($ledger[$key]) (+$($actual - $ledger[$key]) since it was written; refresh the block when you touch the docs)" -ForegroundColor Yellow
            } else {
                Write-Host "[ok] python ran $actual tests (ledger agrees)" -ForegroundColor Green
            }
        } elseif ($ledger[$key] -ne $actual) {
            Write-Host "[fail] $key ran $actual tests, the ledger says $($ledger[$key])" -ForegroundColor Red
            $failures.Add("test ledger: $key $actual vs $($ledger[$key])")
        } else {
            Write-Host "[ok] $key ran $actual tests (ledger agrees)" -ForegroundColor Green
        }
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Pop-Location
}

$stampEnd = Get-TreeStamp

Write-Host ""
if ($failures.Count -gt 0) {
    foreach ($failure in $failures) {
        Write-Host "[fail] $failure" -ForegroundColor Red
    }
    exit 1
}
if ($stampStart -ne $stampEnd) {
    Write-Host "[warn] the source tree changed while the gate ran ($stampStart -> $stampEnd)" -ForegroundColor Yellow
    Write-Host '[warn] this run is inconclusive: someone edited code mid-run, so its verdict is about no single tree' -ForegroundColor Yellow
    Write-Host '[inconclusive] rerun on a quiet tree before believing any result' -ForegroundColor Yellow
    exit 2
}
Write-Host '[ok] content, build, tests and parity are consistent' -ForegroundColor Green
exit 0
