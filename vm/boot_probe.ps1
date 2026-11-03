# Boot the mkqnximage x86_64 image headless for a fixed time and print the serial console.
param([string]$Image = "C:\Users\dev\Documents\portpilot-work\qnxvm\x86_64", [int]$Seconds = 90)
$out = Join-Path $Image "output"
$log = Join-Path $out "serial.log"
if (Test-Path $log) { Remove-Item $log }
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
$args = @("-smp", "2", "-cpu", "max", "-m", "1G",
          "-drive", "file=$out\disk-qemu.vmdk,if=ide,id=drv0",
          "-kernel", "$out\ifs.bin",
          "-display", "none", "-monitor", "none", "-serial", "file:$log",
          "-object", "rng-builtin,id=rng0", "-device", "virtio-rng-pci,rng=rng0",
          "-no-reboot")
$p = Start-Process -FilePath $qemu -ArgumentList $args -PassThru -WindowStyle Hidden
Start-Sleep -Seconds $Seconds
$alive = -not $p.HasExited
if ($alive) { Stop-Process -Id $p.Id -Force }
"qemu_alive_at_end=$alive exit=$($p.ExitCode)"
if (Test-Path $log) { Get-Content $log -Raw } else { "no serial log" }
