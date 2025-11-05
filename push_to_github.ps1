# PowerShell script to push changes to GitHub
# Repository: https://github.com/Akshi2002/log.git

Write-Host "=== Pushing to GitHub ===" -ForegroundColor Green

# Check if git is available
$gitPath = $null
$possiblePaths = @(
    "git",
    "C:\Program Files\Git\bin\git.exe",
    "C:\Program Files (x86)\Git\bin\git.exe",
    "$env:LOCALAPPDATA\Programs\Git\bin\git.exe"
)

foreach ($path in $possiblePaths) {
    try {
        if ($path -eq "git") {
            $result = Get-Command git -ErrorAction SilentlyContinue
            if ($result) {
                $gitPath = "git"
                break
            }
        } else {
            if (Test-Path $path) {
                $gitPath = $path
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $gitPath) {
    Write-Host "ERROR: Git not found. Please install Git from https://git-scm.com/download/win" -ForegroundColor Red
    Write-Host "Or use GitHub Desktop or VS Code to push your changes." -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Git: $gitPath" -ForegroundColor Cyan

# Check if remote exists
Write-Host "`nChecking remote configuration..." -ForegroundColor Yellow
& $gitPath remote -v

# Add remote if it doesn't exist
$remoteExists = & $gitPath remote | Select-String -Pattern "origin"
if (-not $remoteExists) {
    Write-Host "`nAdding remote origin..." -ForegroundColor Yellow
    & $gitPath remote add origin https://github.com/Akshi2002/log.git
}

# Set remote URL (in case it's different)
Write-Host "`nSetting remote URL..." -ForegroundColor Yellow
& $gitPath remote set-url origin https://github.com/Akshi2002/log.git

# Check status
Write-Host "`nChecking git status..." -ForegroundColor Yellow
& $gitPath status

# Add all files
Write-Host "`nAdding all changes..." -ForegroundColor Yellow
& $gitPath add .

# Commit changes
Write-Host "`nCommitting changes..." -ForegroundColor Yellow
$commitMessage = "Add Firebase Authentication, OTP verification, and WFH confirmation flow

- Implemented Firebase Authentication for login
- Added email OTP verification for employee signup
- Removed password change functionality (handled by Firebase)
- Added WFH confirmation flow requiring employee checkbox
- Updated login flow to remove geofence check (only for attendance sign-in)
- Added SMTP configuration for OTP emails
- Fixed indentation errors"

& $gitPath commit -m $commitMessage

# Push to GitHub
Write-Host "`nPushing to GitHub..." -ForegroundColor Yellow
& $gitPath push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Successfully pushed to GitHub!" -ForegroundColor Green
    Write-Host "Repository: https://github.com/Akshi2002/log" -ForegroundColor Cyan
} else {
    Write-Host "`n❌ Push failed. You may need to:" -ForegroundColor Red
    Write-Host "1. Check your internet connection" -ForegroundColor Yellow
    Write-Host "2. Authenticate with GitHub (use GitHub Desktop or VS Code)" -ForegroundColor Yellow
    Write-Host "3. Or run: git push -u origin main" -ForegroundColor Yellow
}


