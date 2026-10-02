<#
.SYNOPSIS
    Build mode on Taylor's laptop: on for N hours, off, or status. Mike runs it from a terminal.

.DESCRIPTION
    NEW in this repo. While Mike builds on Taylor's laptop, build mode lets this machine change
    the system's code (protect-architecture.py, layer B) and dispatch dev agents (Explore, Plan,
    general-purpose, plugin reviewers) that are not on Taylor's team. Taylor's switched-off agents
    stay off, and no-cloud.py still refuses `git push` from any session: Mike pushes from this
    terminal.

    It is a marker, state\BUILD_MODE: this host's name on the first line and an expiry in UTC on
    the second. Every gate, the status line, the roll call and the doctor read it the same way
    (.claude\hooks\_health.py). An expired marker is OFF everywhere, so forgetting to switch it
    off costs at most the hours given, and the BUILD MODE banner on every turn says when.

    Mike's own machine keeps the permanent marker state\BUILD_MACHINE (its host name, no expiry),
    created by hand once. This script never writes that one.

    Refused inside a Claude Code session, which sets CLAUDECODE, CLAUDE_CODE_ENTRYPOINT,
    CLAUDE_CODE_SESSION_ID or CLAUDE_PID for every command it runs; protect-architecture.py also
    refuses any session command that runs this script or writes the marker.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_mode.ps1 on -Hours 4
    powershell -ExecutionPolicy Bypass -File scripts\build_mode.ps1 status
    powershell -ExecutionPolicy Bypass -File scripts\build_mode.ps1 off
#>
param(
    [Parameter(Position = 0)][ValidateSet("on", "off", "status")][string]$Action = "status",
    [double]$Hours = 4
)
$ErrorActionPreference = "Stop"
$MaxHours = 24

foreach ($name in @("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")) {
    if (Test-Path "Env:$name") {
        Write-Output "REFUSED: build mode is switched by Mike from his own terminal, never from a Claude Code session ($name is set)."
        exit 2
    }
}

$root = Split-Path -Parent $PSScriptRoot
$marker = Join-Path $root "state\BUILD_MODE"
$machine = Join-Path $root "state\BUILD_MACHINE"
$hostName = [System.Net.Dns]::GetHostName()

switch ($Action) {
    "on" {
        if ($Hours -le 0 -or $Hours -gt $MaxHours) {
            Write-Output "REFUSED: -Hours must be more than 0 and at most $MaxHours."
            exit 2
        }
        $now = [DateTime]::UtcNow
        $until = $now.AddHours($Hours)
        $invariant = [Globalization.CultureInfo]::InvariantCulture  # ':' is a culture's time separator otherwise
        $stamp = $until.ToString("yyyy-MM-ddTHH:mm:ss", $invariant) + "Z"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $marker) | Out-Null
        $body = "$hostName`n$stamp`nswitched on by $env:USERNAME at " + $now.ToString("yyyy-MM-ddTHH:mm:ss", $invariant) + "Z`n"
        [System.IO.File]::WriteAllText($marker, $body)  # UTF-8 without a BOM: a BOM would make the host name not match
        Write-Output ("BUILD MODE ON until " + $until.ToLocalTime().ToString("ddd yyyy-MM-dd HH:mm") + " (local time).")
        Write-Output "Code can change here and dev agents can run until then. Reload the VS Code window to see it."
        Write-Output "End it early: powershell -ExecutionPolicy Bypass -File scripts\build_mode.ps1 off"
    }
    "off" {
        if (Test-Path $marker) {
            Remove-Item -Force $marker
            Write-Output "BUILD MODE OFF. Reload the VS Code window."
        } else {
            Write-Output "Build mode was already off."
        }
    }
    "status" {
        if ((Test-Path $machine) -and ((Get-Content $machine -TotalCount 1).Trim() -eq $hostName)) {
            Write-Output "BUILD MACHINE: state\BUILD_MACHINE names this host, so build mode never expires here."
            exit 0
        }
        if (-not (Test-Path $marker)) {
            Write-Output "Build mode is off."
            exit 0
        }
        $lines = @(Get-Content $marker)
        if ($lines.Count -lt 2 -or $lines[0].Trim() -ne $hostName) {
            Write-Output "Build mode is off: state\BUILD_MODE does not name this machine."
            exit 0
        }
        $until = [DateTime]::Parse($lines[1].Trim(), [Globalization.CultureInfo]::InvariantCulture,
                                   [Globalization.DateTimeStyles]::AdjustToUniversal)
        if ($until -gt [DateTime]::UtcNow.AddHours($MaxHours).AddMinutes(5)) {
            Write-Output "Build mode is off: its expiry is more than $MaxHours hours ahead, which this script never writes."
        } elseif ($until -le [DateTime]::UtcNow) {
            Write-Output ("Build mode is off: it expired " + $until.ToLocalTime().ToString("ddd yyyy-MM-dd HH:mm") + ". Remove the stale marker with: build_mode.ps1 off")
        } else {
            Write-Output ("BUILD MODE ON until " + $until.ToLocalTime().ToString("ddd yyyy-MM-dd HH:mm") + " (local time).")
        }
    }
}
exit 0
