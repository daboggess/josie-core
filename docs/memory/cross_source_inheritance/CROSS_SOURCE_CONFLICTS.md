# Cross-Source Conflicts & Temporal Evolutions

This document catalogs instances where evidence from ChatGPT and Gemini shows differing facts, polarity conflicts, or temporal evolutions over time.

---

## 1. Temporal Evolutions (Legitimate State Changes Over Time)

### Conflict / Update 01: Mobile Device Progression
- **ChatGPT Evidence (2025 – Early 2026):**  
  Dustin references his daily mobile device as a **Samsung Galaxy S22 Ultra**.
- **Gemini Evidence (August 2026):**  
  Dustin states: *"Samsung Galaxy S26 Ultra"* (Unit 19, Conv 928, Msg 4784).
- **Resolution:** This is a chronological hardware upgrade, not a factual dispute. S22 Ultra should be routed to `historical_only`, while S26 Ultra represents the latest point-in-time state.

### Conflict / Update 02: Host CPU & RAM Evolution
- **ChatGPT Early Evidence (2025):**  
  Early conversations refer to an older i3 / i5 desktop setup and exploring motherboard options.
- **ChatGPT & Gemini Late Evidence (August 2026):**  
  Both corpora independently state: *"We upgraded to i7 7700 and 32g ram"*.
- **Resolution:** Corroborated temporal milestone. Early CPU configurations are historical; i7-7700 with 32GB RAM is current state.

---

## 2. Hardware Availability & Purchase Tactics

### Conflict / Update 03: RTX 3060 Status
- **ChatGPT Evidence (Early August 2026):**  
  Dustin considers buying an RTX 3060 and asks about power requirements on the Advantech board.
- **Gemini Evidence (August 25, 2026):**  
  Dustin states: *"well that 3060 sold as i was chatting with the guy, wasnt meant to be"* (Msg 5097).
- **Resolution:** Proves that the RTX 3060 was NOT purchased. The candidate claim `does_not_own: RTX 3060` is correct and should NOT be asserted as owned hardware.
