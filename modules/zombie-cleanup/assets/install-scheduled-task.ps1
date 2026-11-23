# Register the hourly safety-net scheduled task for the MCP zombie cleaner.
#
# The zcode.cjs shutdown hook only fires when ZCode exits cleanly. If ZCode is
# killed, crashes, or the user closes the window in a way that skips the hook,
# orphans accumulate until the next clean exit. This task bounds that interval
# to one hour.
#
# Run with -Unregister to remove it.

param(
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$taskName = 'ZCode-MCP-Zombie-Cleanup'
$script = Join-Path $PSScriptRoot 'cleanup_mcp_zombies.ps1'

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed scheduled task '$taskName'."
    } else {
        Write-Host "Scheduled task '$taskName' not present."
    }
    return
}

if (-not (Test-Path $script)) {
    Write-Error "cleanup script not found: $script"
    return
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Tag scheduled' -f $script)

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 1)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Set-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings | Out-Null
    Write-Host "Updated scheduled task '$taskName' (hourly)."
} else {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Description 'Kill orphaned ZCode MCP node processes once an hour' | Out-Null
    Write-Host "Registered scheduled task '$taskName' (hourly)."
}
