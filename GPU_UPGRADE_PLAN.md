# Future EVGA RTX 3060 12GB upgrade plan

**Plan only. No step below was executed during this documentation pass.** Native Windows Ollama is the current inference server; there is no Linux NVIDIA/container stack to install for it.

## Gate 1 — resolve physical unknowns

- [ ] Confirm the card's exact EVGA part number and that it is the **12GB** RTX 3060, not a similarly named variant.
- [ ] Dustin confirms the current board is Advantech Mini-ITX with SO-DIMMs, not the older micro-ATX reference. Photograph/read its exact model/revision and BIOS screen. OS SKYBAY/default strings and historical AIMB-205G2 BIOS notes do not identify it. Exact board/slot/firmware compatibility: **PHYSICAL VERIFICATION REQUIRED**.
- [ ] Verify the exact card manual's minimum PSU recommendation, connector requirement, dimensions and slot clearance against the installed system. The **200 W PSU** is a historical/original reference, not proof of the current installed or intended PSU. Current PSU model/wattage and required PCIe GPU connector: **PHYSICAL VERIFICATION REQUIRED**. Do not clear readiness from documentation alone.
- [ ] Confirm a suitable PCIe slot, bracket clearance, airflow and supported card weight. Do not force the card into an obstructed slot.
- [ ] Use the correct PSU-provided PCIe power cable (6+2-pin when appropriate for the actual card), not CPU/EPS. Never mix modular PSU cables from different units. Do not improvise SATA/Molex adapters or open the PSU.
- [ ] Stop for Dustin's decision if a PSU/case/board change is required; that is separate work, not part of this plan's authorization.

The exact EVGA SKU is not presently verified, so no SKU-specific wattage/clearance claim is being invented.

## Gate 2 — preserve the known working stack

- [ ] Complete [BACKUP_CHECKLIST.md](BACKUP_CHECKLIST.md), including current full-service recovery and independent copy.
- [ ] Review Git status and preserve the pre-existing Compose/phone-proof changes.
- [ ] Verify the [doctor](RUNBOOK.md) and full suite; keep [PRE_GPU_BASELINE.md](PRE_GPU_BASELINE.md) unchanged.
- [ ] Confirm sufficient C: headroom for driver staging/recovery; do not delete Docker data to free space.
- [ ] Record current display driver, BIOS settings and a working integrated-graphics display connection.
- [ ] Confirm local administrator/recovery access and Windows restore/recovery media. If device encryption is enabled, secure its recovery key privately.
- [ ] Save active work, finish jobs/backups, gracefully shut down the stack and Windows.

Do not combine this upgrade with WebUI/Ollama updates, model changes, history import, startup redesign or network-policy changes. That would destroy a clean before/after comparison.

## Gate 3 — physical installation, attended

With Windows shut down, power disconnected and appropriate anti-static precautions, install/secure the card and the correct PCIe power connection according to its manual. Check that cables cannot touch fans. Preserve the known working iGPU display route for recovery.

Boot without changing unrelated firmware settings. Observe POST and Windows device detection. Do not flash BIOS or change CSM, Secure Boot, storage mode, primary display, Above 4G or ReBAR merely because a generic guide suggests it. Older attended notes are historical evidence, not proof of current settings. If detection requires firmware changes, stop and make a separately reviewed, reversible plan for this exact board.

Windows detection (read-only):

```powershell
Get-CimInstance Win32_VideoController |
    Select-Object Name,Status,DriverVersion,PNPDeviceID
Get-PnpDevice -Class Display | Select-Object Status,FriendlyName,InstanceId
```

Linux lspci/systemd/apt instructions are **not applicable** to this native Windows deployment. Do not install Linux GPU drivers into Docker Desktop's managed WSL distribution.

## Gate 4 — Windows driver plan, only after explicit go-ahead

