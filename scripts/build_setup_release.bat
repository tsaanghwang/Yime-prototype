@echo off
setlocal
>&2 echo Obsolete workflow blocked in this detached maintenance repository: Setup.exe product build.
>&2 echo Run product build and release work in C:\dev\Yime. See docs\DETACHED_MAINTENANCE_BOUNDARY.md.
exit /b 2
