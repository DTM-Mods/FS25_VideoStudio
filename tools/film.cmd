@echo off
rem Starts the game with a savegame, films a plan, cuts the clips (and with --make the video).
rem   film.cmd 1 --plan showcase --target "Tiger" --make
rem   film.cmd                      lists the saves and plans and asks
setlocal
if not "%~1"=="" goto direct
call "%~dp0_py.cmd" saves
echo.
call "%~dp0_py.cmd" plans
echo.
set /p "SAVE=Savegame number: "
if not defined SAVE exit /b 1
set /p "PLAN=Plan [showcase]: "
if not defined PLAN set "PLAN=showcase"
set /p "TARGET=What to film, part of its name [what you stand next to]: "
set "VS_TARGET="
if defined TARGET set VS_TARGET=--target "%TARGET%"
call "%~dp0_py.cmd" run %SAVE% --plan %PLAN% %VS_TARGET% --make
call "%~dp0_pause.cmd"
exit /b
:direct
call "%~dp0_py.cmd" run %*
exit /b %ERRORLEVEL%
