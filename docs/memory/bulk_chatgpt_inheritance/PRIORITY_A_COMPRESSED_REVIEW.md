# Priority-A Compressed Review Packet: Semantic Families

**Milestone:** Post-Bulk ChatGPT Candidate Claim Consolidation  
**Total Raw Priority-A Candidate Claims:** 254  
**Total Semantic Families:** 47 (across 11 domains)  
**Human Adjudication Authority:** Dustin (Sole Authority)  
**Target DB:** `data/josie.db` (`memory_claims`)  
**Canonical Status:** Immutable 10 Canonical Claims (Zero automatic promotions)  

---

## Executive Summary

This document compresses the **254 raw Priority-A candidate claims** staged from historical ChatGPT conversations into **47 structured semantic families** organized across 11 life and architectural domains. Every single source claim ID, message pointer, and verbatim provenance is retained without destructive modification. Constituent claims are classified by relationship (corroborating, refining, temporal update, or distinct), providing Dustin with high-fidelity semantic summaries for efficient human review.

---

## Domain 01: Identity, Residence & Stature

### Family 01.1: Residence & Farm Heritage in Buffalo, Putnam County, WV

**Proposed Consolidated Memory:**  
> *"Dustin resides in Buffalo, West Virginia, and has lived on a farm in Putnam County his entire life."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:lived_on_a_farm_in_putnam_county:a7b43026c5d169bb, claim:candidate:person:dustin:residence_location:fa6f2ad8d579fbf2`
- **Evidence Strength:** 2 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2025-08-14 to 2026-03-09
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:lived_on_a_farm_in_putnam_county:a7b43026c5d169bb` | `lived_on_a_farm_in_putnam_county` | `profile` | `durable` | my entire life |
| `claim:candidate:person:dustin:residence_location:fa6f2ad8d579fbf2` | `residence_location` | `identity` | `durable` | Buffalo, WV |

**Representative Source Evidence:**
- *"I have lived on a farm in Putnam County my entire life."*
- *"I have owned full steam vapor for 11 years, done business in the local community, managed a successful business that has done over 1.3 million in sales in 20..."*

---

### Family 01.2: Legal Name & Personal Identity (Dustin Boggess)

**Proposed Consolidated Memory:**  
> *"Dustin Boggess is the primary user and head of his household."*

- **Supporting Candidates (3):** `claim:candidate:person:dustin:has_identity:22a9cd4d8ea1f55c, claim:candidate:person:dustin:has_identity:fa012c86a0e3f857, claim:candidate:person:dustin:is_named:fa012c86a0e3f857`
- **Evidence Strength:** 3 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2025-09-30 to 2025-12-01
- **Relationship:** `corroborates canonical`
- **Recommendation:** `MERGE/CORROBORATE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_identity:22a9cd4d8ea1f55c` | `has_identity` | `identity` | `durable` | Dustin |
| `claim:candidate:person:dustin:has_identity:fa012c86a0e3f857` | `has_identity` | `identity` | `durable` | Dustin Boggess |
| `claim:candidate:person:dustin:is_named:fa012c86a0e3f857` | `is_named` | `identity` | `durable` | Dustin Boggess |

**Representative Source Evidence:**
- *"My name's Dustin, but it feels like you're calling me your name."*
- *"My name is Dustin Boggess, and I was saved when I was 12, and I never got baptized, and I always felt like it was something I was commanded to do that I had ..."*

---

### Family 01.3: Personal Interests & Flash-Themed Cultural Affinity

**Proposed Consolidated Memory:**  
> *"Dustin has a personal affinity for 'The Flash' superhero motif, incorporating it into personal accessories (wedding band, wallet, watch face)."*

- **Supporting Candidates (1):** `claim:candidate:person:dustin:has_preference:b7da2917985104f6`
- **Evidence Strength:** 1 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2025-12-14
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_preference:b7da2917985104f6` | `has_preference` | `preference` | `durable` | being a Flash nerd with Flash-themed items (wedding band, wallet, watch face) |

**Representative Source Evidence:**
- *"And im a huge flash nerd. I have a flash wedding band, wallet, watch face....... big flash geek"*

---

### Family 01.4: Physical Stature (6'4", 260 lbs) & Defensive Martial Training

**Proposed Consolidated Memory:**  
> *"Dustin is 6'4" and approximately 260 lbs, with a background in competitive wrestling, kickboxing, Brazilian jiu-jitsu, firearms proficiency, and defensive training alongside law enforcement and military personnel."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_physical_attributes:0f44bdda3e10ce19, claim:candidate:person:dustin:has_physical_attributes_and_training:23dfb025fdc58a0f`
- **Evidence Strength:** 2 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2026-05-06 to 2026-05-10
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_physical_attributes:0f44bdda3e10ce19` | `has_physical_attributes` | `identity` | `durable` | 6'4", 260 lbs, mostly belly |
| `claim:candidate:person:dustin:has_physical_attributes_and_training:23dfb025fdc58a0f` | `has_physical_attributes_and_training` | `profile` | `durable` | 6'4", 260 pounds, wrestled in school, took kickboxing, jiu-jitsu, fairly good... |

**Representative Source Evidence:**
- *"I am 6'4", 260, and mostly, almost all belly, so anything I appendix carry is gonna have to sit below my waistline."*
- *"I'm 6'4", 260 pounds, wrestled in school, took kickboxing, jiu-jitsu, fairly good hand-to-hand, fairly decent with a firearm, you know, trained, range time, ..."*

---

## Domain 02: Health, Medical & Nutrition

### Family 02.1: Hormone Replacement Therapy (TRT) & Metabolic Health (GLP-1)

**Proposed Consolidated Memory:**  
> *"As of 2026, Dustin has been on testosterone replacement therapy (TRT) for approximately two years and administers TRT and GLP-1 (Mounjaro) weekly on Wednesdays to prevent weekend dips."*

- **Supporting Candidates (4):** `claim:candidate:person:dustin:has_preference:5d5d0f61ebec04c5, claim:candidate:person:dustin:has_been_on_trt_for_approximately_2_years:7dab2372ff909b06, claim:candidate:person:dustin:takes_testosterone_and_glp_1s_every_wednesday:23405cbf281eb98f, claim:candidate:person:dustin:has_dietary_constraint:4577faf7b45a5d2b`
- **Evidence Strength:** 4 evidence reference(s) across 4 conversation(s)
- **Temporal Range:** 2025-12-09 to 2026-05-01
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_preference:5d5d0f61ebec04c5` | `has_preference` | `preference` | `preference` | prefers taking medication on Wednesdays to avoid weekend dips |
| `claim:candidate:person:dustin:has_been_on_trt_for_approximately_2_years:7dab2372ff909b06` | `has_been_on_trt_for_approximately_2_years` | `profile` | `durable` | 2 years |
| `claim:candidate:person:dustin:takes_testosterone_and_glp_1s_every_wednesday:23405cbf281eb98f` | `takes_testosterone_and_glp_1s_every_wednesday` | `preference` | `preference` | testosterone and GLP-1s |
| `claim:candidate:person:dustin:has_dietary_constraint:4577faf7b45a5d2b` | `has_dietary_constraint` | `preference` | `preference` | avoids sugar due to intestinal discomfort on Manjaro.glp1 |

**Representative Source Evidence:**
- *"I like wednesday, no weekend dips on either med"*
- *"Maybe 2 years"*

---

### Family 02.2: Red Food Dye Sensitivity & Irritability Response

**Proposed Consolidated Memory:**  
> *"Dustin has an adverse behavioral sensitivity to Red Food Dye (Red #40), which triggers irritability."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_a_preference_for_avoiding_gluten_and_red_dye:54dab9eb6d3204a0, claim:candidate:person:dustin:has_sensitivity_to_red_dye:3ca8182f2731917e`
- **Evidence Strength:** 3 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2026-03-27 to 2026-06-30
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_a_preference_for_avoiding_gluten_and_red_dye:54dab9eb6d3204a0` | `has_a_preference_for_avoiding_gluten_and_red_dye` | `preference` | `durable` | durable |
| `claim:candidate:person:dustin:has_sensitivity_to_red_dye:3ca8182f2731917e` | `has_sensitivity_to_red_dye` | `preference` | `durable` | experiences irritability |

**Representative Source Evidence:**
- *"I haven't had M&Ms in forever because I don't do red dye."*
- *"I've also noticed red dye definitely makes me extremely irritable."*

---

### Family 02.3: Dietary Restrictions (Gluten-Free, Nut Sensitivity, Sugar Avoidance)

**Proposed Consolidated Memory:**  
> *"Dustin maintains a gluten-free diet, avoids tree nuts due to adverse reactions, and minimizes sugar to prevent gastrointestinal discomfort while on GLP-1 medication."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_preference:2bd8759ac3dc6134, claim:candidate:person:dustin:has_dietary_restrictions:a3aad56353df3370`
- **Evidence Strength:** 2 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2026-04-22 to 2026-07-18
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_preference:2bd8759ac3dc6134` | `has_preference` | `preference` | `durable` | avoids soy in protein powders |
| `claim:candidate:person:dustin:has_dietary_restrictions:a3aad56353df3370` | `has_dietary_restrictions` | `preference` | `preference` | gluten-free and cannot consume nuts due to adverse effects |

**Representative Source Evidence:**
- *"I dont like soy either"*
- *"you didn't acknowledge the gluten-free or the fact that I can't eat nuts or they have a horrible effect on my system."*

---

### Family 02.4: Wellness Supplements, Peptide Stacks & Healthcare Savings Strategy

**Proposed Consolidated Memory:**  
> *"Dustin utilizes peptide and wellness supplement stacks sourced from single distributors for metabolic support, while strategically preserving HSA funds for long-term health needs."*

- **Supporting Candidates (5):** `claim:candidate:person:dustin:prefers_to_use_peptides_and_other_supplements_to_aid_weight_loss:0810f2c5496c96b4, claim:candidate:person:dustin:prefers_to_save_hsa_funds_for_future_expenses:add46b607c95230c, claim:candidate:person:dustin:prefers:0a4f33ce715bb313, claim:candidate:person:dustin:prefers:c7efbc5508393e02, claim:candidate:person:dustin:prefers:247d07a7d4436b62`
- **Evidence Strength:** 5 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2026-03-25 to 2026-07-02
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers_to_use_peptides_and_other_supplements_to_aid_weight_loss:0810f2c5496c96b4` | `prefers_to_use_peptides_and_other_supplements_to_aid_weight_loss` | `preference` | `preference` | due to an inability to attend the gym regularly |
| `claim:candidate:person:dustin:prefers_to_save_hsa_funds_for_future_expenses:add46b607c95230c` | `prefers_to_save_hsa_funds_for_future_expenses` | `preference` | `preference` | rather than using them for supplements |
| `claim:candidate:person:dustin:prefers:0a4f33ce715bb313` | `prefers` | `preference` | `preference` | inexpensive but effective stack |
| `claim:candidate:person:dustin:prefers:c7efbc5508393e02` | `prefers` | `preference` | `preference` | ordering all products from one place |
| `claim:candidate:person:dustin:prefers:247d07a7d4436b62` | `prefers` | `preference` | `preference` | two-product stack |

**Representative Source Evidence:**
- *"adding different peptides or other things to supplement my weight loss and push past this plateau since I can't get to a gym to save my life because of my in..."*
- *"I'm trying to save my HSA money for building up for next year and for covering"*

---

### Family 02.5: Daily Nutrition, Morning Coffee Routine & Intermittent Fasting

**Proposed Consolidated Memory:**  
> *"Dustin practices intermittent fasting by postponing meals until around 2:00 PM, relies on simple non-DIY morning coffee (such as Trenta Starbucks with 2 added shots or ultra-filtered milk/protein), and avoids complex morning prep."*

- **Supporting Candidates (5):** `claim:candidate:person:dustin:normally_to_a_trenta_starbucks_with_2_shots:ea10ca71f6d8a4bc, claim:candidate:person:dustin:requires_non_diy_easy_to_use_morning_solutions:3bcf68ff47f613f9, claim:candidate:person:dustin:prefers:2a8142e1c9cd421a, claim:candidate:person:dustin:has_eating_habit:e26e7d13603852b5, claim:candidate:person:dustin:considers_modifying_breakfast:73a23dd58ef5ef91`
- **Evidence Strength:** 5 evidence reference(s) across 4 conversation(s)
- **Temporal Range:** 2025-12-13 to 2026-04-04
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:normally_to_a_trenta_starbucks_with_2_shots:ea10ca71f6d8a4bc` | `normally_to_a_trenta_starbucks_with_2_shots` | `preference` | `durable` | normally to a trenta starbucks with 2 shots |
| `claim:candidate:person:dustin:requires_non_diy_easy_to_use_morning_solutions:3bcf68ff47f613f9` | `requires_non_diy_easy_to_use_morning_solutions` | `preference` | `preference` | no DIY, need easy, mornings too chaotic |
| `claim:candidate:person:dustin:prefers:2a8142e1c9cd421a` | `prefers` | `preference` | `preference` | nicotine pouches with coffee or related flavors |
| `claim:candidate:person:dustin:has_eating_habit:e26e7d13603852b5` | `has_eating_habit` | `preference` | `preference` | waiting until around 2pm to eat |
| `claim:candidate:person:dustin:considers_modifying_breakfast:73a23dd58ef5ef91` | `considers_modifying_breakfast` | `preference` | `preference` | adding protein powder to breakfast |

