$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $RootDir '.venv'

. (Join-Path $ScriptDir 'common.ps1')

Ensure-PythonTools
$python = Get-PythonLauncher
$VenvPython = Ensure-Venv -VenvDir $VenvDir -Python $python
Install-PythonDeps -VenvPython $VenvPython -RootDir $RootDir
Build-WebUi -RootDir $RootDir

$Port = Get-ConfigPort -RootDir $RootDir
Write-Host ''
Write-Host 'ACELink'
Write-Host '-------'
Write-Host ''
Write-Host "Web UI:  http://localhost`:$Port"
Write-Host 'Press Ctrl+C to stop'
Write-Host ''
& $VenvPython (Join-Path $RootDir 'main.py')
