@echo off
rem Pauses only when the shortcut was double-clicked: Explorer runs cmd /c ""x.cmd" " (trailing space),
rem a terminal runs cmd /c ""x.cmd"" or nothing at all.
set "VS_CL=%CMDCMDLINE:"=%"
if "%VS_CL:~-1%"==" " pause