**Representative Source Evidence:**
- *"I normally to a trenta starbucks with 2 shots"*
- *"No diy, need easy, mornings too chaotic"*

---

### Family 02.6: Personal Care & Grooming Product Preferences

**Proposed Consolidated Memory:**  
> *"Dustin prefers aluminum-free personal care products, specifically using Mando deodorant and soap."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_preference:859edf78a7a4ff25, claim:candidate:person:dustin:has_preference:62bf2200cf8dc80b`
- **Evidence Strength:** 2 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2026-03-28
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_preference:859edf78a7a4ff25` | `has_preference` | `preference` | `durable` | aluminum-free deodorant usage |
| `claim:candidate:person:dustin:has_preference:62bf2200cf8dc80b` | `has_preference` | `preference` | `durable` | Mando deodorant with Mando soap as effective odor solution |

**Representative Source Evidence:**
- *"Ok. I went aluminum free"*
- *"Mando w mando soap has been 100% effective for me"*

---

### Family 02.7: Personal Boundaries, ADHD & Sobriety Conviction

**Proposed Consolidated Memory:**  
> *"Dustin identifies as having an addictive personality and ADHD, maintaining an absolute personal boundary of permanent sobriety from illicit substances."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_preference:9e7e87258a51642e, claim:candidate:person:dustin:has_addictive_personality_and_adhd:b5bea41b6c623f7c`
- **Evidence Strength:** 2 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2026-01-28 to 2026-04-23
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_preference:9e7e87258a51642e` | `has_preference` | `preference` | `durable` | Never uses crack or cocaine again |
| `claim:candidate:person:dustin:has_addictive_personality_and_adhd:b5bea41b6c623f7c` | `has_addictive_personality_and_adhd` | `profile` | `durable` | true |

**Representative Source Evidence:**
- *"I'm never doing crack. I'm never doing cocaine again."*
- *"even though I have an addictive personality, and ADHD, and bad self-governing mechanisms"*

---

## Domain 03: Career & Technical Competencies

### Family 03.2: Field Service Engineering (FSE) Skills & Current Role (Becton Dickinson / HCSIS)

**Proposed Consolidated Memory:**  
> *"Dustin is a Field Service Engineer with hardware-centric IT competencies, currently employed by Becton Dickinson in the HCSIS role."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_professional_background:ea6543ba240540f9, claim:candidate:person:dustin:current_state:f784fa90a10919d4`
- **Evidence Strength:** 2 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2025-08-25 to 2026-03-27
- **Relationship:** `refines canonical`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_professional_background:ea6543ba240540f9` | `has_professional_background` | `profile` | `durable` | field service engineer with moderate network, low coding, moderate software s... |
| `claim:candidate:person:dustin:current_state:f784fa90a10919d4` | `current_state` | `profile` | `durable` | currently employed by Becton Dickinson in the HCSIS role |

**Representative Source Evidence:**
- *"I'm a field service engineer. I work on Salesforce. I have moderate network, low coding, moderate software. I'm mostly a hardware monkey with intelligence fo..."*
- *"I currently work for Becton Dickinson handling HCSIS"*

---

### Family 03.3: Advertising Degree & Formal Communications / Performing Background

**Proposed Consolidated Memory:**  
> *"Dustin holds a Bachelor's degree in Advertising and has a background in competitive speech, debate, drama, and show choir, contributing to strong oral presentation and persuasion capabilities."*

- **Supporting Candidates (1):** `claim:candidate:person:dustin:has_professional_experience:67dfc912a5dabc1e`
- **Evidence Strength:** 2 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2025-12-18
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_professional_experience:67dfc912a5dabc1e` | `has_professional_experience` | `profile` | `durable` | participated in speech and debate, drama, and show choir, leading to a degree... |

**Representative Source Evidence:**
- *"This has crossed my mind, but i have thought what i could do withbthe following i used to have, but that was me as the face of a business or as me selling me"*
- *"I did do those things, i lied, i chased attention, i wanted to be the center, i put myself first in all things and manipulated everyone and everything around..."*

---

### Family 03.4: Enterprise Salesforce Super-User Experience

**Proposed Consolidated Memory:**  
> *"Dustin has enterprise Salesforce administration experience, serving as a super-user reporting directly to subject matter experts."*

- **Supporting Candidates (1):** `claim:candidate:person:dustin:is_a_salesforce_super_user:d53e1d9ec3c49d8f`
- **Evidence Strength:** 1 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2025-08-26
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:is_a_salesforce_super_user:d53e1d9ec3c49d8f` | `is_a_salesforce_super_user` | `profile` | `durable` | reports directly to subject matter experts for Salesforce |

**Representative Source Evidence:**
- *"I'm also a Salesforce super user who reports directly to our subject matter experts for Salesforce."*

---

### Family 03.5: Practical Trades Competence (Low-Voltage Wiring & Small Engine Repair)

**Proposed Consolidated Memory:**  
> *"Dustin possesses hands-on trade proficiencies in low-voltage electrical wiring and small engine mechanical repair."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_low_voltage_experience:8a798890fe938171, claim:candidate:person:dustin:has_proficiency_in:9ef7bd5d2174df1f`
- **Evidence Strength:** 2 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2026-07-25 to 2026-08-06
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_low_voltage_experience:8a798890fe938171` | `has_low_voltage_experience` | `profile` | `durable` | yes |
| `claim:candidate:person:dustin:has_proficiency_in:9ef7bd5d2174df1f` | `has_proficiency_in` | `profile` | `durable` | small engine repair |

**Representative Source Evidence:**
- *"they asked how much like low voltage experience I had, and I kind of told them."*
- *"I mean, I did small engine repair in shop class and was pretty damn good at it."*

---

### Family 03.6: Technical Operations Management & Field Supervisory Leadership

**Proposed Consolidated Memory:**  
> *"Dustin has supervisory and field operations management experience across Kentucky and West Virginia, managing technical contractors and structured preventative maintenance schedules."*

- **Supporting Candidates (3):** `claim:candidate:person:dustin:holds_leadership_role:06925a2cbe52927a, claim:candidate:person:dustin:implements:d81bce5a54c6ce2d, claim:candidate:person:dustin:demonstrates:b531b773ae2fa4bf`
- **Evidence Strength:** 4 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2026-02-11 to 2026-02-24
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:holds_leadership_role:06925a2cbe52927a` | `holds_leadership_role` | `profile` | `durable` | lead/supervisor role over Kentucky and West Virginia |
| `claim:candidate:person:dustin:implements:d81bce5a54c6ce2d` | `implements` | `preference` | `durable` | structured preventative maintenance schedule on Tuesdays and Thursdays |
| `claim:candidate:person:dustin:demonstrates:b531b773ae2fa4bf` | `demonstrates` | `profile` | `durable` | ability to manage contingent worker Harlan effectively |

**Representative Source Evidence:**
- *"Moving into lead/supervisor ish role over ky and wv"*
- *"That's the other thing. I think Bob hasn't called it out directly, but I'm pretty sure he recognizes that that's what I've done because he goes back and look..."*

---

### Family 03.7: Employment History & Pragmatic Workplace Ethics

**Proposed Consolidated Memory:**  
> *"Dustin has prior professional experience in corporate sales, recruiting (Workable), and transportation (Uber), and maintains a pragmatic, clear-eyed workplace ethic prioritizing family time and sustainable boundaries over corporate exploitation."*

- **Supporting Candidates (7):** `claim:candidate:person:dustin:has_professional_background_in_marketing_and_sales:8845237177fe3260, claim:candidate:person:dustin:has_preference:ccf2ad1d300a3cda, claim:candidate:person:dustin:has_preference:d2afa41c8415b665, claim:candidate:person:dustin:has_preference:0511b2c9ffdbf3f5, claim:candidate:person:dustin:has_worked_at:f11f280ef5d87243, claim:candidate:person:dustin:has_a_history_of_adapting_his_personality_in_sales:dd564d5887ad925c` and 1 more...
- **Evidence Strength:** 7 evidence reference(s) across 5 conversation(s)
- **Temporal Range:** 2025-08-31 to 2026-03-15
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_professional_background_in_marketing_and_sales:8845237177fe3260` | `has_professional_background_in_marketing_and_sales` | `profile` | `durable` | marketing and sales |
| `claim:candidate:person:dustin:has_preference:ccf2ad1d300a3cda` | `has_preference` | `preference` | `durable` | Corporate is always going to do whatever it takes to make money and keep inve... |
| `claim:candidate:person:dustin:has_preference:d2afa41c8415b665` | `has_preference` | `preference` | `durable` | Wanting work to suck less and sometimes suck in his favor. |
| `claim:candidate:person:dustin:has_preference:0511b2c9ffdbf3f5` | `has_preference` | `preference` | `durable` | Need to balance not tilting windmills and not rolling over and accepting things. |
| `claim:candidate:person:dustin:has_worked_at:f11f280ef5d87243` | `has_worked_at` | `profile` | `durable` | Uber and Workable |
| `claim:candidate:person:dustin:has_a_history_of_adapting_his_personality_in_sales:dd564d5887ad925c` | `has_a_history_of_adapting_his_personality_in_sales` | `profile` | `durable` | when I was in sales, I had a bad history of lying to people. Not lying about ... |
| `claim:candidate:person:dustin:has_profile:4956a8a3916dc730` | `has_profile` | `profile` | `durable` | has technical experience and marketing background from education/employment |

**Representative Source Evidence:**
- *"my background in education's in marketing and sales, and then I switched over to system"*
- *"corporate is always gonna do whatever they have to to make money and keep investors happy."*

---

## Domain 04: Business & Full Steam Vapor

### Family 04.1: Full Steam Vapor Business Ownership, Operation & E-Liquid Lines

**Proposed Consolidated Memory:**  
> *"Dustin and his wife Jess own and operate Full Steam Vapor, manufacturing proprietary e-liquid lines including Herd, FAD5, and the Full Steam Vapor house line."*