1. Recheck the official NVIDIA selector for the exact GeForce RTX 3060 and Windows 11 64-bit. Choose a currently supported signed/WHQL driver; record exact version, installer source and installation time. Do not use third-party driver sites or silently auto-update the rest of the stack. [NVIDIA official drivers](https://www.nvidia.com/en-us/drivers/)
2. Recheck Ollama's Windows requirements at installation time. The documentation reviewed for this plan specifies NVIDIA 551.61 or newer and native Windows GPU support. The existing standalone Ollama distribution includes NVIDIA runtime libraries. Keep the current Ollama installation/model store for the first comparison; do not install a second copy. [Ollama Windows documentation](https://docs.ollama.com/windows)
3. Create/verify the approved Windows recovery point/image, install the reviewed driver, reboot when requested, then return through the documented startup sequence. Docker may still require manual launch.
4. Do **not** install the CUDA Toolkit by default. This is an inference deployment, not CUDA development. Add another runtime/toolkit only if actual logs establish a missing requirement and Dustin separately approves it.
5. RTX 3060 appears in Ollama's supported NVIDIA hardware list; this is compatibility guidance, not proof that this particular machine is electrically/physically ready. [Ollama hardware support](https://docs.ollama.com/gpu)

## Gate 5 — device, driver, VRAM and inference validation

After driver installation, read-only commands:

```powershell
nvidia-smi
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,temperature.gpu,power.draw --format=csv
& 'D:/Josie-Storage/apps/Ollama/0.32.5/ollama.exe' --version
& 'D:/Josie-Storage/apps/Ollama/0.32.5/ollama.exe' ps
& 'C:/Program Files/Git/bin/bash.exe' C:/Josie/josie-doctor.sh
```

If nvidia-smi is not on PATH, inspect the actual installed location; do not “fix” it by downloading random binaries. Confirm the reported GPU is RTX 3060 and total memory is approximately 12 GiB (typically around 12,288 MiB; small reservations may apply). A driver installed successfully is not yet proof of Ollama offload.

The CUDA version shown by nvidia-smi is driver capability, not proof a CUDA development toolkit is installed. Preserve its output alongside the driver version. [NVIDIA nvidia-smi documentation](https://docs.nvidia.com/deploy/nvidia-smi/index.html)

With no active jobs or resident models, run the **same** bounded benchmark:

```powershell
Set-Location C:/Josie
.venv/Scripts/python.exe -B scripts/measure_pre_gpu.py --run
& 'D:/Josie-Storage/apps/Ollama/0.32.5/ollama.exe' ps
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,power.draw --format=csv
```

Verify Ollama reports GPU residency/offload (size_vram greater than zero), not merely that Windows sees the card. Save results in a separate POST_GPU report, preserving original model digest/options/version. Record:

- first content latency, total wall time, generation tokens/s;
- host RAM/CPU, pagefile changes and model VRAM;
- idle/during/after GPU temperature and power where available;
- driver/device identity, errors, and any different software versions.

For during-inference telemetry, an attended second terminal can run the same nvidia-smi query with -l 1, stopped with Ctrl+C afterward. Do not start a long stress campaign or an 8B delegation benchmark before the small repeatable test passes.

## Gate 6 — stability and acceptance

- [ ] Recheck WebUI desktop and private phone access; ordinary local chat and existing tools remain available.
- [ ] Review recent Ollama/Docker logs and Windows Display/WHEA events locally; redact private content before sharing.
- [ ] Look for driver resets, CUDA allocation failures, unexpected CPU fallback, thermal throttling, artifacts or power shutdowns.
- [ ] Compare temperatures against the actual card's published limits; no current temperature baseline was available.
- [ ] If power faults, overheating, burning smell or repeated resets occur, stop workloads and shut down safely. Do not repeatedly retry under load.
- [ ] Run the full Josie suite and doctor. Record remaining warnings rather than hiding them.
- [ ] Only then create a separate post-GPU commit/report/recovery checkpoint. Model/context optimization is a later task.

## Rollback if detection/driver installation breaks operation

1. Stop GPU workloads; preserve logs and the exact driver version. Do not reset Docker, delete databases or reinstall Josie.
2. Use the retained iGPU display path/local console. If normal boot fails, use Windows recovery/Safe Mode and the prepared recovery strategy.
3. Device Manager → Display adapters → affected NVIDIA device → Properties → Driver → Roll Back Driver, **if a previous driver exists**. A first NVIDIA installation may have no rollback target; use the approved restore point or a reviewed removal of only the newly introduced NVIDIA driver. Do not remove Intel graphics blindly. [Microsoft driver rollback guidance](https://support.microsoft.com/en-us/windows/update-drivers-through-device-manager-in-windows-ec62f46c-ff14-c91d-eead-d7126dc1f7b6)
4. If hardware must be removed, power down/disconnect first and restore the known physical/iGPU configuration. Do not clear BIOS defaults indiscriminately.
5. Start the existing native services/Docker through [RUNBOOK.md](RUNBOOK.md), then confirm CPU-only local chat and data integrity. Preserve all history.
6. Production data restore is only for actual data damage, separately approved and validated in isolation; a display-driver failure is not a reason to overwrite chats.

**Current decision:** software baseline prepared; installation is on hold pending physical power/fit verification and current full-service recovery coverage.
