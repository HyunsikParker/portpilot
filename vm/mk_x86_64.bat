@echo off
call C:\Users\dev\qnx800\qnxsdp-env.bat >nul 2>&1
set PATH=C:\Program Files\qemu;%PATH%
cd /d C:\Users\dev\Documents\portpilot-work\qnxvm\x86_64
call C:\Users\dev\qnx800\host\common\bin\mkqnximage.bat --clean --type=qemu --arch=x86_64 --hostname=ppvm --ssh-ident=none --data-size=512 --noprompt > C:\Users\dev\Documents\portpilot-work\qnxvm\mk.log 2>&1
echo mk_exit=%ERRORLEVEL%
