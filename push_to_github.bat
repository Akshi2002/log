@echo off
echo === Pushing to GitHub ===
echo Repository: https://github.com/Akshi2002/log.git
echo.

echo Checking git status...
git status
echo.

echo Adding all changes...
git add .
echo.

echo Committing changes...
git commit -m "Add Firebase Authentication, OTP verification, and WFH confirmation flow

- Implemented Firebase Authentication for login
- Added email OTP verification for employee signup  
- Removed password change functionality (handled by Firebase)
- Added WFH confirmation flow requiring employee checkbox
- Updated login flow to remove geofence check (only for attendance sign-in)
- Added SMTP configuration for OTP emails
- Fixed indentation errors"
echo.

echo Setting remote URL...
git remote set-url origin https://github.com/Akshi2002/log.git
echo.

echo Pushing to GitHub...
git push -u origin main
echo.

if %errorlevel% equ 0 (
    echo Successfully pushed to GitHub!
    echo Repository: https://github.com/Akshi2002/log
) else (
    echo Push failed. Please check your Git configuration and authentication.
    echo You may need to use GitHub Desktop or authenticate with GitHub.
)

pause


