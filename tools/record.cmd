@echo off
rem Records the running game while you film with Right Shift + 1..4 (or vsShot); Enter stops and cuts.
call "%~dp0_py.cmd" record %*
call "%~dp0_pause.cmd"
