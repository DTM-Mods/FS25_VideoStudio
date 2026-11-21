@echo off
rem Makes the finished video from a clips folder: make.cmd "<clips folder>" [--style cinematic] [--shorts]
setlocal
set "CLIPS=%~1"
if not defined CLIPS set /p "CLIPS=Clips folder (drag it here): "
if not defined CLIPS exit /b 1
shift
set "VS_ARGS="
:collect
if "%~1"=="" goto go
set VS_ARGS=%VS_ARGS% %1
shift
goto collect
:go
call "%~dp0_py.cmd" make "%CLIPS%" %VS_ARGS%
call "%~dp0_pause.cmd"