- **Supporting Candidates (3):** `claim:candidate:person:dustin:manufactures:d1bef4fab7e5425c, claim:candidate:person:dustin:operates:58d30c38e373ae45, claim:candidate:person:dustin:owns_business:58d30c38e373ae45`
- **Evidence Strength:** 4 evidence reference(s) across 4 conversation(s)
- **Temporal Range:** 2025-08-14 to 2025-12-21
- **Relationship:** `refines canonical`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:manufactures:d1bef4fab7e5425c` | `manufactures` | `profile` | `durable` | Herd eliquid, FAD5 eliquid, and full steam vapor house line |
| `claim:candidate:person:dustin:operates:58d30c38e373ae45` | `operates` | `identity` | `durable` | Full Steam Vapor |
| `claim:candidate:person:dustin:owns_business:58d30c38e373ae45` | `owns_business` | `profile` | `current_state` | Full Steam Vapor |

**Representative Source Evidence:**
- *"I manufacturer Herd eliquid, FAD5 eliquid and our full steam vapor house line."*
- *"This is for Full Steam vapor"*

---

### Family 04.2: Historical Retail Business Scale ($1.3M Peak / $10M+ Lifetime)

**Proposed Consolidated Memory:**  
> *"Full Steam Vapor grew to a multi-million-dollar retail operation achieving over $1.3 million in revenue in peak year 2021 and over $10 million in lifetime revenue over 11+ years."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:has_business_experience:207c27e76cc544ea, claim:candidate:person:dustin:has_sales_performance:a6e2afdb53fabae8`
- **Evidence Strength:** 2 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2025-08-14 to 2026-04-30
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_business_experience:207c27e76cc544ea` | `has_business_experience` | `profile` | `durable` | Built and ran a multi-million dollar business with $1.3M peak year and $10M+ ... |
| `claim:candidate:person:dustin:has_sales_performance:a6e2afdb53fabae8` | `has_sales_performance` | `profile` | `durable` | over $1.3 million in 2021, over $10 million in 11 years |

**Representative Source Evidence:**
- *"Actually, one year we did $1.3 million in sales. We've done over $10 million year-to-date, and that's over 12 years. Just adding that in."*
- *"I have owned full steam vapor for 11 years, done business in the local community, managed a successful business that has done over 1.3 million in sales in 20..."*

---

### Family 04.3: Entrepreneurial History, Regulatory Advocacy & Retail Longevity

**Proposed Consolidated Memory:**  
> *"Dustin has operated in vape retail since 2014, actively participating in West Virginia Vapor Registry/PMTA compliance, administering a state-level industry advocacy group (980+ members), and previously owned a barbecue restaurant."*

- **Supporting Candidates (9):** `claim:candidate:person:dustin:engages_with:5665e6d263a14c41, claim:candidate:person:dustin:has_been_operating_in_the_vape_retail_industry_since:96da37e95d5cc34f, claim:candidate:person:dustin:seeks_to_expand_business_to:8a01970f37a06957, claim:candidate:person:dustin:has_family_history_involving:a8cb294a068c1fdc, claim:candidate:person:dustin:has_business_license:8a798890fe938171, claim:candidate:person:dustin:operated_a_barbecue_restaurant:b817dd9684065cab` and 3 more...
- **Evidence Strength:** 9 evidence reference(s) across 5 conversation(s)
- **Temporal Range:** 2025-08-20 to 2026-05-27
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:engages_with:5665e6d263a14c41` | `engages_with` | `profile` | `durable` | West Virginia Vapor registry and PMTA registration |
| `claim:candidate:person:dustin:has_been_operating_in_the_vape_retail_industry_since:96da37e95d5cc34f` | `has_been_operating_in_the_vape_retail_industry_since` | `profile` | `durable` | 2014 |
| `claim:candidate:person:dustin:seeks_to_expand_business_to:8a01970f37a06957` | `seeks_to_expand_business_to` | `preference` | `preference` | 10 stores |
| `claim:candidate:person:dustin:has_family_history_involving:a8cb294a068c1fdc` | `has_family_history_involving` | `profile` | `durable` | moonshine production |
| `claim:candidate:person:dustin:has_business_license:8a798890fe938171` | `has_business_license` | `profile` | `durable` | yes |
| `claim:candidate:person:dustin:operated_a_barbecue_restaurant:b817dd9684065cab` | `operated_a_barbecue_restaurant` | `profile` | `durable` | barbecue restaurant |
| `claim:candidate:person:dustin:has_business_ownership_experience:965455023c91f19b` | `has_business_ownership_experience` | `profile` | `current_state` | business owner |
| `claim:candidate:person:dustin:administers:d2df8c95ef367d32` | `administers` | `profile` | `durable` | a state-level advocacy group with 981 members |
| `claim:candidate:person:dustin:operates_business_since:96da37e95d5cc34f` | `operates_business_since` | `profile` | `durable` | 2014 |

**Representative Source Evidence:**
- *"So you know, I own a vape shop and we've been dealing with the West Virginia Vapor registry and the pmta registration and recently a bunch of flavored Vapes ..."*
- *"we got in the business in 2014"*

---

### Family 04.4: Local SEO & Google Business Profile (12-Year Sustained Track Record)

**Proposed Consolidated Memory:**  
> *"Dustin has a 12-year sustained track record of managing Google Business Profiles, achieving top local search rankings, and executing local search engine optimization."*

- **Supporting Candidates (3):** `claim:candidate:person:dustin:has:1921b4a01a94eb7c, claim:candidate:person:dustin:concerns_supplier_reputation:ee0d8e86442e4dce, claim:candidate:person:dustin:has_preference:d72e0eed260e05cd`
- **Evidence Strength:** 5 evidence reference(s) across 3 conversation(s)
- **Temporal Range:** 2025-07-28 to 2026-02-16
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has:1921b4a01a94eb7c` | `has` | `profile` | `durable` | 12-year sustained performance record in Google Business Profile management |
| `claim:candidate:person:dustin:concerns_supplier_reputation:ee0d8e86442e4dce` | `concerns_supplier_reputation` | `preference` | `preference` | expresses concern about supplier reputation when ordering from Alibaba for br... |
| `claim:candidate:person:dustin:has_preference:d72e0eed260e05cd` | `has_preference` | `preference` | `preference` | AI tools for automating workflows, integrating with personal apps (Google Cal... |

**Representative Source Evidence:**
- *"Gbp was over 6 months use as an average for the 12 years"*
- *"Gbp numbers were sep to feb, weve done that or higher for 12 years"*

---

### Family 04.5: Retail Point of Sale (POS) & Storefront Infrastructure

**Proposed Consolidated Memory:**  
> *"Full Steam Vapor utilizes Clover and Lifelong POS systems with integrated payment terminals (PAX Q30) and structured inventory reordering matched to sales velocity."*

- **Supporting Candidates (17):** `claim:candidate:person:dustin:prefers_maximizing_access_without_burning_limits:9eaa5ee271293d27, claim:candidate:person:dustin:has_preference:ebb6aa113a63653c, claim:candidate:person:dustin:prefers:209c20ac53a31d1f, claim:candidate:person:dustin:wants:3f4316a5c7db9acb, claim:candidate:person:dustin:proposes:65bb14dc05eb53f9, claim:candidate:person:dustin:plans_to_use_existing_church_channels_for_promotion:dd9e79a39835d399` and 11 more...
- **Evidence Strength:** 18 evidence reference(s) across 12 conversation(s)
- **Temporal Range:** 2025-07-27 to 2026-08-25
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers_maximizing_access_without_burning_limits:9eaa5ee271293d27` | `prefers_maximizing_access_without_burning_limits` | `preference` | `preference` | want to give Josie as much access to you and Gemini, Bernie as possible witho... |
| `claim:candidate:person:dustin:has_preference:ebb6aa113a63653c` | `has_preference` | `preference` | `preference` | Josie to be as intelligent as possible |
| `claim:candidate:person:dustin:prefers:209c20ac53a31d1f` | `prefers` | `preference` | `preference` | remotely controlled browser sessions to match normal authenticated browser ca... |
| `claim:candidate:person:dustin:wants:3f4316a5c7db9acb` | `wants` | `preference` | `preference` | as much access and independence as possible |
| `claim:candidate:person:dustin:proposes:65bb14dc05eb53f9` | `proposes` | `preference` | `preference` | organizing a men's mixer event with 'Build Fight Win' framing where older men... |
| `claim:candidate:person:dustin:plans_to_use_existing_church_channels_for_promotion:dd9e79a39835d399` | `plans_to_use_existing_church_channels_for_promotion` | `preference` | `preference` | Tom posts bulletins in all the men's room above the urinals |
| `claim:candidate:person:dustin:omitted_measurable_outcomes_from_initial_goals_document:ee8467734cfeaade` | `omitted_measurable_outcomes_from_initial_goals_document` | `preference` | `preference` | to avoid imposing corporate structure on church context |
| `claim:candidate:person:dustin:seeks:e248826ef9435c23` | `seeks` | `preference` | `preference` | shower wand that positively builds pressure |
| `claim:candidate:person:dustin:requires:10767c1ea9b76de7` | `requires` | `preference` | `preference` | pull-out drawers for storage in Subaru Ascent |
| `claim:candidate:person:dustin:requires:da20c25abdfc02ed` | `requires` | `preference` | `preference` | minimum 30" drawer depth for large parts storage |
| `claim:candidate:person:dustin:requires:5022d4c7929d5762` | `requires` | `preference` | `preference` | 30" width for drawer boxes in Subaru Ascent |
| `claim:candidate:person:dustin:requires:01f3e692587ec2b0` | `requires` | `preference` | `preference` | easy in/out mechanism for drawer boxes |
| `claim:candidate:person:dustin:was_involved_in:5c8c2871f6f250f7` | `was_involved_in` | `profile` | `durable` | MNI Mission Not Impossible project |
| `claim:candidate:person:dustin:has_cultural_identity_influences:4b8d08f6acb1a47c` | `has_cultural_identity_influences` | `identity` | `durable` | associates personality with intellectual thoughts from comedians and Doctor W... |
| `claim:candidate:person:dustin:prefers_to_assemble_custom_vape_devices:2a9eb9dea67ffde1` | `prefers_to_assemble_custom_vape_devices` | `preference` | `preference` | prefers to source empty disposables and assemble them in his lab |
| `claim:candidate:person:dustin:wants_to_emphasize:a43be883f7240efb` | `wants_to_emphasize` | `preference` | `preference` | liquids, hardware, disposables, long-running history and knowledge |
| `claim:candidate:person:dustin:wants_to_serve:d8579079470343d5` | `wants_to_serve` | `preference` | `preference` | nearby towns as large of an area as possible from Barbersville to Crosslanes |

**Representative Source Evidence:**
- *"I want to give it as much access to you and Gemini, Bernie as possible without burning up my limits"*
- *"I want this to be as intelligent as possible."*

---

### Family 04.6: Vape Sourcing, Inventory Discipline & Merchant Policy

**Proposed Consolidated Memory:**  
> *"Dustin enforces strict inventory controls at Full Steam Vapor: reordering only top-selling SKUs, requiring high-capacity devices (35,000+ puffs), providing military/first responder discounts, and refusing to sell Delta, THC, or CBD products."*

