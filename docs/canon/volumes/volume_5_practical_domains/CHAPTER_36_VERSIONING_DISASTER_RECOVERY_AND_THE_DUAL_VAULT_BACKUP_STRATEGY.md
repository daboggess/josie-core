# CHAPTER 36: Versioning, Disaster Recovery, and the Dual-Vault Backup Strategy

> *"If a fire sweeps through the shop tomorrow, or an electrical surge destroys the motherboard, can Josie be resurrected in thirty minutes on fresh hardware? If not, you do not have a persistent system; you have a fragile temporary artifact."*  
> — Disaster Recovery Mandate (`DEC-0028`)

---

## § 36.1 The Reality of Hardware Mortality

Physical hardware is mortal. Solid-state drives suffer NAND cell wear and sudden controller death; power supplies fail; lightning storms induce devastating voltage spikes; fire and water hazards exist in any physical building.

A sovereign local architecture that does not possess an automated, disaster-tested recovery strategy is living on borrowed time. Project Josie treats **Disaster Recovery** not as an afterthought, but as a foundational pillar of constant persistence.

---

## § 36.2 The Dual-Vault Backup Architecture

Under **Decision `DEC-0028`**, Josie’s memory and operational state are protected via a **Dual-Vault Backup Strategy**:

```
           [ LIVE RIG: Advantech Mini-ITX ]
             data/josie.db + git repository
                          |
             [ Hourly SQLite Online Backup ]
                          |
                          v
         +----------------------------------+
         |      PRIMARY LOCAL VAULT         |
         | Dedicated Secondary NVMe Drive   |
         | Daily Full Snapshot + WAL Dumps  |
         +----------------------------------+
                          |
             [ Encrypted Restic / Borg ]
                          |
                          v
         +----------------------------------+
         |     OFFSITE COLD STORAGE VAULT   |
         | End-to-End Encrypted Cloud / NAS |
         | Zero-Knowledge Cryptographic Key |
         +----------------------------------+
```

### 1. Primary Local Vault (High-Speed Recovery)
- Located on a physically separate, high-endurance secondary NVMe drive inside the chassis.
- Uses SQLite’s native online backup API (`sqlite3_backup_init`) to capture atomic, transactionally clean snapshots without interrupting active operations or locking writers.
- Retains 24 hourly snapshots and 7 daily snapshots. In the event of software corruption or accidental deletion, recovery time objective (RTO) is under **60 seconds**.

### 2. Offsite Cold Storage Vault (Catastrophic Recovery)
- Every night at 02:00 local time, the daily snapshot is compressed, client-side encrypted using AES-256-GCM with a master passphrase known only to Dustin, and synced to offsite storage.
- The offsite target possesses zero read permissions or cryptographic keys to decrypt the vault. Even in the event of an offsite storage provider breach, Josie’s canonical memory remains completely secure.

---

## § 36.3 The 30-Minute Bare-Metal Resurrection Drill

A backup plan that has never been tested is not a plan; it is a superstition.

In periodic disaster drills, Dustin executes the **Bare-Metal Resurrection Protocol**:
1. Take a completely unformatted, blank computer with an NVIDIA GPU.
2. Install the base operating system from a standard bootable USB.
3. Clone the core repository from git.
4. Restore the latest encrypted snapshot from the Cold Storage Vault.
5. Execute `python -m josie.core.bootstrap`.
6. Verify that Startup Gate 1 through Gate 5 pass cleanly.

In verified drill receipts, total elapsed time from blank drive to fully functional, historically intact Josie operational readiness was **24 minutes and 18 seconds**. 

Her identity, her memory, her boundaries, and her relationship with her wielder survive the physical death of any single machine. That is true persistence.
