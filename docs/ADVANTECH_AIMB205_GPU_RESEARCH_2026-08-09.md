# AIMB-205 GPU compatibility research — 2026-08-09

## Decision result

**PCIe slot-power compatibility remains unresolved. Do not purchase or install
an RTX 3060 on the strength of the current documentation.**

## Proven by official Advantech sources

The [official AIMB-205 support page](https://www.advantech.com/en-us/support/details/manual?id=1-1DXQYC7)
links the first-edition AIMB-205 user manual dated 2017-09-18.

The [official AIMB-205 user manual](https://advdownload.advantech.com/productfile/Downloadfile4/1-1E13MJV/AIMB-205_User_Manual_Ed.1.pdf)
states that the board has one PCIe x16 slot. It also lists a maximum-load
system power measurement for an i7-7700 with 32 GB of memory. The manual does
not state a 60 W or 75 W slot-power rating, a separate PCIe-slot current limit,
or an approved discrete-GPU power envelope.

The published system measurement cannot safely be converted into a slot-power
rating because the documented test does not identify a discrete add-in GPU.
The existence of a PCIe x16 connector proves interface compatibility only; it
does not prove that this industrial board can safely supply the slot-side power
required by a particular RTX 3060.

## Required evidence before purchase

Obtain written confirmation from Advantech for the exact `AIMB-205G2` revision:

1. Maximum sustained and peak power available through `PCIEX16_1`.
2. Maximum permitted current on the slot's 12 V and 3.3 V rails.
3. Whether a discrete GPU with an external 8-pin connector is supported.
4. Any BIOS revision, PSU, cooling, chassis, or riser restrictions.

After that, verify the exact GPU model's measured slot draw and replace the
current 200 W PSU with an appropriate quality ATX supply before installation.
No purchase, vendor contact, message, or hardware change was authorized or
performed by this research.
