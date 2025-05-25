# PowerShell script for setting up FilePilot virtual environment on Windows
# Run this script from a PowerShell command prompt
# Specifically targeting Python 3.12

Write-Host "Setting up virtual environment for FilePilot with Python 3.12 on Windows..." -ForegroundColor Cyan

# Define virtual environment directory
$VENV_DIR = "venv"

# Check if Python 3.12 is installed
$PYTHON = $null
$pythonVersion = $null

try {
    # First check for python3.12 specifically
    $lpythonVersion = (python3.12 --version 2>&1)
    $PYTHON = "python3.12"
} catch {
    try {
        # Then check for python3
        $pythonVersion = (python3 --version 2>&1)
        if ($pythonVersion -match "Python 3.12") {
            $PYTHON = "python3"
        } else {
            # Then check for python
            try {
                $pythonVersion = (python --version 2>&1)
                if ($pythonVersion -match "Python 3.12") {
                    $PYTHON = "python"
                } else {
                    # Python exists but not 3.12
                    if ($pythonVersion -match "Python 3") {
                        Write-Host "Warning: Python 3.12 not found. Using $pythonVersion" -ForegroundColor Yellow
                        Write-Host "For best compatibility, consider installing Python 3.12." -ForegroundColor Yellow
                        $PYTHON = "python"
                    } else {
                        Write-Host "Error: Python 3 is required but not found." -ForegroundColor Red
                        Write-Host "Please install Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Red
                        exit 1
                    }
                }
            } catch {
                Write-Host "Error: Python 3.12 is not installed." -ForegroundColor Red
                Write-Host "Please install Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Red
                exit 1
            }
        }
    } catch {
        try {
            # Last resort, try python
            $pythonVersion = (python --version 2>&1)
            if ($pythonVersion -match "Python 3.12") {
                $PYTHON = "python"
            } else {
                # Python exists but not 3.12
                if ($pythonVersion -match "Python 3") {
                    Write-Host "Warning: Python 3.12 not found. Using $pythonVersion" -ForegroundColor Yellow
                    Write-Host "For best compatibility, consider installing Python 3.12." -ForegroundColor Yellow
                    $PYTHON = "python"
                } else {
                    Write-Host "Error: Python 3 is required but not found." -ForegroundColor Red
                    Write-Host "Please install Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Red
                    exit 1
                }
            }
        } catch {
            Write-Host "Error: Python is not installed." -ForegroundColor Red
            Write-Host "Please install Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host "Using $PYTHON ($pythonVersion)" -ForegroundColor Green

# Check for pip
try {
    & $PYTHON -m pip --version | Out-Null
} catch {
    Write-Host "Error: pip is not installed for $PYTHON." -ForegroundColor Red
    Write-Host "Please install pip for Python 3.12." -ForegroundColor Red
    exit 1
}

# Check for virtualenv
Write-Host "Checking for virtualenv..." -ForegroundColor Cyan
$hasVirtualenv = & $PYTHON -m pip list | Select-String -Pattern "virtualenv"
if (-not $hasVirtualenv) {
    Write-Host "Installing virtualenv..." -ForegroundColor Cyan
    & $PYTHON -m pip install virtualenv
}

# Create virtual environment if it doesn't exist
if (-not (Test-Path $VENV_DIR)) {
    Write-Host "Creating virtual environment in $VENV_DIR directory with $PYTHON..." -ForegroundColor Cyan
    & $PYTHON -m virtualenv $VENV_DIR
} else {
    Write-Host "Virtual environment already exists in $VENV_DIR." -ForegroundColor Yellow
    Write-Host "To recreate it with Python 3.12, delete the directory first and run this script again." -ForegroundColor Yellow
}

# Activate the virtual environment and install dependencies
Write-Host "Activating virtual environment and installing dependencies..." -ForegroundColor Cyan

# Activate virtual environment
$activateScript = Join-Path -Path $VENV_DIR -ChildPath "Scripts\activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
} else {
    Write-Host "Error: Unable to find activation script at $activateScript." -ForegroundColor Red
    exit 1
}

# Install requirements
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Cyan
& $PYTHON -m pip install -r requirements.txt

# Install package in development mode
Write-Host "Installing FilePilot package in development mode..." -ForegroundColor Cyan
& $PYTHON -m pip install -e .

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "FilePilot virtual environment setup complete with $pythonVersion!" -ForegroundColor Green
Write-Host "To activate the virtual environment, run:" -ForegroundColor Cyan
Write-Host "  .\$VENV_DIR\Scripts\activate.ps1" -ForegroundColor White
Write-Host ""
Write-Host "To run FilePilot with GUI:" -ForegroundColor Cyan
Write-Host "  filepilot" -ForegroundColor White
Write-Host "Or:" -ForegroundColor Cyan
Write-Host "  python -m filepilot.main" -ForegroundColor White
Write-Host ""
Write-Host "To run FilePilot in CLI mode:" -ForegroundColor Cyan
Write-Host "  filepilot --cli --help" -ForegroundColor White
Write-Host "=======================================================" -ForegroundColor Green

# Create batch files for easier usage
Write-Host "Creating Windows activation script (activate.bat)..." -ForegroundColor Cyan
@"
@echo off
call %~dp0\$VENV_DIR\Scripts\activate.bat
"@ | Out-File -FilePath "activate.bat" -Encoding ascii

Write-Host "Creating Windows runner script (run_filepilot.bat)..." -ForegroundColor Cyan
@"
@echo off
call %~dp0\$VENV_DIR\Scripts\activate.bat
python -m filepilot.main %*
"@ | Out-File -FilePath "run_filepilot.bat" -Encoding ascii

# Leave the virtual environment active so the user can start using it right away