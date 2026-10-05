# probe_agy.ps1 - register rows 1 and 2, Windows port of probe_agy.sh.
#
# Settles one question: can an orchestrator drive `agy` unattended on THIS
# machine? Checks it rather than trusting community reports.
#
# Differences from the bash probe, all forced by Windows:
#   - no timeout(1): a hard kill timer here, and agy's own --print-timeout is
#     tested as a shape of its own;
#   - no script(1) / PTY: shape D is reported SKIP, never faked;
#   - no profile flag exists in `agy --help`, so row 2 overrides the profile
#     environment variables for the child process instead of HOME.
#
# Run from a directory you do not mind an agent reading. Writes probe_agy.log.
#
#   powershell -File pipeline\probe_agy.ps1

$ErrorActionPreference = "Stop"

$Prompt  = "Reply with exactly the word: ALIVE"
$Timeout = if ($env:PROBE_TIMEOUT) { [int]$env:PROBE_TIMEOUT } else { 90 }
$Log     = "probe_agy.log"
Set-Content -Path $Log -Value "" -Encoding ASCII

$script:pass = 0
$script:fail = 0

function Say([string]$m) { Write-Host $m; Add-Content -Path $Log -Value $m -Encoding ASCII }
function Head([string]$m) { Say ""; Say ("-- $m " + ("-" * 40)) }

