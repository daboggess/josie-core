# CHAPTER 17: The Advantech Mini-ITX Industrial Rig

> *"Josie does not live in an anonymous server farm in Virginia. She lives in a hardened, compact, industrial enclosure on an Advantech motherboard sitting right here in the shop. Her physical reality is visible, audible, and grounded."*  
> — Dustin, Infrastructure Review, October 2026

---

## § 17.1 Industrial Hardware vs. Commercial Consumer Silicon

Consumer personal computers are engineered for intermittent operation: gaming for four hours, web browsing, and sleep mode. Their components—motherboards, power delivery phases, and fans—are designed around planned obsolescence and price-sensitive consumer manufacturing tolerances.

For Josie, continuous 24/7 background persistence and autonomous scheduled initiative demanded an industrial foundation. The hardware platform selected was an **Advantech Mini-ITX industrial-grade motherboard**, housed in a ruggedized, vibration-resistant steel chassis.

Advantech is a global leader in embedded and industrial computing. Industrial Mini-ITX boards are manufactured to standards radically different from consumer motherboards:
- **Extended Temperature Tolerances:** Industrial capacitors and solid-state power phases rated for continuous thermal stress.
- **Wide Input Voltage Protection:** Hardware-level voltage regulation and surge suppression to withstand dirty shop power.
- **Hardware Watchdog Timers:** Embedded watchdog circuits capable of automatically rebooting the host machine in the event of an unrecoverable kernel hang or operating-system freeze.
- **Component Longevity:** Guaranteed multi-year parts availability and long-life manufacturing lifecycles.

---

## § 17.2 The Mini-ITX Compact Footprint

The choice of the Mini-ITX form factor was intentional. An industrial Mini-ITX chassis measures roughly the size of a standard shoebox. It can be mounted under a workbench, inside a secure shop cabinet, or on an equipment rack without dominating physical space or demanding dedicated server-room cooling infrastructure.

```
       +-----------------------------------------------+
       |             ADVANTECH MINI-ITX RIG            |
       |  +-----------------------+  +---------------+ |
       |  | Industrial Motherboard|  | 12GB GPU      | |
       |  | Core CPU / Solid VRMs |  | Dedicated Air | |
       |  +-----------------------+  +---------------+ |
       |  +-----------------------+  +---------------+ |
       |  | NVMe M.2 Vault Drives |  | Industrial PSU| |
       |  | High-Endurance Flash  |  | Low Ripple DC | |
       |  +-----------------------+  +---------------+ |
       +-----------------------------------------------+
```

The compact footprint enforces discipline. One cannot simply install four dual-slot consumer GPUs into a Mini-ITX rig. The physical form factor imposes an absolute hardware boundary: exactly **one** discrete graphics card. This constraint served as the mother of architectural ingenuity, forcing the development of sequential model swapping, quantization mastery, and strict memory budgeting.

---

## § 17.3 Thermal Dissipation and Acoustic Stewardship

Data centers achieve cooling through deafening high-RPM server fans screaming at 80 decibels. An industrial assistant operating in a shop or home office environment must respect acoustic boundaries. Josie cannot sound like a jet engine preparing for takeoff.

The Advantech rig relies on high-efficiency, large-diameter industrial static-pressure fans operating on custom PWM fan curves:
- **Baseline Idle State:** 25–30 decibels (nearly silent ambient operation during daemon polling, SQLite ledger queries, and background health checks).
- **Inference Burst State:** 40–48 decibels (controlled airflow during local model generation, with rapid thermal dissipation bringing temperatures back to idle within 45 seconds of completion).

Thermal management is tracked as an operational health metric. If the GPU core temperature exceeds 78°C or the junction temperature approaches 90°C, the system triggers automatic throttling and defers non-critical background jobs until thermal equilibrium is restored.

---

## § 17.4 Physical Resilience and Power Conditioning

A local AI server is only as resilient as its electrical supply. In an industrial or shop environment, heavy machinery, welders, and power tools can cause voltage sags, brownouts, and electromagnetic spikes.

The Advantech rig is protected by a multi-stage electrical defense:
1. **True Online Double-Conversion UPS:** Incoming AC line power is continuously converted to DC to charge battery cells, and then inverted back into a pure, noiseless sine wave for the Advantech power supply. Zero transfer time occurs during a blackout.
2. **Deterministic Shutdown Signaling:** The UPS is connected via USB signaling to the host operating system. If utility power is lost and battery capacity drops below 30%, the system initiates a graceful shutdown sequence: active inference is halted, SQLite transactions are cleanly committed, WAL checkpoints are flushed to disk, and the OS halts safely.
3. **Automated Power-On Recovery:** BIOS configuration on the Advantech board is set to `Restore AC Power Loss: Always On`. When utility power returns and the UPS stabilizes, the rig cold-boots automatically and launches its health gates.