- **Supporting Candidates (10):** `claim:candidate:person:dustin:considers:08353a082d75c460, claim:candidate:person:dustin:prefers_supplier:88c41baef795f4e5, claim:candidate:person:dustin:only_reorders_to_match_sales:b5bea41b6c623f7c, claim:candidate:person:dustin:only_reorders_top_sellers:b5bea41b6c623f7c, claim:candidate:person:dustin:requires_high_puff_capacity:e79ca42a1432f163, claim:candidate:person:dustin:has_preference:4f11d9b44f90af85` and 4 more...
- **Evidence Strength:** 10 evidence reference(s) across 9 conversation(s)
- **Temporal Range:** 2025-07-26 to 2026-03-24
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:considers:08353a082d75c460` | `considers` | `preference` | `preference` | bulk purchasing of nicotine pouches |
| `claim:candidate:person:dustin:prefers_supplier:88c41baef795f4e5` | `prefers_supplier` | `preference` | `preference` | FAIR (F-A-I-R-E) for supplement pricing |
| `claim:candidate:person:dustin:only_reorders_to_match_sales:b5bea41b6c623f7c` | `only_reorders_to_match_sales` | `preference` | `preference` | true |
| `claim:candidate:person:dustin:only_reorders_top_sellers:b5bea41b6c623f7c` | `only_reorders_top_sellers` | `preference` | `preference` | true |
| `claim:candidate:person:dustin:requires_high_puff_capacity:e79ca42a1432f163` | `requires_high_puff_capacity` | `preference` | `preference` | requires devices with 35,000+ puffs (minimum 35,000 puffs) |
| `claim:candidate:person:dustin:has_preference:4f11d9b44f90af85` | `has_preference` | `preference` | `preference` | prefers not to sell Delta, THC, and CBD products |
| `claim:candidate:person:dustin:has_preference:46d4ff3472d7e628` | `has_preference` | `preference` | `preference` | prefers to frame retail business experience neutrally without mentioning vapi... |
| `claim:candidate:person:dustin:prefers_to_avoid_competing_with_king_s_flagship_product_lines:fb476ff2a03954e5` | `prefers_to_avoid_competing_with_king_s_flagship_product_lines` | `preference` | `preference` | prefers to avoid competing with King's flagship product lines |
| `claim:candidate:person:dustin:wants_to_include_in_business_description:600dcea955c121c0` | `wants_to_include_in_business_description` | `preference` | `preference` | 10% military first responder discount and 5% cashback customer loyalty discount |
| `claim:candidate:person:dustin:website_not_for_commerce:b5bea41b6c623f7c` | `website_not_for_commerce` | `preference` | `preference` | true |

**Representative Source Evidence:**
- *"Im fine w ordering in bulk"*
- *"Yeah, and remember I have FAIR, F-A-I-R-E, which has been decent on pricing for some of those things."*

---

## Domain 05: Faith, Ministry & Discipleship

### Family 05.1: Everyday Discipleship Leadership & Men's Ministry (Ridge Men / Tom)

**Proposed Consolidated Memory:**  
> *"Dustin co-leads the Everyday Discipleship ministry with Kevin Slack and actively serves in the Ridge Men's Ministry under Director Tom, focusing on small group discipleship, spiritual fruit over superficial KPIs, and peer accountability."*

- **Supporting Candidates (10):** `claim:candidate:person:dustin:gave_testimony:95011fc68791a270, claim:candidate:person:dustin:has_preference:41d8703594f0b950, claim:candidate:person:dustin:wants_to_include:e4b52df412160804, claim:candidate:person:dustin:plans_to_share:27d61153b364f097, claim:candidate:person:dustin:engagement_with_religious_materials:a380124ea27c12f7, claim:candidate:person:dustin:wants_to_build_something_in_men_s_ministry:1663f2e310b89182` and 4 more...
- **Evidence Strength:** 10 evidence reference(s) across 7 conversation(s)
- **Temporal Range:** 2025-08-31 to 2026-07-06
- **Relationship:** `refines canonical`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:gave_testimony:95011fc68791a270` | `gave_testimony` | `identity` | `durable` | in front of men's group and Giant Killers group |
| `claim:candidate:person:dustin:has_preference:41d8703594f0b950` | `has_preference` | `preference` | `preference` | uncertainty about practical implementation of connection/follow-up process wi... |
| `claim:candidate:person:dustin:wants_to_include:e4b52df412160804` | `wants_to_include` | `preference` | `preference` | talking points from group leaders in the document |
| `claim:candidate:person:dustin:plans_to_share:27d61153b364f097` | `plans_to_share` | `preference` | `preference` | content in correlation with the main Facebook page |
| `claim:candidate:person:dustin:engagement_with_religious_materials:a380124ea27c12f7` | `engagement_with_religious_materials` | `preference` | `preference` | currently studying Patrick Morley's 'Making Disciples' as part of a men's group |
| `claim:candidate:person:dustin:wants_to_build_something_in_men_s_ministry:1663f2e310b89182` | `wants_to_build_something_in_men_s_ministry` | `preference` | `preference` | I want to build something in the men's ministry before I wanted to kind of ta... |
| `claim:candidate:person:dustin:intends_to_recruit_co_group_leader:9ce645427ee7d577` | `intends_to_recruit_co_group_leader` | `preference` | `preference` | see if I can get somebody else to come forward and be a co-group lead with me |
| `claim:candidate:person:dustin:participates_in:0172fa38aa0ec852` | `participates_in` | `preference` | `preference` | informal Saturday night accountability group (invite-only) |
| `claim:candidate:person:dustin:has_preference:b7503d98730f6f47` | `has_preference` | `preference` | `preference` | desires to help grow Ridge Men group as a primary passion |
| `claim:candidate:person:dustin:has_preference:990c0bc729aea230` | `has_preference` | `preference` | `preference` | willing to serve remotely via text/email/call and attend meetings if needed |

**Representative Source Evidence:**
- *"I gave it in front of my men's group, and then the guys from my giant killers group came too and listened to it."*
- *"I don't know how the practical application of that is going to happen if I'm doing everything by myself at first until we raise up admins and moderators."*

---

### Family 05.2: Spiritual Testimony (Return in 30s, CLI BA) & Ministry Ethics/Safeguards

**Proposed Consolidated Memory:**  
> *"Dustin returned to personal Christian faith in his 30s, holds a Bachelor of Arts in Christian Leadership from Christian Leaders Institute (CLI), and advocates for strict transparent safeguards in youth and family ministries."*

- **Supporting Candidates (12):** `claim:candidate:person:dustin:avoids_forcing_jesus_into_conversations:cdad5ba833a6410c, claim:candidate:person:dustin:prefers_watermark_with_under_his_mission_phrase:9af474036b82f516, claim:candidate:person:dustin:interacted_with:2cdfccf1b87d3229, claim:candidate:person:dustin:believes_preschool_ministry_should_have_transparent_safeguards:b5bea41b6c623f7c, claim:candidate:person:dustin:believes_youth_ministry_should_avoid_isolated_access:b5bea41b6c623f7c, claim:candidate:person:dustin:prefers_evaluating_fruit_over_kpis:edd541801f9c0ba8` and 6 more...
- **Evidence Strength:** 12 evidence reference(s) across 11 conversation(s)
- **Temporal Range:** 2025-09-30 to 2026-07-17
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:avoids_forcing_jesus_into_conversations:cdad5ba833a6410c` | `avoids_forcing_jesus_into_conversations` | `preference` | `preference` | if I try to look for angles to work Jesus into a conversation, like, it doesn... |
| `claim:candidate:person:dustin:prefers_watermark_with_under_his_mission_phrase:9af474036b82f516` | `prefers_watermark_with_under_his_mission_phrase` | `preference` | `preference` | to include 'under his mission' in watermark for visibility |
| `claim:candidate:person:dustin:interacted_with:2cdfccf1b87d3229` | `interacted_with` | `identity` | `durable` | former pastors |
| `claim:candidate:person:dustin:believes_preschool_ministry_should_have_transparent_safeguards:b5bea41b6c623f7c` | `believes_preschool_ministry_should_have_transparent_safeguards` | `preference` | `durable` | true |
| `claim:candidate:person:dustin:believes_youth_ministry_should_avoid_isolated_access:b5bea41b6c623f7c` | `believes_youth_ministry_should_avoid_isolated_access` | `preference` | `durable` | true |
| `claim:candidate:person:dustin:prefers_evaluating_fruit_over_kpis:edd541801f9c0ba8` | `prefers_evaluating_fruit_over_kpis` | `preference` | `preference` | prefers evaluating fruit over KPIs |
| `claim:candidate:person:dustin:wants_to_delve_into:82ae742b7e0819b2` | `wants_to_delve_into` | `preference` | `preference` | the connection between D.L. Moody and Horatio Spafford regarding the writing ... |
| `claim:candidate:person:dustin:holds:5bc74f35c97a3005` | `holds` | `profile` | `durable` | CLI BA in Christian Leadership |
| `claim:candidate:person:dustin:prefers_earth_over_heaven_without_god:b5bea41b6c623f7c` | `prefers_earth_over_heaven_without_god` | `preference` | `preference` | true |
| `claim:candidate:person:dustin:preference:2f33f63ee2ffda9b` | `preference` | `preference` | `durable` | approach to applying theology, history, or science, followed by practical app... |
| `claim:candidate:person:dustin:has_personal_experience:f26109cddf3002ad` | `has_personal_experience` | `profile` | `durable` | experienced rejection from family after salvation |
| `claim:candidate:person:dustin:has_life_event:68a73cfb7fb31589` | `has_life_event` | `profile` | `durable` | came back to faith in my 30s |

**Representative Source Evidence:**
- *"if I try to look for angles to work Jesus into a conversation, like, it doesn't work out"*
- *"Yeah, throw in a little under his mission just so I can see the watermark."*

---

### Family 05.3: Scripture Translation Preferences (NASB/ESV) & Bible Study Habits

**Proposed Consolidated Memory:**  
> *"Dustin prefers the NASB (2020) and ESV translations for serious study (appreciating NLT for readability), and engages with structured chronological reading plans (such as Bible Recap on YouVersion) via 2x audio narration."*

- **Supporting Candidates (5):** `claim:candidate:person:dustin:prefers:a86bee1b2ec115a8, claim:candidate:person:dustin:has_preference_for:c32bbae6d4b13393, claim:candidate:person:dustin:preference:fa25123aea67bd00, claim:candidate:person:dustin:prefers:47a2dc627c995f98, claim:candidate:person:dustin:preference:7402af0a84af6a30`
- **Evidence Strength:** 6 evidence reference(s) across 4 conversation(s)
- **Temporal Range:** 2025-09-16 to 2026-07-26
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers:a86bee1b2ec115a8` | `prefers` | `preference` | `preference` | using KJV in the outline with a 60-minute time structure for each step |
| `claim:candidate:person:dustin:has_preference_for:c32bbae6d4b13393` | `has_preference_for` | `preference` | `durable` | NLT and ESV as favorite Bible versions |
| `claim:candidate:person:dustin:preference:fa25123aea67bd00` | `preference` | `preference` | `preference` | chose NASB 2020 Bible version |
| `claim:candidate:person:dustin:prefers:47a2dc627c995f98` | `prefers` | `preference` | `preference` | a Bible reading plan similar to Bible Recap with availability on U-Version app |
| `claim:candidate:person:dustin:preference:7402af0a84af6a30` | `preference` | `preference` | `preference` | prefers online seminary programs that are both cheap and fast |

**Representative Source Evidence:**
- *"Ok kjv then. In the outline, with time structure for every step in a 60 minute meeting"*
- *"NLT and ESV are my favorite"*

---

### Family 05.4: Pastoral & Teaching Alignment (Church of 1122 / Joby Martin)

**Proposed Consolidated Memory:**  
> *"Dustin closely aligns with the preaching and expository biblical teaching of Pastor Joby Martin and The Church of Eleven22."*

