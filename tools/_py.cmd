@echo off
rem Runs fs25_video.py with py, or python if there is no py; --test: the offline tests.
set "VS_DIR=%~dp0"
where py >nul 2>&1 && set "VS_PY=py -3" || set "VS_PY=python"
if "%~1"=="--test" goto test
%VS_PY% "%VS_DIR%fs25_video.py" %*
exit /b
:test
set "VS_RC=0"
for %%t in (test_video_studio test_tools test_pipeline) do (
  echo === %%t
  %VS_PY% "%VS_DIR%..\tests\%%t.py" || set "VS_RC=1"
  echo.
)
exit /b %VS_RC%
