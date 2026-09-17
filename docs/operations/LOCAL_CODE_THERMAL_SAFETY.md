# Local-code GPU thermal safety

Josie's bounded local-code adapter reads its unattended thermal profile from
`config/local-code-thermal.json`. This guard applies only to `Delegate Local:` and
`Delegate Local Code:` jobs. It does not shut down Windows, alter GPU settings, or
change ordinary chat or Codex delegation.

The adapter resolves `nvidia-smi.exe` from Windows System32 first and queries GPU 0
with CSV output:

```text
nvidia-smi.exe --id=0 --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits
```

The initial profile warns at 70 C, refuses new jobs at 75 C, and terminates an
active job after two samples at or above 82 C. Samples are ten seconds apart. A
reading at or below 79 C resets the sustained-temperature counter, providing 3 C
of hysteresis. A critical 90 C sample terminates immediately. Two consecutive
telemetry failures during a job terminate it; unavailable preflight telemetry
refuses the job before OpenCode starts.

NVIDIA driver 616.56 reported a target temperature of 83 C, maximum operating
temperature 93 C, slowdown temperature 95 C, and shutdown temperature 98 C for
the installed RTX 3060 on 2026-09-01. The configured intervention points do not
modify those driver limits and remain below the reported operating limit.