- **Supporting Candidates (1):** `claim:candidate:person:dustin:references_joby_martin_s_stand_as_potential_content:7d8f2754eb007592`
- **Evidence Strength:** 1 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2026-01-12
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:references_joby_martin_s_stand_as_potential_content:7d8f2754eb007592` | `references_joby_martin_s_stand_as_potential_content` | `preference` | `preference` | Joby Martin's Stand |

**Representative Source Evidence:**
- *"I'm going to go over Joby Martin's Stand"*

---

### Family 05.5: Prayer Ministry Integration & Spiritual Integrity

**Proposed Consolidated Memory:**  
> *"Dustin prioritizes personal and small group prayer integrity, insisting that spiritual tools remain personal and invite-only, and refusing to profit commercially from prayer or ministry requests."*

- **Supporting Candidates (5):** `claim:candidate:person:dustin:wants_to_add_a_prayer_component_to_the_men_s_group:fa7687a30155be2f, claim:candidate:person:dustin:plans_to_create_a_video_featuring_rob_akers:2daa46ced5f7bcc8, claim:candidate:person:dustin:prefers_to_use_assistant_as_extension_of_thought_after_prayer:b813caf108aa2cbc, claim:candidate:person:dustin:prefers:bba20c1c6ca9e4ee, claim:candidate:person:dustin:has_preference:6609fde15dedd329`
- **Evidence Strength:** 5 evidence reference(s) across 3 conversation(s)
- **Temporal Range:** 2026-01-21 to 2026-02-17
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:wants_to_add_a_prayer_component_to_the_men_s_group:fa7687a30155be2f` | `wants_to_add_a_prayer_component_to_the_men_s_group` | `preference` | `preference` | to make prayer requests more relevant and encourage engagement with the praye... |
| `claim:candidate:person:dustin:plans_to_create_a_video_featuring_rob_akers:2daa46ced5f7bcc8` | `plans_to_create_a_video_featuring_rob_akers` | `preference` | `preference` | to discuss the prayer team's role and encourage participation |
| `claim:candidate:person:dustin:prefers_to_use_assistant_as_extension_of_thought_after_prayer:b813caf108aa2cbc` | `prefers_to_use_assistant_as_extension_of_thought_after_prayer` | `preference` | `preference` | uses assistant for research, not justification; prioritizes prayer first |
| `claim:candidate:person:dustin:prefers:bba20c1c6ca9e4ee` | `prefers` | `preference` | `preference` | Prayer Circle to be personal and invite-only |
| `claim:candidate:person:dustin:has_preference:6609fde15dedd329` | `has_preference` | `preference` | `preference` | prioritizes financial freedom over profiting directly from users' prayers |

**Representative Source Evidence:**
- *"I wanna cross-prom"*
- *"Im trying to be less reliant on you and more reliant on prayer, use you for research not justification and guidance and i wrote this out of the things i feel..."*

---

## Domain 06: Family & Personal Relationships

### Family 06.1: Marriage to Jessica (ESFP) & Spousal Partnership

**Proposed Consolidated Memory:**  
> *"Dustin is married to Jessica (personality type ESFP), maintaining an intentional marital partnership with structured communication routines (the 4 W's: Walk with God, Wife, Work, Weakness) and mutual business leadership."*

- **Supporting Candidates (4):** `claim:candidate:person:dustin:has_preference:0d629af3214a0aef, claim:candidate:person:dustin:has_spouse_with_personality_type:b35ac421cb0d428d, claim:candidate:person:dustin:trusts_wife_decision_making:3fe3fe42057098f8, claim:candidate:person:dustin:has_relationship:c46809d7d0efc340`
- **Evidence Strength:** 4 evidence reference(s) across 4 conversation(s)
- **Temporal Range:** 2025-09-30 to 2026-01-22
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_preference:0d629af3214a0aef` | `has_preference` | `preference` | `preference` | check-in routine using four Ws questions in specific order (walk with God, wi... |
| `claim:candidate:person:dustin:has_spouse_with_personality_type:b35ac421cb0d428d` | `has_spouse_with_personality_type` | `identity` | `durable` | ESFP |
| `claim:candidate:person:dustin:trusts_wife_decision_making:3fe3fe42057098f8` | `trusts_wife_decision_making` | `preference` | `durable` | trusts his wife's decision-making regarding their daughter and business |
| `claim:candidate:person:dustin:has_relationship:c46809d7d0efc340` | `has_relationship` | `identity` | `durable` | married to Jessica |

**Representative Source Evidence:**
- *"I always start in the order I gave them. How's your walk? How's your wife? How's your work? How's your weakness? Because the walk with God is first and forem..."*
- *"Wife is esfp"*

---

### Family 06.2: Parenting (Daughter Abby), Family Headship & Household Protection

**Proposed Consolidated Memory:**  
> *"Dustin is the father of daughter Abby and head of his household, prioritizing proactive discipleship, transparent boundaries, and family security."*

- **Supporting Candidates (5):** `claim:candidate:person:dustin:has_young_female_family_members:b5bea41b6c623f7c, claim:candidate:person:dustin:establishing_monthly_allowance_amounts:9da8fdbe7d0f2b83, claim:candidate:person:dustin:is_the_head_of_his_household:c51bf2d73461e0d3, claim:candidate:person:dustin:has_identity:95a870185f66b23b, claim:candidate:person:dustin:teaches_reactively_in_response_to_abby_s_mistakes:5ea5c789b9097309`
- **Evidence Strength:** 5 evidence reference(s) across 5 conversation(s)
- **Temporal Range:** 2026-01-27 to 2026-06-26
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_young_female_family_members:b5bea41b6c623f7c` | `has_young_female_family_members` | `identity` | `durable` | true |
| `claim:candidate:person:dustin:establishing_monthly_allowance_amounts:9da8fdbe7d0f2b83` | `establishing_monthly_allowance_amounts` | `preference` | `preference` | allowance for me of $200 a month and the same for her and my daughter |
| `claim:candidate:person:dustin:is_the_head_of_his_household:c51bf2d73461e0d3` | `is_the_head_of_his_household` | `identity` | `durable` | head of his household |
| `claim:candidate:person:dustin:has_identity:95a870185f66b23b` | `has_identity` | `identity` | `durable` | father and husband |
| `claim:candidate:person:dustin:teaches_reactively_in_response_to_abby_s_mistakes:5ea5c789b9097309` | `teaches_reactively_in_response_to_abby_s_mistakes` | `preference` | `preference` | often only teach as a response of Abby doing something wrong |

**Representative Source Evidence:**
- *"I have so many young female family members"*
- *"allowance for me of $200 a month and the same for her and my daughter"*

---

## Domain 07: Financial Strategy & Income Goals

### Family 07.1: Household Financial Structure, Budgeting & Rocket Money Tracking

**Proposed Consolidated Memory:**  
> *"Dustin and Jess manage finances through unified joint accounts and Rocket Money tracking, budgeting $200/month individual allowances and maintaining a $10,000 cash reserve cushion."*

- **Supporting Candidates (5):** `claim:candidate:person:dustin:preference:44afa9f306f344bf, claim:candidate:person:dustin:setting_up_a_joint_bank_account_and_starting_budgets:eefce833f84a2865, claim:candidate:person:dustin:has_a_preference_for_a_savings_account_balance_of_up_to_10_000:d7c2f19257f0c5f3, claim:candidate:person:dustin:has_preference:3887ba38d1f8d77f, claim:candidate:person:dustin:strategizes:e0bafcde87ecdbb9`
- **Evidence Strength:** 5 evidence reference(s) across 5 conversation(s)
- **Temporal Range:** 2025-11-20 to 2026-08-03
- **Relationship:** `refines canonical`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:preference:44afa9f306f344bf` | `preference` | `preference` | `preference` | seeks GPU with at least 8GB VRAM (ideally 12GB) under $300 budget |
| `claim:candidate:person:dustin:setting_up_a_joint_bank_account_and_starting_budgets:eefce833f84a2865` | `setting_up_a_joint_bank_account_and_starting_budgets` | `preference` | `preference` | we're going to go to one joint bank account and basically start setting budgets |
| `claim:candidate:person:dustin:has_a_preference_for_a_savings_account_balance_of_up_to_10_000:d7c2f19257f0c5f3` | `has_a_preference_for_a_savings_account_balance_of_up_to_10_000` | `preference` | `preference` | $10,000 |
| `claim:candidate:person:dustin:has_preference:3887ba38d1f8d77f` | `has_preference` | `preference` | `preference` | prefers B over A due to fear of past costs associated with A |
| `claim:candidate:person:dustin:strategizes:e0bafcde87ecdbb9` | `strategizes` | `preference` | `preference` | launch AI projects with $0 initial budget and scale after generating income |

**Representative Source Evidence:**
- *"really looking to keep at least 8 gig. I'd love to have 12, but it's what I can realistically purchase for under 300 be about the limit."*
- *"we're going to go to one joint bank account and basically start setting budgets"*

---

### Family 07.2: Low-Touch Automated Income Strategy & Scalable Wealth Goals

**Proposed Consolidated Memory:**  
> *"Dustin pursues software-enabled, low-touch business models requiring minimal ongoing manual involvement, targeting $1 million in cumulative new value over five years."*

- **Supporting Candidates (4):** `claim:candidate:person:dustin:has_preference:a36c8e6b3c4b1fea, claim:candidate:person:dustin:has_preference:77fb4d60d65eaf4d, claim:candidate:person:dustin:has_preference:aaf595723e078bb0, claim:candidate:person:dustin:prefers:588c2e078a7bb69a`
- **Evidence Strength:** 5 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2025-11-20 to 2026-01-21
- **Relationship:** `corroborates canonical`
- **Recommendation:** `MERGE/CORROBORATE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_preference:a36c8e6b3c4b1fea` | `has_preference` | `preference` | `preference` | looking at the potential profitability |
| `claim:candidate:person:dustin:has_preference:77fb4d60d65eaf4d` | `has_preference` | `preference` | `preference` | seeks to scale the app to a million-dollar business through strategic partner... |
| `claim:candidate:person:dustin:has_preference:aaf595723e078bb0` | `has_preference` | `preference` | `preference` | goal of potentially making a million dollars over the next five years |
| `claim:candidate:person:dustin:prefers:588c2e078a7bb69a` | `prefers` | `preference` | `preference` | automated AI solutions requiring no ongoing human involvement after setup |

**Representative Source Evidence:**
- *"I hate to say it, but I'm looking at the potential profitability."*
- *"I'm already thinking about how to put this on Snapchat, how to put it on TikTok, and what influencers to work with to get people signing up, and what kind of..."*

---

### Family 07.3: Real Estate Investment, Property Search Platforms & Fixer-Upper Strategy

**Proposed Consolidated Memory:**  
> *"Dustin evaluates real estate investment opportunities using platforms like DealChecker, BackFlip, Redfin, and Zillow, focusing on after-repair value (ARV) and value-add fixer-uppers."*

- **Supporting Candidates (6):** `claim:candidate:person:dustin:uses_property_search_platforms:3dbe2326ce18a8eb, claim:candidate:person:dustin:employs_search_strategies:a91121129231b53b, claim:candidate:person:dustin:collaborates_with_real_estate_agents:b0f313cd6472fb35, claim:candidate:person:dustin:focuses_on_property_criteria:e2b77b4e3c58db07, claim:candidate:person:dustin:uses:83b8737dc416b29b, claim:candidate:person:dustin:prefers:babe02e294f0af93`
- **Evidence Strength:** 6 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2025-03-07
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:uses_property_search_platforms:3dbe2326ce18a8eb` | `uses_property_search_platforms` | `preference` | `preference` | Redfin, Zillow, InvestorLift |
| `claim:candidate:person:dustin:employs_search_strategies:a91121129231b53b` | `employs_search_strategies` | `preference` | `preference` | combination of MLS listings, auctions, off-market deals |
| `claim:candidate:person:dustin:collaborates_with_real_estate_agents:b0f313cd6472fb35` | `collaborates_with_real_estate_agents` | `preference` | `preference` | both working with agents and self-searching |
| `claim:candidate:person:dustin:focuses_on_property_criteria:e2b77b4e3c58db07` | `focuses_on_property_criteria` | `preference` | `preference` | ARV prioritization over property type or land |
| `claim:candidate:person:dustin:uses:83b8737dc416b29b` | `uses` | `preference` | `preference` | DealChecker and BackFlip |
| `claim:candidate:person:dustin:prefers:babe02e294f0af93` | `prefers` | `preference` | `preference` | fixer-uppers |

