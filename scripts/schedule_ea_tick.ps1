<#
    Register the tick with Task Scheduler. PORTED FROM PIPER's schedule_cadence_tick.ps1.

        powershell -ExecutionPolicy Bypass -File scripts\schedule_ea_tick.ps1 -RunNow
        powershell -ExecutionPolicy Bypass -File scripts\schedule_ea_tick.ps1 -Status
        powershell -ExecutionPolicy Bypass -File scripts\schedule_ea_tick.ps1 -Remove

    Run on Taylor's machine at install, by Mike. NOT run on the build machine.

    ------------------------------------------------------------------------
    THE BATTERY GATE. -AllowStartIfOnBatteries and -DontStopIfGoingOnBatteries both
    default restrictive, so on an unplugged laptop the task simply does not run, and
    -StartWhenAvailable does not help because the blocking condition is power, not
    availability. Six STEVIE tasks have this defect. Taylor works on a laptop. Do not
    "clean these up".
    ------------------------------------------------------------------------

    A DAILY TRIGGER AT 07:00 REPEATING EVERY 4 HOURS FOR A DAY. A laptop asleep at
    07:00 still ticks at 11:00, 15:00, 19:00 or 23:00, and an unchanged Doc revision
    makes the extra runs nearly free. 30-minute execution limit.

    WHAT IT RUNS. run_ea_tick.ps1, which runs ea_tick.py: deterministic Python that
    reads the Docs and the Calendar and writes only the local register. It does NOT
    run `claude -p`; that indirection is what let STEVIE's sweep rot for eleven weeks.

    The task registers as the current user, not as an administrator, so the token in
    state\google-token.json and the register stay readable by Taylor's own account.
#>
param(
    [switch]$Remove,
    [switch]$RunNow,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
$TaskName = "EA-Tick"
$Project  = Split-Path -Parent $PSScriptRoot
$Wrapper  = Join-Path $Project "scripts\run_ea_tick.ps1"
$At       = "07:00"

function Show-Status {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Write-Host "  $TaskName is not registered."; return }
    $i = Get-ScheduledTaskInfo -TaskName $TaskName
    $settings = $t.Settings
    Write-Host "  Task        : $TaskName"
    Write-Host "  State       : $($t.State)"
    Write-Host "  Action      : $($t.Actions[0].Arguments)"
    Write-Host "  On battery  : start=$($settings.DisallowStartIfOnBatteries -eq $false) keep-running=$($settings.StopIfGoingOnBatteries -eq $false)"
    Write-Host "  Last run    : $($i.LastRunTime)"
    Write-Host "  Last result : $($i.LastTaskResult)  (0 ok, 2 preflight, 3 register write failed, 4 partial, 9 crash)"
    Write-Host "  Next run    : $($i.NextRunTime)"
}

if ($Status) { Show-Status; exit 0 }

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed $TaskName."
    } else {
        Write-Host "$TaskName was not registered."
    }
    exit 0
}

if (-not (Test-Path $Wrapper)) { Write-Error "Wrapper not found: $Wrapper"; exit 1 }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Existing task found. Current state:"
    Show-Status
    Write-Host ""
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File `"$Wrapper`"" `
    -WorkingDirectory $Project

$trigger = New-ScheduledTaskTrigger -Daily -At $At
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $At `
    -RepetitionInterval (New-TimeSpan -Hours 4) `
    -RepetitionDuration (New-TimeSpan -Days 1)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force `
    -Description "Executive-assistant tick: reads the registered 1:1 Docs and Calendar series and updates the local register. Writes nothing to any Doc. Daily 07:00, repeating every 4h, allowed on battery. See scripts/schedule_ea_tick.ps1." | Out-Null

Write-Host "Registered $TaskName (daily $At, repeating every 4h for 1 day, allowed on battery)."
Write-Host ""

if ($RunNow) {
    # Prove it runs now rather than trusting it.
    Write-Host "Starting a verification run..."
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 5
    $waited = 5
    while ((Get-ScheduledTask -TaskName $TaskName).State -eq "Running" -and $waited -lt 900) {
        Start-Sleep -Seconds 5; $waited += 5
    }
    Show-Status
    $res = (Get-ScheduledTaskInfo -TaskName $TaskName).LastTaskResult
    if ($res -eq 0) {
        Write-Host "`n  Verification run succeeded. Confirm with: python scripts\ea_doctor.py"
    } else {
        Write-Warning "`n  Verification run returned $res; read logs\ea-tick.log and logs\ea-tick.err.log"
    }
} else {
    Show-Status
    Write-Host "`nRun with -RunNow to prove it executes before trusting the schedule."
}
