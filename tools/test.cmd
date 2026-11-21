@echo off
rem The offline tests: the mod (needs Python lupa), the tools, the whole edit (needs ffmpeg; heavy, not while you play).
setlocal
call "%~dp0_py.cmd" --test
set "RC=%ERRORLEVEL%"
call "%~dp0_pause.cmd"
exit /b %RC%