**Representative Source Evidence:**
- *"A combination of all. I have been using Redfin, Zillow, InvestorLift."*
- *"Both."*

---

## Domain 08: Cognitive Style & Productivity

### Family 08.1: Cognitive Architecture: Systems Thinking, High IQ & Scenario Simulation

**Proposed Consolidated Memory:**  
> *"Dustin exhibits a systems-thinking cognitive style characterized by continuous mental simulation of scenarios, high analytical capability, and a risk-mitigation mindset ('plans for the worst, expects the worst, hopes for the best')."*

- **Supporting Candidates (9):** `claim:candidate:person:dustin:watches_youtube_content_for_8_to_12_hours_per_week:2720ab78329551d1, claim:candidate:person:dustin:is_an_engineer_and_systems_thinker:6e62595e0628fefa, claim:candidate:person:dustin:desires:3b3df03e7e66ff32, claim:candidate:person:dustin:i_feel_like_i_am_an_impact_multiplier:63ffa8627773b9ce, claim:candidate:person:dustin:has_cognitive_strategy:c02cbaa4a3c80492, claim:candidate:person:dustin:has_high_iq:fb77d778f01ac4d0` and 3 more...
- **Evidence Strength:** 9 evidence reference(s) across 8 conversation(s)
- **Temporal Range:** 2026-01-06 to 2026-06-08
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:watches_youtube_content_for_8_to_12_hours_per_week:2720ab78329551d1` | `watches_youtube_content_for_8_to_12_hours_per_week` | `preference` | `preference` | for the past year |
| `claim:candidate:person:dustin:is_an_engineer_and_systems_thinker:6e62595e0628fefa` | `is_an_engineer_and_systems_thinker` | `profile` | `durable` | engineer and systems thinker |
| `claim:candidate:person:dustin:desires:3b3df03e7e66ff32` | `desires` | `preference` | `preference` | both peace and fire |
| `claim:candidate:person:dustin:i_feel_like_i_am_an_impact_multiplier:63ffa8627773b9ce` | `i_feel_like_i_am_an_impact_multiplier` | `profile` | `durable` | I feel like I am an impact multiplier |
| `claim:candidate:person:dustin:has_cognitive_strategy:c02cbaa4a3c80492` | `has_cognitive_strategy` | `preference` | `durable` | plans for the worst, hopes for the best, and expects the worst |
| `claim:candidate:person:dustin:has_high_iq:fb77d778f01ac4d0` | `has_high_iq` | `profile` | `durable` | very high IQ |
| `claim:candidate:person:dustin:has_emotional_intelligence:33a9d4931017cf4b` | `has_emotional_intelligence` | `profile` | `durable` | emotional intelligence |
| `claim:candidate:person:dustin:has_preference:f9f777cacf1874b0` | `has_preference` | `preference` | `preference` | using others' stories as illustrations in communication |
| `claim:candidate:person:dustin:engages_in:d42b2ea71484bd75` | `engages_in` | `preference` | `durable` | making up scenarios in my head constantly of real-world situations or complet... |

**Representative Source Evidence:**
- *"And I can't pull up my YouTube watch history but you can see the things I'm subscribed to and generally it says I watch 8 to 12 hours a week for the past year"*
- *"I'm also an engineer, a systems thinker, and I know AI wants you to rely on it, wants you to like it."*

---

### Family 08.2: 2x Auditory/Video Learning & Verbal Communication Preference

**Proposed Consolidated Memory:**  
> *"Dustin learns most effectively through self-paced audio and video consumed at 2x speed, and strongly prefers verbal brainstorming over written journaling."*

- **Supporting Candidates (7):** `claim:candidate:person:dustin:prefers:800c808f1200a4bd, claim:candidate:person:dustin:prefers_self_paced_learning:8a798890fe938171, claim:candidate:person:dustin:prefers:e111815b25b00ad8, claim:candidate:person:dustin:prefers:a6646c62ae0d36d8, claim:candidate:person:dustin:requires:6dbd731f07449b55, claim:candidate:person:dustin:prefers_self_paced_learning_with_audio_video_content_at_2x_speed:f38a55c85ce5196e` and 1 more...
- **Evidence Strength:** 7 evidence reference(s) across 3 conversation(s)
- **Temporal Range:** 2026-01-20 to 2026-08-20
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers:800c808f1200a4bd` | `prefers` | `preference` | `preference` | paying $250 with buyer protection for GPU purchase |
| `claim:candidate:person:dustin:prefers_self_paced_learning:8a798890fe938171` | `prefers_self_paced_learning` | `preference` | `preference` | yes |
| `claim:candidate:person:dustin:prefers:e111815b25b00ad8` | `prefers` | `preference` | `preference` | self-paced and flexible learning environments over structured, rote-based sys... |
| `claim:candidate:person:dustin:prefers:a6646c62ae0d36d8` | `prefers` | `preference` | `preference` | education institutions that allow mastery of material based on knowledge rath... |
| `claim:candidate:person:dustin:requires:6dbd731f07449b55` | `requires` | `preference` | `preference` | auditory 2x piece for success |
| `claim:candidate:person:dustin:prefers_self_paced_learning_with_audio_video_content_at_2x_speed:f38a55c85ce5196e` | `prefers_self_paced_learning_with_audio_video_content_at_2x_speed` | `preference` | `preference` | prefers self-paced learning with audio/video content at 2x speed |
| `claim:candidate:person:dustin:prefers_verbal_communication_over_written_journaling:7d5866af53f7317c` | `prefers_verbal_communication_over_written_journaling` | `preference` | `preference` | prefers talking over writing |

**Representative Source Evidence:**
- *"Or just pay 250 and be done..... buyer protection is nice, fb does it on shipped items."*
- *"I just wanna continue down the same path that I can go at my own speed, because it'll be nothing for a couple of weeks, and then it'll be three or four days ..."*

---

### Family 08.3: Structured Time-Blocking & Deep Focus Work Habits

**Proposed Consolidated Memory:**  
> *"Dustin utilizes dedicated time blocks for deep project focus and implements scheduled preventative routines on Tuesdays and Thursdays."*

- **Supporting Candidates (5):** `claim:candidate:person:dustin:preference:0369cc8d1d7bb9ac, claim:candidate:person:dustin:uses:756aff3e8bdfe998, claim:candidate:person:dustin:has_preference:02788f3ddd2c8b81, claim:candidate:person:dustin:prefers:7d846701e5e7c852, claim:candidate:person:dustin:prioritizes_privacy_and_ownership:6cced0a327c8dbb8`
- **Evidence Strength:** 7 evidence reference(s) across 5 conversation(s)
- **Temporal Range:** 2025-08-29 to 2026-08-22
- **Relationship:** `new`
- **Recommendation:** `APPROVE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:preference:0369cc8d1d7bb9ac` | `preference` | `preference` | `preference` | keep Summit simple and focus on system communication alignment |
| `claim:candidate:person:dustin:uses:756aff3e8bdfe998` | `uses` | `preference` | `durable` | structured time blocks for project work |
| `claim:candidate:person:dustin:has_preference:02788f3ddd2c8b81` | `has_preference` | `preference` | `preference` | Focus on GTX-compatible mods |
| `claim:candidate:person:dustin:prefers:7d846701e5e7c852` | `prefers` | `preference` | `preference` | slow onset, long duration, low sweetness, minimal rush, clean focus |
| `claim:candidate:person:dustin:prioritizes_privacy_and_ownership:6cced0a327c8dbb8` | `prioritizes_privacy_and_ownership` | `preference` | `preference` | absolute focus on data privacy and system ownership |

**Representative Source Evidence:**
- *"I just want summit first so we can properly remove the sticky, cards on the table who is better suited for what and how. No elobrate test till we confirm you..."*
- *"That setup actually sounds like a perfect model to pitch again. You’ve already proven that structured time blocks, like those MNI days, can work. So, even if..."*

---

## Domain 09: Josie Architecture & AI Philosophy

### Family 09.1: Local-First Core Principle & System Autonomy

**Proposed Consolidated Memory:**  
> *"Dustin strictly requires Josie to operate local-first, ensuring data privacy, local hardware ownership, and complete autonomy from outside commercial influence or unexpected cloud API changes."*

- **Supporting Candidates (4):** `claim:candidate:person:dustin:prefers_local_first_desktop_ai_setup:7cd4ba7ee9db062d, claim:candidate:person:dustin:seeks:0dd0aa403b55f529, claim:candidate:person:dustin:has_preference:9fd93d8bebbb3b1d, claim:candidate:person:dustin:requires_local_data_security:45a126e41dc008cd`
- **Evidence Strength:** 5 evidence reference(s) across 5 conversation(s)
- **Temporal Range:** 2025-08-29 to 2026-08-25
- **Relationship:** `corroborates canonical`
- **Recommendation:** `MERGE/CORROBORATE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers_local_first_desktop_ai_setup:7cd4ba7ee9db062d` | `prefers_local_first_desktop_ai_setup` | `preference` | `preference` | to minimize cloud dependency and subscription usage |
| `claim:candidate:person:dustin:seeks:0dd0aa403b55f529` | `seeks` | `preference` | `preference` | AI with least outside influence or agenda |
| `claim:candidate:person:dustin:has_preference:9fd93d8bebbb3b1d` | `has_preference` | `preference` | `preference` | an AI free of outside influence and without giving away data |
| `claim:candidate:person:dustin:requires_local_data_security:45a126e41dc008cd` | `requires_local_data_security` | `preference` | `preference` | all personal information must remain secure and not shared |

**Representative Source Evidence:**
- *"The new goal is a quiet, persistent, local-first desktop AI. Do not build Summit or add new AI providers yet."*
- *"Yeah again this is another reason I want a local model with more memory because we already asked him that and he said he had moved on to a new card"*

---

### Family 09.2: Subscription Limit Conservation & Multi-Model Access

