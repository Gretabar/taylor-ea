<#
    The wrapper Task Scheduler actually executes for the tick. PORTED FROM PIPER's
    run_cadence_tick.ps1: the shape, the outside-the-process exit-code watch, the
    alarm's interpreter list, and the reasoning below are kept. What changed: it runs
    scripts\ea_tick.py, alarms through scripts\notify_owner.py, logs to
    logs\ea-tick.log, and has no -Live switch because the tick has no send path.

    WHY A WRAPPER RATHER THAN CALLING python.exe DIRECTLY. STEVIE-QueueSweep failed
    from 2026-05-25 and nothing alerted, because the process died BEFORE its own
    error handling ran. Python-level try/except cannot report a failure to START: a
    missing interpreter, an import error, or a crash above main() leaves no Python
    alive to raise the alarm. This watches the exit code from OUTSIDE the process.

    -RedirectStandardOutput TRUNCATES, so it is NOT pointed at the rolling log. Each
    run is captured to a temp file and APPENDED, keeping real history, and the
    rolling log is trimmed at 5 MB.

    Everything sits inside try/catch because $ErrorActionPreference = "Stop" makes
    every cmdlet failure terminating, and a terminating error would kill the script
    above the alarm block. The two helpers are the alarm itself, so neither throws.

    Exit codes passed straight through from ea_tick.py:
        0  ticked, nothing registered yet, or another run holds the lock
        2  preflight failed: identity unreadable, token missing, expired or short a scope
        3  the register could not be written
        4  partial: a Doc or Calendar series could not be read; the rest was done
        9  the tick crashed, or this wrapper did
#>
param(
    [switch]$DryRun,        # read everything, write nothing
    [string]$Date           # report as of this date, for testing
)

$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
$LogDir  = Join-Path $Project "logs"
$Log     = Join-Path $LogDir "ea-tick.log"
$ErrLog  = Join-Path $LogDir "ea-tick.err.log"

function Resolve-Python {
    # A LIST: "the interpreter is unusable" has two shapes, absent and broken.
    $candidates = @()
    if ($env:EA_PYTHON -and (Test-Path $env:EA_PYTHON)) { $candidates += $env:EA_PYTHON }
    $onPath = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($onPath) { $candidates += $onPath }
    $onPath3 = (Get-Command python3.exe -ErrorAction SilentlyContinue).Source
    if ($onPath3) { $candidates += $onPath3 }
    return ($candidates | Select-Object -Unique)
}

function Write-JobLog([string]$Text) {
    # An unwritable log is one of the failures this wrapper reports, so it must not
    # also kill the reporter.
    try { Add-Content -Path $script:Log -Value $Text -ErrorAction Stop } catch { }
}

function Send-Alarm([string]$Text) {
    # Never throws. $ErrorActionPreference drops to Continue: under "Stop", one line
    # of stderr from a native process is a terminating error.
    $ErrorActionPreference = "Continue"
    $notifier = Join-Path $script:Project "scripts\notify_owner.py"
    foreach ($py in (Resolve-Python)) {
        # $global: is load-bearing: a bare assignment would shadow the variable `&` sets.
        $global:LASTEXITCODE = $null
        try {
            & $py $notifier --level fail --source ea-tick --text $Text | Out-Null
        } catch {
            Write-JobLog "ea-tick: alarm via $py failed ($($_.Exception.Message)); trying the next interpreter"
            continue
        }
        if ($global:LASTEXITCODE -eq 0) { return }
        Write-JobLog "ea-tick: notify_owner.py via $py returned $global:LASTEXITCODE. Message was: $Text"
        return
    }
    Write-JobLog "ea-tick: no usable python; could not raise the alarm. Message was: $Text"
}

function Invoke-Watchdog {
    # The out-of-band liveness check: a toast, because the status line and /morning
    # only render when Taylor has a session open. It cannot affect the exit code.
    $ErrorActionPreference = "Continue"
    try {
        $watcher = Join-Path $script:Project "scripts\notify_owner.py"
        if (-not (Test-Path $watcher)) { return }
        foreach ($py in (Resolve-Python)) {
            & $py $watcher --watch 2>&1 | ForEach-Object { Write-JobLog "watchdog: $_" }
            return
        }
    } catch {
        Write-JobLog "ea-tick: watchdog check failed ($($_.Exception.Message)); the tick result is unaffected"
    }
}

try {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

    $pythons = @(Resolve-Python)
    if ($pythons.Count -eq 0) {
        # Not Write-Error: under "Stop" that is terminating and would die above the alarm.
        $msg = "ea-tick: no python interpreter found (set EA_PYTHON or put python on PATH)"
        Write-JobLog $msg
        Write-Host $msg
        Send-Alarm "$msg  (log: $Log)"
        exit 9
    }
    $Python = $pythons[0]

    $jobArgs = @((Join-Path $Project "scripts\ea_tick.py"))
    if ($DryRun) { $jobArgs += "--dry-run" }
    if ($Date)   { $jobArgs += @("--date", $Date) }

    Add-Content -Path $Log -Value "===== run $(Get-Date -Format o) : $($jobArgs -join ' ')"

    $RunOut = Join-Path $LogDir "ea-tick.out.tmp"
    $RunErr = Join-Path $LogDir "ea-tick.err.tmp"
    $p = Start-Process -FilePath $Python -ArgumentList $jobArgs `
         -WorkingDirectory $Project -Wait -PassThru -NoNewWindow `
         -RedirectStandardOutput $RunOut -RedirectStandardError $RunErr
    $code = $p.ExitCode

    # This run's stderr tail, read before it is folded into the rolling file, so a
    # previous run's error is never quoted at a run that produced none.
    $tail = ""
    if (Test-Path $RunErr) {
        $tail = (Get-Content $RunErr -Tail 3 -ErrorAction SilentlyContinue) -join " | "
    }
    foreach ($pair in @(@($RunOut, $Log), @($RunErr, $ErrLog))) {
        if (Test-Path $pair[0]) {
            Get-Content $pair[0] -ErrorAction SilentlyContinue | Add-Content -Path $pair[1]
            Remove-Item $pair[0] -Force -ErrorAction SilentlyContinue
        }
    }
    Add-Content -Path $Log -Value "===== exit $code at $(Get-Date -Format o)"

    foreach ($f in @($Log, $ErrLog)) {
        if ((Test-Path $f) -and ((Get-Item $f).Length -gt 5MB)) {
            $keep = Get-Content $f -Tail 2000
            Set-Content -Path $f -Value $keep -Encoding utf8
        }
    }

    if ($code -ne 0) {
        Send-Alarm "ea tick exited $code. $tail  (log: $Log)"
    }
    # On success this deliberately stamps nothing: the heartbeat is written by
    # ea_tick.py itself, and a wrapper that stamps one the job did not earn is how a
    # dead job looks alive.

    Invoke-Watchdog
    exit $code
}
catch {
    $err  = $_
    $line = $err.InvocationInfo.ScriptLineNumber
    $msg  = "ea-tick wrapper crashed at line ${line}: $($err.Exception.Message)"
    Write-JobLog "===== $msg"
    Write-Host $msg
    Send-Alarm "$msg  (log: $Log)"
    exit 9
}
