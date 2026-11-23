# Cleanup orphaned MCP node processes left behind by closed ZCode sessions.
#
# ZCode starts one full set of MCP servers (wigolo/filesystem/memory/github/
# sequential-thinking) per session window, usually wrapped in a cmd.exe shim.
# When a window closes or ZCode restarts, the app-server exits but its MCP
# child processes survive - and the cmd.exe shim stays alive too, so a plain
# "parent is dead" test never matches them.
#
# The reliable test is the ANCESTOR CHAIN: walk up from the node process; if no
# live ZCode.exe appears anywhere above it, the process belongs to a session
# that no longer exists and is safe to kill.
#
# Dry-run mode only lists what would be killed.

param(
    [switch]$DryRun,
    [string]$Tag = 'manual'
)

function Log-Line {
    param([int]$Orphans, [int]$Killed, [bool]$Dry, $Candidates, [string]$Who)
    $mode = if ($Dry) { "dryrun" } else { "clean" }
    $pids = "none"
    if ($Candidates) {
        $pids = ($Candidates | ForEach-Object { $_.ProcessId }) -join ","
    }
    $line = "{0} | mode={1} orphans={2} killed={3} pids={4} tag={5}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $mode, $Orphans, $Killed, $pids, $Who
    $reportsDir = Join-Path $PSScriptRoot "reports"
    if (-not (Test-Path $reportsDir)) { New-Item -ItemType Directory -Path $reportsDir | Out-Null }
    $logFile = Join-Path $reportsDir "mcp-cleanup.log"
    Add-Content -Path $logFile -Value $line -Encoding Ascii
}

# Walk up the parent chain (bounded) looking for a live ZCode.exe.
# Returns $true when the process still belongs to a running ZCode tree.
function Test-OwnedByZCode {
    param([int]$ProcessId)

    $cur = $ProcessId
    $seen = @{}
    for ($i = 0; $i -lt 8; $i++) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$cur"
        if (-not $proc) { return $false }          # chain broke -> orphan
        if ($seen.ContainsKey($cur)) { return $false }
        $seen[$cur] = $true
        if ($proc.Name -eq 'ZCode.exe') { return $true }

        $parentId = [int]$proc.ParentProcessId
        if ($parentId -le 0) { return $false }     # reached the root -> orphan
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId"
        if (-not $parent) { return $false }

        # Guard against PID reuse: a recycled parent PID would otherwise look
        # like a live ancestor. The parent must have been created no later than
        # the child it supposedly spawned.
        if ($parent.CreationDate -and $proc.CreationDate -and
            $parent.CreationDate -gt $proc.CreationDate) {
            return $false     # parent is younger than child -> not a real parent
        }
        $cur = $parentId
    }
    return $false
}

$ErrorActionPreference = 'SilentlyContinue'
$killed = 0
$candidates = @()

# Only touch node processes that ZCode itself spawns (MCP servers + account
# bridge). Orphaned node from other apps is not our business and an unattended
# schedule must stay surgical.
$patterns = @('wigolo-patched', 'server-filesystem', 'server-memory', 'server-github', 'server-sequential-thinking', 'acct.cjs')

foreach ($proc in (Get-CimInstance Win32_Process -Filter "Name='node.exe'")) {
    $cmd = $proc.CommandLine
    if (-not $cmd) { continue }

    # Match the command line against the whitelist. `$proc` is the live process
    # object here - the previous version piped $patterns and tested
    # $_.CommandLine on a STRING, which is always $null, so nothing ever
    # matched and the module silently cleaned nothing.
    $isMcp = $false
    foreach ($pat in $patterns) {
        if ($cmd -match [regex]::Escape($pat)) { $isMcp = $true; break }
    }
    if (-not $isMcp) { continue }

    if (-not (Test-OwnedByZCode -ProcessId ([int]$proc.ProcessId))) {
        $candidates += $proc
    }
}

if ($candidates.Count -eq 0) {
    Write-Host "No orphan MCP processes found."
    Log-Line 0 0 $DryRun $candidates $Tag
    exit 0
}

foreach ($p in $candidates) {
    $cmd = $p.CommandLine
    if ($cmd.Length -gt 100) { $cmd = $cmd.Substring(0, 100) + "..." }
    if ($DryRun) {
        Write-Host ("[DRY-RUN] orphan node PID {0} (no live ZCode in ancestry): {1}" -f $p.ProcessId, $cmd)
    } else {
        Write-Host ("Killing orphan node PID {0} (no live ZCode in ancestry)" -f $p.ProcessId)
        Stop-Process -Id $p.ProcessId -Force
        $killed++
    }
}

if (-not $DryRun) {
    Write-Host ("Done. Killed {0} orphan MCP process(es)." -f $killed)
} else {
    Write-Host ("Dry-run: {0} orphan process(es) would be killed." -f $candidates.Count)
}
Log-Line $candidates.Count $killed $DryRun $candidates $Tag