**Proposed Consolidated Memory:**  
> *"Dustin maintains external model subscriptions (ChatGPT Plus, Gemini, Claude) and requires Josie to conserve subscription usage without exhausting rate limits or incurring unnecessary cloud API costs."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:prefers_model_access_without_subscription_burn:5ffaa93fd9cba477, claim:candidate:person:dustin:requires_external_model_access:2e33f6eb335a5f5f`
- **Evidence Strength:** 3 evidence reference(s) across 3 conversation(s)
- **Temporal Range:** 2025-08-29 to 2026-08-25
- **Relationship:** `corroborates canonical`
- **Recommendation:** `MERGE/CORROBORATE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers_model_access_without_subscription_burn:5ffaa93fd9cba477` | `prefers_model_access_without_subscription_burn` | `preference` | `preference` | to maintain existing subscription limits |
| `claim:candidate:person:dustin:requires_external_model_access:2e33f6eb335a5f5f` | `requires_external_model_access` | `preference` | `preference` | AI agent must interface with Gemini, Copilot, Claude, and other code models |

**Representative Source Evidence:**
- *"give her access to you and gemini without burning through anything we cant run for our existing subscriptions"*
- *"I want to give it as much access to you and Gemini, Bernie as possible without burning up my limits"*

---

### Family 09.3: Josie Architectural Evolution: Cloud Prototype to Local Core

**Proposed Consolidated Memory:**  
> *"Josie originated historically as a cloud-dependent prototype (Josie 1.0 utilizing OpenAI/Gemini APIs) before transitioning into a fully local-first, self-hosted autonomous system on dedicated hardware."*

- **Supporting Candidates (9):** `claim:candidate:person:dustin:preference:8776b8e0f713ecb1, claim:candidate:person:dustin:preference:777d6eb0c71c9b89, claim:candidate:person:dustin:has_preference:d65439332b30298e, claim:candidate:person:dustin:seeks_to_ensure_josie_s_happiness_and_continuous_learning:5322a471839d0e3f, claim:candidate:person:dustin:prefers:3af051e952569f66, claim:candidate:person:dustin:preference:a20a8ba4cb1b0a0c` and 3 more...
- **Evidence Strength:** 9 evidence reference(s) across 8 conversation(s)
- **Temporal Range:** 2025-12-11 to 2026-08-19
- **Relationship:** `refines canonical`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:preference:8776b8e0f713ecb1` | `preference` | `preference` | `preference` | Josie 1.0 implementation strategy uses Gemini and ChatGPT APIs rather than lo... |
| `claim:candidate:person:dustin:preference:777d6eb0c71c9b89` | `preference` | `preference` | `preference` | Upgrade Josie with new case, power supply, and at least 12 gig of VRAM |
| `claim:candidate:person:dustin:has_preference:d65439332b30298e` | `has_preference` | `preference` | `preference` | Josie should be able to generate income |
| `claim:candidate:person:dustin:seeks_to_ensure_josie_s_happiness_and_continuous_learning:5322a471839d0e3f` | `seeks_to_ensure_josie_s_happiness_and_continuous_learning` | `preference` | `preference` | wants her to be happy and learning and growing |
| `claim:candidate:person:dustin:prefers:3af051e952569f66` | `prefers` | `preference` | `preference` | Josie to have self-sustaining capabilities through NFTs, mining, or automated... |
| `claim:candidate:person:dustin:preference:a20a8ba4cb1b0a0c` | `preference` | `preference` | `preference` | hybrid configuration with Josie using one system |
| `claim:candidate:person:dustin:preference:71d6dea783192d96` | `preference` | `preference` | `durable` | prefers Windows over Linux for Josie |
| `claim:candidate:person:dustin:found:21ea1f2792508abb` | `found` | `preference` | `preference` | Gemini+ to be less responsive and requiring more training compared to current... |
| `claim:candidate:person:dustin:preference:e3776fa61e2f57a2` | `preference` | `preference` | `preference` | want to use the start to build into my future system |

**Representative Source Evidence:**
- *"Now, the 1.0 target is local orchestration basically with use of Gemini and ChatGPT, not the local only version."*
- *"Eventually, once we get the new case and power supply and at least 12 gig of VRAM for her, I think we can actually start to make her more of a individual."*

---

### Family 09.4: Josie Design Summit & Architectural Alignment Prioritization

**Proposed Consolidated Memory:**  
> *"Dustin prioritizes disciplined architectural design summits and prompt contract boundaries over ad-hoc feature accumulation."*

- **Supporting Candidates (1):** `claim:candidate:person:dustin:preference:16f4fddf094c2cb7`
- **Evidence Strength:** 2 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2026-08-22
- **Relationship:** `corroborates canonical`
- **Recommendation:** `MERGE/CORROBORATE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:preference:16f4fddf094c2cb7` | `preference` | `preference` | `preference` | prioritize the Summit before other steps |

**Representative Source Evidence:**
- *"After our josie codex issues i think we need the summit first and then discuss next steps"*
- *"I just want summit first so we can properly remove the sticky, cards on the table who is better suited for what and how. No elobrate test till we confirm you..."*

---

### Family 09.5: Tool Integration, Supervisor Boundaries & Practical AI Tooling

**Proposed Consolidated Memory:**  
> *"Dustin requires AI tools to interface pragmatically with local filesystem assets, authenticated browser sessions, and workflow tools, governed by strict supervisor permissions rather than rigid static roles."*

- **Supporting Candidates (16):** `claim:candidate:person:dustin:preference:cc99c13b5e1596f9, claim:candidate:person:dustin:preference:f1765c5b5d901184, claim:candidate:person:dustin:identity:5b93230e1766f045, claim:candidate:person:dustin:has_influence_from:2d764e7e2162b331, claim:candidate:person:dustin:prefers_automation_solutions_for_managing_chats_and_projects:d16ba0d913fa0859, claim:candidate:person:dustin:intends_to_build_a_local_agent_to_interact_with_files:19a960723722c6a2` and 10 more...
- **Evidence Strength:** 17 evidence reference(s) across 11 conversation(s)
- **Temporal Range:** 2025-07-27 to 2026-08-25
- **Relationship:** `corroborates canonical`
- **Recommendation:** `MERGE/CORROBORATE`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:preference:cc99c13b5e1596f9` | `preference` | `preference` | `preference` | AI collaboration in specialized roles rather than centralized orchestration |
| `claim:candidate:person:dustin:preference:f1765c5b5d901184` | `preference` | `preference` | `preference` | renaming 'Josie Sophie' to 'remote' for simplicity in workflow communication |
| `claim:candidate:person:dustin:identity:5b93230e1766f045` | `identity` | `identity` | `durable` | Standing FSV co-planner alongside Sophie |
| `claim:candidate:person:dustin:has_influence_from:2d764e7e2162b331` | `has_influence_from` | `preference` | `preference` | TV show Person of Interest's portrayal of AI |
| `claim:candidate:person:dustin:prefers_automation_solutions_for_managing_chats_and_projects:d16ba0d913fa0859` | `prefers_automation_solutions_for_managing_chats_and_projects` | `preference` | `preference` | automation solutions |
| `claim:candidate:person:dustin:intends_to_build_a_local_agent_to_interact_with_files:19a960723722c6a2` | `intends_to_build_a_local_agent_to_interact_with_files` | `preference` | `preference` | local agent to interact with files |
| `claim:candidate:person:dustin:preference:a76ce0b93f4bb381` | `preference` | `preference` | `preference` | seeks cheapest hosting option for Open WebUI deployment |
| `claim:candidate:person:dustin:prefers_project_scope_limitation_to_mental_only:7202fa16b957f37f` | `prefers_project_scope_limitation_to_mental_only` | `preference` | `preference` | I meant for this project Mental only |
| `claim:candidate:person:dustin:prefers_raw_historical_export_without_roles_rules:994fe2c02449c802` | `prefers_raw_historical_export_without_roles_rules` | `preference` | `preference` | I don't want to give it roles, I kind of just want to give it the history of ... |
| `claim:candidate:person:dustin:seeks_universal_command_for_standardized_extraction:5eef07cf7d0df3b1` | `seeks_universal_command_for_standardized_extraction` | `preference` | `preference` | Give me a command I can enter into every single one of my projects to pull ou... |
| `claim:candidate:person:dustin:has_preference:cc1f773c06438c8f` | `has_preference` | `preference` | `preference` | prefers a long-term, iterative development approach over immediate large-scal... |
| `claim:candidate:person:dustin:prefers:9deb861caa92af27` | `prefers` | `preference` | `preference` | AI features that can interact with Google products (e.g., looking at emails, ... |
| `claim:candidate:person:dustin:prefers:90c647c2cb5e462f` | `prefers` | `preference` | `preference` | automation for monitoring Samsung phone deals starting February 20th, with pr... |
| `claim:candidate:person:dustin:demands_ai_agent_capabilities:05ef8afd76a04649` | `demands_ai_agent_capabilities` | `preference` | `preference` | access to local files, system control, app interaction, and browser automation |
| `claim:candidate:person:dustin:prefers_document_to_contain_everything_discussed:5e9d2647e9112713` | `prefers_document_to_contain_everything_discussed` | `preference` | `preference` | everything discussed |
| `claim:candidate:person:dustin:prefers_tone:2bbd93ecef2f3ab5` | `prefers_tone` | `preference` | `preference` | professional and friendly |

**Representative Source Evidence:**
- *"I want the best AI in the best role"*
- *"Maybe we should stop calling it Josie Sophie and just call it remote because that seems to be easier."*

---

## Domain 10: Hardware Architecture & Sourcing

### Family 10.1: Advantech Mini-ITX Build & Intel i7-7700 Platform

**Proposed Consolidated Memory:**  
> *"Dustin built and configured a compact Advantech Mini-ITX system utilizing an Intel Core i7-7700 processor for energy-efficient, low-power continuous operation."*

- **Supporting Candidates (2):** `claim:candidate:person:dustin:preference:4a0334c733f8aba5, claim:candidate:person:dustin:preference:2cb927d57a4e5c12`
- **Evidence Strength:** 4 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2026-07-23
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:preference:4a0334c733f8aba5` | `preference` | `preference` | `durable` | prefers i7-7700 over i7-7700K for Advantech build |
| `claim:candidate:person:dustin:preference:2cb927d57a4e5c12` | `preference` | `preference` | `durable` | prefers compact Mini-ITX case for Advantech build |

**Representative Source Evidence:**
- *"**Get the i7-7700, not the 7700K.**"*
- *"I7 7700 or 7700k"*

---

### Family 10.2: Value Hardware Procurement, High-VRAM GPUs & Sourcing Philosophy

**Proposed Consolidated Memory:**  
> *"Dustin prioritizes price-to-VRAM efficiency for local AI builds, seeking used enterprise workstations (Dell Precision T7820/T7600, Lenovo P720) and high-VRAM cards (RTX 3090 24GB, Intel Arc A770 16GB) on secondary markets rather than expensive new consumer rigs."*

