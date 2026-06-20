$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-PythonLauncher {
    $py312 = Get-Command py -ErrorAction SilentlyContinue
    if ($py312) {
        try {
            $version = & $py312.Path -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            if ($version.Trim() -eq '3.12') {
                return @{
                    Command = $py312.Path
                    Args    = @('-3.12')
                }
            }
        } catch {
            # Ignore and fall through to other launchers.
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $version = & $py.Path -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            if ($version.Trim() -eq '3.12') {
                return @{
                    Command = $py.Path
                    Args    = @('-3')
                }
            }
        } catch {
            # Ignore and fall through to other launchers.
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        try {
            $version = & $python.Path -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            if ($version.Trim() -eq '3.12') {
                return @{
                    Command = $python.Path
                    Args    = @()
                }
            }
        } catch {
            # Ignore and fall through.
        }
    }

    throw 'Python 3.12 is required on Windows for this project. Install Python 3.12 and rerun this script.'
}

function Test-NodeBuildTools {
    return (Get-Command node -ErrorAction SilentlyContinue) -and (Get-Command npm -ErrorAction SilentlyContinue)
}

function Test-NodeVersion {
    $major = & node -p "process.versions.node.split('.')[0]"
    return [int]$major -ge 18
}

function Ensure-PythonTools {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw 'Node.js is required to build the web UI.'
    }

    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw 'npm is required to build the web UI.'
    }

    if (-not (Test-NodeVersion)) {
        throw 'Node.js 18 or newer is required to build the web UI.'
    }
}

function Ensure-Venv {
    param(
        [Parameter(Mandatory = $true)][string]$VenvDir,
        [Parameter(Mandatory = $true)][hashtable]$Python
    )

    if (-not (Test-Path $VenvDir)) {
        & $Python.Command @($Python.Args + @('-m', 'venv', $VenvDir))
    }

    $venvPython = Join-Path $VenvDir 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        throw "Expected virtual environment Python at $venvPython. Delete .venv and rerun the installer."
    }

    $venvVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($venvVersion.Trim() -ne '3.12') {
        throw "The existing .venv was created with Python $($venvVersion.Trim()), but ACELink requires Python 3.12. Delete .venv and rerun the script after installing Python 3.12."
    }

    return $venvPython
}

function Install-PythonDeps {
    param(
        [Parameter(Mandatory = $true)][string]$VenvPython,
        [Parameter(Mandatory = $true)][string]$RootDir
    )

    & $VenvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $RootDir 'requirements.txt') | Out-Null
}

function Build-WebUi {
    param(
        [Parameter(Mandatory = $true)][string]$RootDir
    )

    Push-Location (Join-Path $RootDir 'webui')
    try {
        npm ci
        npm run build
    }
    finally {
        Pop-Location
    }
}

function Ensure-WebUiBuilt {
    param(
        [Parameter(Mandatory = $true)][string]$RootDir
    )

    if (-not (Test-Path (Join-Path $RootDir 'webui\dist\index.html'))) {
        Build-WebUi -RootDir $RootDir
    }
}

function Get-ConfigPort {
    param(
        [Parameter(Mandatory = $true)][string]$RootDir
    )

    $configPath = Join-Path $RootDir 'acelink.config.json'
    if (-not (Test-Path $configPath)) {
        return 8765
    }

    try {
        $data = Get-Content $configPath -Raw | ConvertFrom-Json
        if ($null -ne $data.port) {
            return [int]$data.port
        }
    } catch {
        # Fall back to default.
    }

    return 8765
}
