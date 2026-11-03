@echo off
call C:\Users\dev\qnx800\qnxsdp-env.bat >nul 2>&1
set PATH=C:\Program Files\qemu;%PATH%
cd /d C:\Users\dev\Documents\portpilot-work\qnxvm\aarch64le
call C:\Users\dev\qnx800\host\common\bin\mkqnximage.bat --clean --force --type=qemu --arch=aarch64le --hostname=ppvm --ssh-ident=none --data-size=512 --noprompt > C:\Users\dev\Documents\portpilot-work\qnxvm\mk_aarch64le.log 2>&1
echo mk_exit=%ERRORLEVEL%
