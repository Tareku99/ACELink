$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $RootDir '.venv'

. (Join-Path $ScriptDir 'common.ps1')

function Start-AcelinkScheduledTask {
    $taskName = 'ACELink'
    $pythonPath = $VenvPython
    $mainPath = Join-Path $RootDir 'main.py'
    $args = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"& '$pythonPath' '$mainPath'`""

    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $args
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Seconds 10)

    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        try {
            Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        } catch {
            # Ignore if the task is not currently running.
        }

        try {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        } catch {
            # Ignore missing task
        }
    }

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings | Out-Null
    Start-ScheduledTask -TaskName $taskName
    return $taskName
}

Ensure-PythonTools

Write-Host 'Installing or updating ACELink...'
Write-Host 'Creating or updating the Python virtual environment...'
$python = Get-PythonLauncher
$VenvPython = Ensure-Venv -VenvDir $VenvDir -Python $python
Install-PythonDeps -VenvPython $VenvPython -RootDir $RootDir
Build-WebUi -RootDir $RootDir

Write-Host 'Configuring ACELink to start automatically...'

$TaskName = Start-AcelinkScheduledTask

Start-Sleep -Seconds 3

Write-Host "Scheduled task active: $TaskName"

$LanIp = $null
try {
    $LanIp = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -notlike '127.*' -and
            $_.IPAddress -notlike '169.254.*' -and
            $_.InterfaceOperationalStatus -eq 'Up'
        } |
        Select-Object -First 1 -ExpandProperty IPAddress
} catch {
    $LanIp = $null
}

if (-not $LanIp) {
    $LanIp = 'localhost'
}

$Port = Get-ConfigPort -RootDir $RootDir
Write-Host ''
Write-Host 'ACELink is running.'
Write-Host "Open the web UI at: http://$LanIp`:$Port"
Write-Host "Local access also works at: http://localhost`:$Port"
Write-Host 'ACELink will start automatically at the next logon.'
Write-Host 'Run this same install script again after a git pull to apply updates.'