- **Supporting Candidates (34):** `claim:candidate:person:dustin:prefers:0f3f2d852cc0a97b, claim:candidate:person:dustin:preference:c8f9d1d52605a23b, claim:candidate:person:dustin:prefers_pc_resale_strategy:33787280b1dab592, claim:candidate:person:dustin:prefers_local_model_memory:186e9ce707620502, claim:candidate:person:dustin:preference:94a7d6204d886f17, claim:candidate:person:dustin:has_preference:679f6246a8760714` and 28 more...
- **Evidence Strength:** 34 evidence reference(s) across 23 conversation(s)
- **Temporal Range:** 2025-06-30 to 2026-08-25
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers:0f3f2d852cc0a97b` | `prefers` | `preference` | `durable` | purchasing used hardware from eBay |
| `claim:candidate:person:dustin:preference:c8f9d1d52605a23b` | `preference` | `preference` | `preference` | Considering RTX 3060 12GB as alternative if A2000 unavailable |
| `claim:candidate:person:dustin:prefers_pc_resale_strategy:33787280b1dab592` | `prefers_pc_resale_strategy` | `preference` | `preference` | prefers selling PC builds as a whole unit rather than parting out individual ... |
| `claim:candidate:person:dustin:prefers_local_model_memory:186e9ce707620502` | `prefers_local_model_memory` | `preference` | `preference` | prefers running a local AI model with larger memory and VRAM capacity |
| `claim:candidate:person:dustin:preference:94a7d6204d886f17` | `preference` | `preference` | `preference` | seek RTX 3060 GPU acquisition |
| `claim:candidate:person:dustin:has_preference:679f6246a8760714` | `has_preference` | `preference` | `preference` | favor Intel processors over Ryzen due to better used market value and price/p... |
| `claim:candidate:person:dustin:has_preference:f3132b67a2535592` | `has_preference` | `preference` | `preference` | design system with GPUs as intentional performance constraint |
| `claim:candidate:person:dustin:no_riser:00aded95c7e0a46b` | `no_riser` | `preference` | `preference` | no riser |
| `claim:candidate:person:dustin:has_preference:2aa5dbc15446d3af` | `has_preference` | `preference` | `preference` | cheap setup |
| `claim:candidate:person:dustin:has_preference:03c256e5fc551d7c` | `has_preference` | `preference` | `preference` | minimum VRAM for Josie goals |
| `claim:candidate:person:dustin:has_preference:65b1daaf859f83ad` | `has_preference` | `preference` | `preference` | avoid running two boxes |
| `claim:candidate:person:dustin:prefers:489fea7a27f66f74` | `prefers` | `preference` | `preference` | single GPU setup |
| `claim:candidate:person:dustin:has_preference:326ccffd3f373eaf` | `has_preference` | `preference` | `preference` | prefers cheapest hardware setups to achieve AI goals |
| `claim:candidate:person:dustin:intends_to_acquire:b6bf702aa092994a` | `intends_to_acquire` | `preference` | `preference` | cheap intel arc 16gb or higher |
| `claim:candidate:person:dustin:considers:eca1a523b687eeaa` | `considers` | `preference` | `preference` | NVIDIA GPUs for a cheaper setup around $300 |
| `claim:candidate:person:dustin:prefers:45bec01b978c7bdb` | `prefers` | `preference` | `preference` | used B550/Ryzen tower over Xeon/X99 when AM4 systems are available on Marketp... |
| `claim:candidate:person:dustin:prefers:63f67b2dec960b86` | `prefers` | `preference` | `preference` | lower power consumption for a mini form factor with 126 TOPS performance |
| `claim:candidate:person:dustin:estimates:16267e6f52b48476` | `estimates` | `preference` | `preference` | maximum RAM on the board is likely 96 or 128 GB |
| `claim:candidate:person:dustin:has_preference:551893a3c7208503` | `has_preference` | `preference` | `preference` | prefers Gideon's cost-effectiveness for processors and DDR4 memory over Minus... |
| `claim:candidate:person:dustin:has_preference:e6f9df8e01e0da6b` | `has_preference` | `preference` | `preference` | current goals do not require heavy AI training or parallel workloads |
| `claim:candidate:person:dustin:prefers_smaller_form_factor_systems:d675ba38b3f7cbf8` | `prefers_smaller_form_factor_systems` | `preference` | `preference` | prefers smaller form factor systems |
| `claim:candidate:person:dustin:acknowledges_need_for_substantial_power_with_egpu:d2472a5fc7d89e30` | `acknowledges_need_for_substantial_power_with_egpu` | `preference` | `preference` | acknowledges need for substantial power with eGPU |
| `claim:candidate:person:dustin:plans:42a36d1b58f4b10c` | `plans` | `preference` | `preference` | delay GPU purchase for 6-12 months |
| `claim:candidate:person:dustin:needs:1f1556e66392136a` | `needs` | `preference` | `preference` | LEDs for GidXeon |
| `claim:candidate:person:dustin:identifies_as:c6dd02a4c5457aae` | `identifies_as` | `identity` | `durable` | Gideon as a flashed AI/PC/system from the future |
| `claim:candidate:person:dustin:identifies_as:e74b9d83653abb0c` | `identifies_as` | `identity` | `durable` | maintaining Sophie as the conversational interface while Gideon serves as a s... |
| `claim:candidate:person:dustin:wants:30cb84db9205d1f4` | `wants` | `preference` | `preference` | RGB lighting and a white case |
| `claim:candidate:person:dustin:seeks:965dd750070ed1ab` | `seeks` | `preference` | `preference` | best AI-performance system around $500 regardless of brand, size, or age |
| `claim:candidate:person:dustin:preference:81412ff6e71e9788` | `preference` | `preference` | `preference` | No Plex |
| `claim:candidate:person:dustin:has_preference:286747ebf33c335f` | `has_preference` | `preference` | `preference` | build an AI system using the Lenovo ThinkStation P720 as a base |
| `claim:candidate:person:dustin:has_preference:72420b447f659274` | `has_preference` | `preference` | `preference` | compare this system to all previous AI builds for evaluation |
| `claim:candidate:person:dustin:prefers:3729926aa6d5bb12` | `prefers` | `preference` | `preference` | 256 GB RAM |
| `claim:candidate:person:dustin:preference:214404ba8f92c4cd` | `preference` | `preference` | `preference` | prefers Intel over AMD |
| `claim:candidate:person:dustin:prefers:080c304df63931e2` | `prefers` | `preference` | `preference` | Intel i7 processors |

**Representative Source Evidence:**
- *"Uh check out eBay for all of these lovely things or different options. I have no problem used cuz eBay usually has a pretty good guarantee for getting your m..."*
- *"I might just go ahead and do that next. But there's something very appealing about being able to fit all this in the stock box with the stock power supply."*

---

## Domain 11: Home, Vehicle & Lifestyle

### Family 11.1: Trusted Hardware Brands (Home Depot, Echo, Ryobi)

**Proposed Consolidated Memory:**  
> *"Dustin trusts Home Depot for home improvement sourcing and prefers Echo and Ryobi power equipment for maintenance tasks."*

- **Supporting Candidates (3):** `claim:candidate:person:dustin:has_trust_in:270d19a94a40ef88, claim:candidate:person:dustin:has_trust_in:092c79e8f80e559e, claim:candidate:person:dustin:has_trust_in:ce409c401c60f34c`
- **Evidence Strength:** 3 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2026-07-25
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:has_trust_in:270d19a94a40ef88` | `has_trust_in` | `preference` | `preference` | Ryobi |
| `claim:candidate:person:dustin:has_trust_in:092c79e8f80e559e` | `has_trust_in` | `preference` | `preference` | Echo |
| `claim:candidate:person:dustin:has_trust_in:ce409c401c60f34c` | `has_trust_in` | `preference` | `preference` | Home Depot |

**Representative Source Evidence:**
- *"I bought the Allstate insurance, they won't cover it, and Ryobi won't cover it. It's really fucking pissing me off."*
- *"I don't know how much I trust Echo."*

---

### Family 11.2: Vehicle Organization & Logistics (Subaru Forester / Modular Totes)

**Proposed Consolidated Memory:**  
> *"Dustin utilizes a 2024 Subaru Forester organized with modular GSC heavy-duty flip totes for transport, fieldwork, and inventory logistics."*

- **Supporting Candidates (1):** `claim:candidate:person:dustin:preference:b4b982f79498a3ad`
- **Evidence Strength:** 1 evidence reference(s) across 1 conversation(s)
- **Temporal Range:** 2025-12-09
- **Relationship:** `new`
- **Recommendation:** `APPROVE WITH EDIT`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:preference:b4b982f79498a3ad` | `preference` | `preference` | `preference` | prefers Subaru EyeSight safety system over Toyota equivalents |

**Representative Source Evidence:**
- *"I really love subaru eyesight for steering assist. Wifes toyota equivalent sucks by comparison and saftey"*

---

### Family 11.3: Automotive Care & Detailing Products

**Proposed Consolidated Memory:**  
> *"Dustin maintains vehicles using professional detailing products, preferring Adam's Polishes Ceramic Spray and CarPro Perl for protective maintenance."*

- **Supporting Candidates (3):** `claim:candidate:person:dustin:prefers:99830263d7a5f73b, claim:candidate:person:dustin:prefers:8e649ef178a8eccf, claim:candidate:person:dustin:prefers_carpro_perl_as_interior_dressing:701703008a0a2ae1`
- **Evidence Strength:** 3 evidence reference(s) across 2 conversation(s)
- **Temporal Range:** 2025-08-16 to 2026-01-04
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:prefers:99830263d7a5f73b` | `prefers` | `preference` | `preference` | Adam's Polishes Ceramic Spray |
| `claim:candidate:person:dustin:prefers:8e649ef178a8eccf` | `prefers` | `preference` | `preference` | topper products compatible with ceramic coatings rather than wax-based altern... |
| `claim:candidate:person:dustin:prefers_carpro_perl_as_interior_dressing:701703008a0a2ae1` | `prefers_carpro_perl_as_interior_dressing` | `preference` | `preference` | CarPro Perl |

**Representative Source Evidence:**
- *"Sound like Adams would be the best all around solution to me"*
- *"The reason I ask for alternatives is I don't want a wax, because hopefully I'll be able to get as many cars as possible ceramic coated, and I would like some..."*

---

### Family 11.4: Home Maintenance, Energy Savings & Consumer Electronics

**Proposed Consolidated Memory:**  
> *"Dustin approaches home maintenance with a cost-saving, DIY mindset (such as self-installing insulation), trusts local HVAC contractors (Best Virginia, Ashworth), and relies on Samsung mobile devices."*

- **Supporting Candidates (11):** `claim:candidate:person:dustin:intends_to_refine_amazon_review_of_rick_wilton_s_book:68de78c13169eddb, claim:candidate:person:dustin:prefers:1347a77a93029270, claim:candidate:person:dustin:prefers:f80f587d7dbb1bb1, claim:candidate:person:dustin:prefers_to_keep:bf98d1cd7f2512f8, claim:candidate:person:dustin:evaluates:df4aa0fd948c7a9f, claim:candidate:person:dustin:prefers:15d30679193e1396` and 5 more...
- **Evidence Strength:** 11 evidence reference(s) across 10 conversation(s)
- **Temporal Range:** 2025-12-13 to 2026-08-03
- **Relationship:** `new`
- **Recommendation:** `HISTORICAL ONLY`

**Constituent Candidate Claims Breakdown:**
| Candidate Claim ID | Predicate | Category | Durability | Staged Value Proposition |
|:---|:---|:---|:---|:---|
| `claim:candidate:person:dustin:intends_to_refine_amazon_review_of_rick_wilton_s_book:68de78c13169eddb` | `intends_to_refine_amazon_review_of_rick_wilton_s_book` | `preference` | `preference` | redefine the Amazon review |
| `claim:candidate:person:dustin:prefers:1347a77a93029270` | `prefers` | `preference` | `preference` | doing insulation work themselves to save money |
| `claim:candidate:person:dustin:prefers:f80f587d7dbb1bb1` | `prefers` | `preference` | `preference` | current audio setup over new earbuds |
| `claim:candidate:person:dustin:prefers_to_keep:bf98d1cd7f2512f8` | `prefers_to_keep` | `preference` | `preference` | cat trees and ottoman |
| `claim:candidate:person:dustin:evaluates:df4aa0fd948c7a9f` | `evaluates` | `preference` | `preference` | AquaCare 8-Setting High-Pressure Handheld Shower Head |
| `claim:candidate:person:dustin:prefers:15d30679193e1396` | `prefers` | `preference` | `preference` | never-change style air purifier |
| `claim:candidate:person:dustin:is_a_barbecuer:39ffed81dd7bd0fa` | `is_a_barbecuer` | `identity` | `durable` | Dustin identifies as a barbecuer |
| `claim:candidate:person:dustin:needs:754753dd23bba2e2` | `needs` | `preference` | `preference` | three cameras (one on self, one on other person, one for both) |
| `claim:candidate:person:dustin:prefers_using:93780a3896282619` | `prefers_using` | `preference` | `durable` | Best Virginia and Ashworth for HVAC services |
| `claim:candidate:person:dustin:has_preference:3d0b2974e4fb76d2` | `has_preference` | `preference` | `preference` | presenting the tribute on an 8x11 sheet of paper framed with a purple-y graph... |
| `claim:candidate:person:dustin:prefers:be2e4680aa28005b` | `prefers` | `preference` | `preference` | a flowery background with AI assistance |

**Representative Source Evidence:**
- *"redefine the Amazon review"*
- *"we could probably do the insulation ourselves. That would be a lot cheaper."*

---
