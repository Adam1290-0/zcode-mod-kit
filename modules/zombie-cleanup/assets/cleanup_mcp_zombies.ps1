# Cleanup orphaned MCP node processes left behind by closed ZCode sessions.
#
# ZCode starts one full set of MCP servers (wigolo/filesystem/memory/github/
# sequential-thinking) per session window. When a window closes or ZCode
# restarts, the app-server exits but its MCP child processes are not reaped,
# leaving orphan "zombie" node processes that keep holding memory.
#
# This script kills node.exe processes whose parent process is already dead.
# Live MCP servers always have a living parent (the ZCode app-server), so they
# are never touched. Dry-run mode only lists what would be killed.

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

$ErrorActionPreference = 'SilentlyContinue'
$killed = 0
$candidates = @()

# Only touch node processes that ZCode itself spawns (MCP servers + account
# bridge). Orphaned node from other apps is not our business and an unattended
# schedule must stay surgical.
$patterns = @('wigolo-patched', 'server-filesystem', 'server-memory', 'server-github', 'server-sequential-thinking', 'acct.cjs')

Get-WmiObject Win32_Process -Filter "Name='node.exe'" | ForEach-Object {
    $matches = $patterns | Where-Object { $_.CommandLine -match [regex]::Escape($_) }
    if (-not $matches) { return }
    $parent = Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue
    if (-not $parent) {
        $candidates += $_
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
        Write-Host ("[DRY-RUN] orphan node PID {0} (parent {1} dead): {2}" -f $p.ProcessId, $p.ParentProcessId, $cmd)
    } else {
        Write-Host ("Killing orphan node PID {0} (parent {1} dead)" -f $p.ProcessId, $p.ParentProcessId)
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