# Absolute path, so a changed LOCALAPPDATA in row 2 cannot hide the binary.
$cmd = Get-Command agy -ErrorAction SilentlyContinue
$Agy = if ($cmd) { $cmd.Source } else { Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe" }
if (-not (Test-Path $Agy)) { Say "agy not found - install it first, then re-run."; exit 2 }

function Quote([string]$a) { if ($a -match '[\s"]') { '"' + ($a -replace '"', '\"') + '"' } else { $a } }

# Runs agy with stdin closed and stdout/stderr captured through pipes (what
# subprocess.run does). Returns exit code (124 = killed by the hard timer),
# combined output, and elapsed seconds.
function Invoke-Agy {
    param([string[]]$ArgList, [hashtable]$Env = @{}, [int]$HardTimeout = $Timeout, [string]$StdoutFile = "")
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Agy
    $psi.Arguments = ($ArgList | ForEach-Object { Quote $_ }) -join " "
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    foreach ($k in $Env.Keys) { $psi.EnvironmentVariables[$k] = $Env[$k] }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = [System.Diagnostics.Process]::Start($psi)
    $p.StandardInput.Close()
    $so = $p.StandardOutput.ReadToEndAsync()
    $se = $p.StandardError.ReadToEndAsync()
    if ($p.WaitForExit($HardTimeout * 1000)) {
        $rc = $p.ExitCode
        $p.WaitForExit()
    } else {
        & taskkill /T /F /PID $p.Id *> $null
        $rc = 124
    }
    $sw.Stop()
    $out = ""
    try { $out = $so.Result + $se.Result } catch { }
    if ($StdoutFile) { Set-Content -Path $StdoutFile -Value $out -Encoding UTF8 }
    return [pscustomobject]@{ Rc = $rc; Out = $out; Secs = [math]::Round($sw.Elapsed.TotalSeconds, 1) }
}

function Verdict([string]$name, $r) {
    $o = ($r.Out -replace '\s+$', '')
    if ($r.Rc -eq 124) {
        Say "FAIL  $name - killed after ${Timeout}s (the hang defect)"; $script:fail++
    } elseif ($r.Rc -ne 0) {
        $snip = $o.Substring(0, [math]::Min(200, $o.Length))
        Say "FAIL  $name - exit $($r.Rc) after $($r.Secs)s"; Say "      $snip"; $script:fail++
    } elseif ([string]::IsNullOrWhiteSpace($o)) {
        Say "FAIL  $name - exit 0 but no output (the silent-drop defect)"; $script:fail++
    } else {
        Say "PASS  $name - $($o.Length) chars in $($r.Secs)s"; $script:pass++
    }
}

Head "Environment"
$ver = (& $Agy --version 2>&1 | Select-Object -First 1)
Say "agy:      $ver"
Say "path:     $Agy"
Say "stdout redirected: $([Console]::IsOutputRedirected)"
Say "timeout(1): n/a on Windows (hard kill timer + --print-timeout)"
Say "script(1):  n/a on Windows (PTY shape skipped)"

# ---------------------------------------------------------------- row 1 -----
Head "Row 1 - does -p produce output without a TTY?"

# A. captured through pipes - what subprocess.run does. stdin closed.
Verdict "pipe (stdout/stderr captured, stdin closed)" (Invoke-Agy @("-p", $Prompt))

# B. stdout redirected to a regular file.
$bf = ".probe_b.txt"
$rb = Invoke-Agy @("-p", $Prompt) -StdoutFile $bf
Verdict "redirect to file" $rb

# C. --output-format json - the shape an adapter actually wants.
$rc_ = Invoke-Agy @("-p", $Prompt, "--output-format", "json")
Verdict "pipe + --output-format json" $rc_
if ($rc_.Rc -eq 0) {
    try { $null = $rc_.Out | ConvertFrom-Json; Say "      json: parses" }
    catch { Say "      json: DOES NOT PARSE as one JSON document (stderr mixed in, or a stream)" }
}

# D. under a pseudo-terminal - no script(1) here, and stock PowerShell cannot
# allocate a PTY. Not faked.
Say "SKIP  PTY - not available on Windows without a ConPTY wrapper; not tested"

# E. agy's own bound instead of timeout(1).
Verdict "pipe + --print-timeout ${Timeout}s" (Invoke-Agy @("-p", $Prompt, "--print-timeout", "${Timeout}s"))

# F. does --print-timeout actually enforce? A 1s bound on a real model turn.
$rf = Invoke-Agy @("-p", $Prompt, "--output-format", "json", "--print-timeout", "1s") -HardTimeout 60
$notice = $rf.Out -match "print timeout after"
if ($rf.Rc -eq 124) {
    Say "FAIL  --print-timeout 1s NOT enforced - still running at the 60s hard kill"
} elseif ($notice -and $rf.Rc -eq 0) {
    Say "WARN  --print-timeout 1s enforced on the TURN but reported as SUCCESS: exit 0 after $($rf.Secs)s,"
    Say "      stderr notice 'print timeout ... returning partial output', empty response."
    Say "      An adapter must treat empty output / that notice as failure, and still needs"
    Say "      an outer kill timer: the bound does not cover startup ($($rf.Secs)s total)."
} elseif ($rf.Rc -ne 0) {
    Say "PASS  --print-timeout 1s enforced - exit $($rf.Rc) after $($rf.Secs)s"
} else {
    Say "NOTE  --print-timeout 1s - finished in $($rf.Secs)s with no timeout notice; enforcement not shown"
}

# ---------------------------------------------------------------- row 2 -----
Head "Row 2 - does it authenticate without the signed-in profile?"
Say "No profile flag exists. Overriding USERPROFILE, HOME, APPDATA, LOCALAPPDATA and"
Say "XDG_* for the child to an empty directory. Windows Credential Manager is per-user"
Say "and is NOT moved by these, so SUCCEEDS means credentials are reachable from"
Say "outside the profile directory."
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("agy-empty-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
$envs = @{
    USERPROFILE = $tmp; HOME = $tmp; APPDATA = $tmp; LOCALAPPDATA = $tmp
    XDG_CONFIG_HOME = $tmp; XDG_DATA_HOME = $tmp; XDG_CACHE_HOME = $tmp
}
$r2 = Invoke-Agy @("-p", $Prompt, "--print-timeout", "${Timeout}s") -Env $envs
$o2 = ($r2.Out -replace '\s+$', '')
$snip2 = $o2.Substring(0, [math]::Min(200, $o2.Length))
if ($r2.Rc -eq 124) {
    Say "HANGS - waits for interactive auth. Unattended runs need a pre-authenticated profile."
} elseif ($r2.Rc -ne 0) {
    Say "EXITS $($r2.Rc) after $($r2.Secs)s - fails cleanly without the profile (better than hanging)."
    Say "      $snip2"
} else {
    Say "SUCCEEDS in $($r2.Secs)s - credentials are reachable from outside the profile dir."
    Say "           Find out where before claiming the worker container is credential-free."
    Say "      $snip2"
}
$left = @(Get-ChildItem -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue).Count
Say "files agy created in the empty profile: $left"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

# ------------------------------------------------------------------ out -----
Remove-Item -Force $bf -ErrorAction SilentlyContinue
Head "Result"
Say "row 1: $($script:pass) passed, $($script:fail) failed"
Say ""
if ($script:fail -eq 0 -and $script:pass -gt 0) {
    Say "The adapter can use plain subprocess with stdin closed. Build it that way."
} elseif ($script:pass -gt 0) {
    Say "Some shapes work and some do not. The adapter must use whichever passed above."
} else {
    Say "Nothing worked unattended. agy is not usable as the worker on this machine today."
}
Say ""
Say "Paste this log into .ai/VERIFIED.md with today's date."
