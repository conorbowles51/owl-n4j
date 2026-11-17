# State v. Mateo Ruiz — Phone Evidence Report

Prepared for the defence of Mateo Ruiz. Case: "Demo: State v. Mateo Ruiz (synthetic)".

**Conventions**

- **Times.** Every time is local Eastern Daylight Time (America/New_York, UTC−4). The phone records store explicit UTC with no device zone. This report converts each one.
- **Citations.** Citations are Loupe record ids, shortened to their first eight characters. "Phone N" is Loupe's label for each extraction.
- **Fact and inference.** **Fact** marks what a record states. **Inference** marks a reading of records. Nothing here is proven.
- **Grades.** A = direct and corroborated across phones or documents. B = direct on one source. C = suggestive only.

---

## 1. Executive summary

1. **The client's phone never contacts the prepaid phone, the warehouse staff or the buyer.**
   - **Fact.** Phone 1 (Mateo Ruiz, 443-555-0112) has no message, call or group membership with 443-555-0131 (the prepaid phone found in his tow truck). It has none with Okafor (0141, 0142, @dee_o28), Marsh (0161), Cole (0151) or Gary Penn (0171).
   - **Fact.** Its only contact with Kell (0121) concerns bay-4 rent and the 8 June tow.
2. **The prepaid phone travels with Kell, not with Ruiz.**
   - **Fact.** Loupe's co-location tool finds Phone 3 together with Kell's Phone 2 in 42 of 42 shared quarter hours across 14 nights (23 May–7 June). It finds Phone 3 with Phone 1 only on 8 June, the day Ruiz towed Kell's car.
   - **Fact.** On every incident night Phone 3 starts the evening at Kell's apartment cluster.
   - **Fact.** On 9 June Kell asks Ruiz whether he found "a phone in the truck" (1ec57976). He then tells Okafor "the other one. don't text it" (ae7b0d60) in a message he deleted, which was recovered (60857dd1).
   - **Inference.** Kell used Phone 3.
3. **Ruiz's phone is elsewhere on every incident night, and two nights have independent documents.**
   - **Fact.** On N1, N4 and N5 Phone 1 sits at the Ruiz home cluster through the offence window.
   - **Fact.** On N2 Phone 1 is at Hobbet Mill Road, 27 km from Brightwater, matching tow invoice 1187.
   - **Fact.** On N3 Phone 1 is at the emergency department, matching Lucía Ruiz's ER discharge. Phone 1 also created a photo there at 23:24 (7de86ce2).
   - **Fact.** Phone 1 never comes within 2.5 km of Brightwater or within 6.8 km of the Stowell storage site.
4. **The night messages run the same way five times, and the crew is Kell, Okafor, Marsh, Cole and Penn.**
   - **Fact.** 16:10 Kell to Okafor: "tonight. 11… dock 3".
   - **Fact.** 22:05 Phone 3 to Okafor's second number: "bay 4 is clear".
   - **Fact.** 22:10 Phone 3 to Marsh: "be on the gate at 11".
   - **Fact.** 01:40 Phone 3: "unit's open".
   - **Fact.** 09:30 Phone 3 to Gary: "got more for you".
   - **Fact.** Kell's badge opens Dock 3 at 23:06 and 03:12 each night, including the two nights after his firing.
   - **Fact.** The goods go to Stowell unit 212, rented in Cole's name on Kell's card at Kell's request.
5. **The State's identification witness was paid, and her account is shaped.**
   - **Fact.** Marsh's phone receives "You received $500.00 from Travis K." at 09:15 the morning after each theft.
   - **Fact.** Kell's bank shows the matching Pocketwire debits.
   - **Fact.** She told police "Nobody has paid me anything".
   - **Fact.** The day before her interview she wrote "I'll say I saw a tow truck… that's all I'm saying" (14b6f5e6) and "I saw what I saw" (e2257c88).
   - **Fact.** Her N5 incident report recorded no vehicles.
6. **The State's cell-site opinion cannot separate Ruiz from Kell.**
   - **Fact.** The sector it relies on covers both the garage and Kell's apartment. The sector is 2.1 km deep; the two places are 1.0 km apart.
   - **Fact.** The opinion ignores the after-midnight cells at Fenwick Ridge and Tallow Creek Road.
   - **Fact.** The money from Penn's Used Tools goes to Kell by check after every theft.
   - **Fact.** The $650 "bay 4 rent" flows from Kell to Ruiz's shop and began five months before the first theft.

---

## 2. Phone inventory and coverage

| Label | Device and number | Extraction | Records | Content | Deleted, recovered | Gaps |
|---|---|---|---|---|---|---|
| Phone 1 | iPhone (PH1), +1 443-555-0112 | FileSystem, 18 Jun 2024 | 3,075 | 207 messages, 13 calls, 438 location points | 0 | Location points are sparse at night (37 between 22:00 and 05:00 across the whole period) |
| Phone 2 | Android (PH2), +1 410-555-0121 | **Logical**, 15 Jun 2024 | — | 417 messages, 28 calls, 2 e-mails, 448 location points; accounts @tk_nights, travis.kell@example.net | 8 messages | Logical extraction: less complete. No location points between 22:40 and 07:30 on any incident night |
| Phone 3 | "PH3 (prepaid)", +1 443-555-0131 | FileSystem, 17 Jun 2024 | 448 | 81 messages, 10 calls, 11 e-mails, 64 location points, 8 scrambled-message records | 0 | First event 29 Feb 2024; scrambled records not decoded |
| Phone 4 | PH4, +1 410-555-0141 and +1 443-555-0142 ("D.O."); Telegram @dee_o28 | 21 Jun 2024 | — | 114 messages, 32 calls, 23 location points | 0 | Few location points |
| Phone 5 | PH5, +1 443-555-0151 | 24 Jun 2024 | — | 74 messages, 12 calls, 11 location points | 1 message | — |
| Phone 6 | PH6, +1 410-555-0161 | 25 Jun 2024 | 552 | 94 messages, 29 calls, 16 location points | 0 | — |

**Notes on the inventory**

- **Fact.** The State's discovery index (discovery-index-state.pdf) lists seven extractions. E-7 is a second handset recovered from Kell's vehicle, and it is not produced.
- **Fact.** No extraction carries a device time zone (Report.xml headers; phone_timestamps offsets are all 0).

---

## 3. Ownership and attribution

A saved contact name tells us how one phone's owner labelled a number. It does not establish who used the number.

### Phone 1 — Mateo Ruiz (confidence: high)
- **Fact.** The extraction states the owner as Mateo Ruiz and the number as 0112.
- **Fact.** The search inventory, item 6, lists Ruiz's iPhone (search-inventory-ruiz-garage-2024-06-14.pdf).
- **Fact.** Kell's phone saves 0112 as "Mateo garage" (Phone 2).
- **Fact.** Its content is family, the tow trade and the bay-4 tenant.
- **Fact.** Phone 1 created photo IMG_4410 with camera "iPhone (Phone PH1)" (7de86ce2).

### Phone 2 — Travis Kell (confidence: high)
- **Fact.** The stated owner is Travis Kell, number 0121.
- **Fact.** It holds the accounts @tk_nights and travis.kell@example.net.
- **Fact.** Three other phones save 0121 for Kell: "Travis Kell (bay 4)" on Phone 1, "Travis 💙" on Phone 5 and "T" on Phone 4.
- **Fact.** Its Pocketwire and bank notifications match Kell's Kestrel account 7730-554471 (929f9bc0, 22a4a0ff and others; see section 7).

### Phone 3 — prepaid, 443-555-0131 (confidence that Kell used it: moderate to strong, inference)
- **Fact.** No owner is stated in the extraction.
- **The State's case.** It was found in the glovebox of Ruiz's tow truck (search inventory item 1). Kell's proffer calls it Mateo's (kell-proffer-transcript-2024-06-20.docx).
- **What points to Kell:**
  - **Location.** Phone 3 is at the Kell apartment cluster (39.267,−76.680) on every incident night before it moves: N1 7f54f269; N2 855cde12; N3 94f394ee; N4 f4f0bcdf; N5 f748755e.
  - **Location, late May to early June.** From 23 May to 7 June it is at the Kell apartment cluster at 20:35, 21:35 and 22:35 nightly. The co-location tool scores Phone 3 with Phone 2 as "moderate": 42 quarter hours together, 0 apart, 14 nights.
  - **Location, 8 June.** Phone 3 reaches Ferrow Ave at 14:12 (da3436d2), where Kell's car broke down (Phone 2 df12d5e4 at 13:45; tow invoice 1242: Kell rode in the truck cab).
  - **Location, after 8 June.** From then on Phone 3 appears only at or near the garage: 14:55 (b9de6777), 10 June (f2163974, a8a5e9a1), 12 June (46844317, 12afa17b) and 14 June 07:10 (905f393d). That is the tow truck's base. **Inference:** the phone stayed in the truck after Kell left it in the cab.
  - **Messages, 9 June.** Kell to Ruiz at 17:20: "did you find a phone in the truck? think I left it in the cab" (1ec57976). Ruiz: "didn't see anything, I'll check tomorrow" (33abe1c7). Kell to Okafor at 19:42: "left something in the tow truck, need it back" (60857dd1, deleted on Phone 2 and recovered; Phone 4 copy 0e5afb34). At 19:51: "the other one. don't text it" (ae7b0d60 / c28f8471).
  - **Contact labels.** Marsh saves 0131 as "T 2", a second "T" (Phone 6). Phone 3 saves Marsh as "L", Okafor's second line as "D.O." and Penn as "G".
  - **Bank records.** The Stowell unit that Phone 3 announces as "unit's open" is paid by Kell's card ending 4471 (stowell-rental-agreement-unit-212.pdf; Kell ledger 6f6be9d6).
- **Against Kell, or neutral:**
  - The phone was physically in Ruiz's truck.
  - The State's evening cell sector covers both the garage and Kell's address (section 7).
- **Recycled number.**
  - **Fact.** Phone 4 holds 2022 calls with 0131 under the name "Curtis Fallowby" (94d202a3, 427eb7f1, b72adf6a; March–November 2022).
  - **Fact.** Phone 3's own first event is 29 February 2024.
  - **Inference.** The number likely had an earlier subscriber. "Curtis Fallowby" is a stale label, not the 2024 user.
- **Fact.** Phone 1 never contacts 0131. Phone 3 never contacts 0112.

### Phone 4 — Desmond Okafor (confidence: high)
- **Fact.** The stated owner is Okafor. It holds 0141, Telegram @dee_o28, and a second number, 0142 ("D.O.").
- **Fact.** The 0142 line is used only with Phone 3 and first appears on 29 February 2024, the same day Phone 3's history begins.
- **Fact.** Kell's phone saves him as "Dee"; Okafor's phone saves Marsh as "Lena M" and Kell as "T".

### Phone 5 — Brianna Cole (confidence: high)
- **Fact.** The stated owner is Cole, number 0151.
- **Fact.** The Stowell rental agreement gives 443-555-0151 as the occupant's phone.
- **Fact.** Kell's phone saves her as "Bri".

### Phone 6 — Lena Marsh (confidence: high)
- **Fact.** The stated owner is Marsh, number 0161.
- **Fact.** Phone 4 saves the number as "Lena M"; Phone 3 saves it as "L".

### 443-555-0181 "Mateo 🔧" (not a seized phone; attribution open)
- **Fact.** It exists only on Phone 4.
- **Fact.** It carries a brakes job: "bring it by 9. it's me and the lift all morning, Mateo" (749a1d5b, 23 May) and "pads and rotors done. $180" (75c1d60d, 25 May).
- **Fact.** It also carries late calls: 26 Mar 01:29, 1,380 s (e7b5b310); 19 May 22:10, 590 s (635bd497); 28 May 01:27, 596 s (4d993776).
- **Fact.** It is neither Ruiz's mobile (0112) nor his shop line (0110). It never appears on Phone 1.
- **Fact.** Neither Ruiz account in the ledger shows a $180 receipt or any payment from Okafor.
- **Inference.** It may be another mechanic named Mateo, or the State may argue it is a second Ruiz phone. Only subscriber records can settle it.

---

## 4. Contact network

**Fact.** Counts are distinct message and call events across all six extractions.

| Party | Talks with | Notes |
|---|---|---|
| Ruiz (0112) | Lucía (0113): 119 messages, 5 calls. Mamá (0114): 43 messages, 4 calls. Harold Vint (0191): 28 messages, 3 calls. Kell (0121): 17 messages, 1 call | No group chat. No contact with 0131, 0141, 0142, @dee_o28, 0151, 0161 or 0171 |
| Kell (0121, @tk_nights) | Okafor, Cole, Penn, Ruiz | Telegram "night crew" = Kell and Dee only. WhatsApp "Group 4" = Kell, Dee, Gary, Bri |
| Phone 3 (0131) | D.O. 0142: 45 messages. L / Marsh 0161: 20 messages, 4 calls. G / Penn 0171: 16 messages, 6 calls | Nobody else |
| Okafor (0141, 0142, @dee_o28) | Kell, Phone 3, Marsh, Cole, "Mateo 🔧" 0181 | 0142 used only with Phone 3 |
| Marsh (0161) | Phone 3 (10 messages on Phone 6), Joanie 0162, Okafor | Never talks with Kell's 0121 |
| Cole (0151) | Kell, Okafor | — |

**Inference.** The network has two separate parts. Ruiz's family-and-trade circle touches the others only through Kell's tenancy. The crew circle (Kell, Phone 3, Okafor, Marsh, Cole, Penn) never reaches Ruiz.

---

## 5. Incident-night reconstruction

**Fact.** Each police report records the same scene:
- Brightwater Logistics Unit 7, 2200 Fenwick Ridge.
- Guard Lena Marsh and loader Desmond Okafor on shift.
- No vehicles logged after 22:45.
- Dock 3 door closed but unlocked.
- Camera 4 offline since February.

**Fact.** The badge log (brightwater-badge-log-2024.csv) shows each night:
- Okafor B-20417 enters at the staff entrance at 22:48 and exits at 06:02.
- Kell B-11032 is granted at Dock 3 at 23:06 and 03:12.

**Fact.** The Stowell gate log (code 2120) records entry at about 02:40 each night.

The following sequence repeats on all five nights (record ids per night below):

| Local time | Event | Phones |
|---|---|---|
| 16:10–16:15 | "tonight. 11. same as before" / "ok. dock 3 again?" / "dock 3" | Kell ↔ Okafor, Telegram night crew |
| 22:05 / 22:07 | "bay 4 is clear" / "ok" | Phone 3 ↔ D.O. 0142 |
| 22:10 / 22:12 | "be on the gate at 11. same as before" / "ok" | Phone 3 ↔ Marsh |
| 22:15 | Phone 3 at Kell apartment cluster | Phone 3 |
| 22:30, 22:40 | Phone 2 at Kell apartment cluster (last points until 07:30) | Phone 2 |
| 22:50 | Phone 6 at Brightwater | Phone 6 |
| 23:06 | Kell badge, Dock 3 | badge log |
| 23:30, 01:30 | Phone 4 at Brightwater | Phone 4 |
| 00:40 | Phone 3 at Brightwater | Phone 3 |
| 01:40 / 01:43 | "unit's open" / "on the way" | Phone 3 ↔ D.O. |
| 02:30 | Phone 3 at Stowell | Phone 3 |
| ~02:40 | Stowell gate entry, code 2120 | gate log |
| 02:45 | Phone 4 at Stowell | Phone 4 |
| 03:10 | Phone 6 at Brightwater | Phone 6 |
| 03:12 | Kell badge, Dock 3 | badge log |
| 09:15 next day | "You received $500.00 from Travis K." | Phone 6 |
| 09:30 / 09:41 next day | "got more for you, saturday" / "same price. come to the back" | Phone 3 ↔ G (Penn) |
| ~10:30–11:40 next day | Phone 2 at Stowell, then at Penn's (inferred); Phone 5 photographs inside Stowell | Phones 2, 5 |

**Inference: Okafor off-site.** Phone 4 is at Stowell at 02:45 while Okafor's badge shows no exit until 06:02. Phone 4 was off-site during the shift, and so, likely, was Okafor.

**Chance check.** One crew member at the warehouse on a shift night is expected. Five nights with the same messages, the same order of places and the same badge times are not chance. Phone 1 takes part in none of it.

### N1 — Friday 15 to Saturday 16 March (CCPD-24-1100; 20 items, $3,300)
- **Crew messages, fact.**
  - Night crew: c73b4872, 611e49d4, f48be660, 99c86cd6, 6c40cacc, 76bac317.
  - "bay 4 is clear": def38f2a / 99065ac3.
  - Gate: f257e290 / 492998c3.
  - "unit's open" / "on the way": 87ec5f98, b38b0c3e / 9f01318b, f9924ecf.
  - Penn: d8481e9b, 4cc11a0b.
- **Crew places, fact.**
  - Phone 3: 7f54f269, 7b30c9fe, 3ff700af.
  - Phone 4: 4eac2de1, ad07d733, 74a997b3.
- **Kell ↔ Cole, fact.**
  - 02:05 "loaded" (c55075de).
  - 10:50 "they're all in 212, took pics" (5dd4a12d).
- **Media, fact.**
  - Phone 5 receives IMG-20240316-WA0003.jpg at 02:05 (e4b81bef). Its EXIF names camera "Phone PH2" (Kell's phone) and GPS at Brightwater (36da7024).
  - Phone 5 creates IMG_2041 at Stowell at 10:48 (0e87b7d3 / b173c1e5).
- **Ruiz, fact.**
  - Lucía: "¿Vienes a cenar?" (8c58f4f4). Ruiz: "closing up now, 20 min" (cbabd349).
  - Phone 1 at the Ruiz home cluster through the window: 44dc8c4b, 8892a054, 17497c1d, a9039a87, ac0e2d64.
  - Phone-only device activity at home: 23:01, 23:42, 00:22 (connectivity 20c2cc73, 11554f16, 06f7c506); 00:58 (app use 4f938651); 02:05 (device event 73d0e45f).

### N2 — Friday 12 to Saturday 13 April (CCPD-24-1137; 16 items, $4,184)
- **Crew messages, fact.**
  - Night crew: c60a97cb, 030a62b1, 46661df7, ce9fcf5c, 69c9b43e, fce4ea2b.
  - Then aa853dde / d0888635; c5c36737 / 141481c7; d3f368fa, 76d79405 / b791e1ff, 1af7f429; 47e9e103, dd3183b7.
- **Crew places, fact.** Phone 3: 855cde12, 4985a566, ddd8a335.
- **Kell ↔ Cole, fact.** "212 again. it's getting full" (735572fe).
- **Media, fact.** Phone 5 creates IMG_2107 at Stowell at 10:51 (2262b795).
- **Ruiz, the tow call to Hobbet Mill Road, fact.**
  - 22:31 Vint calls, 140 s (15ef7af0).
  - 22:33 to Lucía: "tow call…" (15d2cd42).
  - Vint: "Hobbet Mill past the reservoir sign" (b5ae6ee3). Ruiz: "ok, 40 minutes" (c123d03d).
  - Phone 1 positions: garage 22:40 (c2c1ed6c); en route 23:00 (6dc4be4b); Hobbet Mill 23:20–00:40 (9e3bf7d1, 3dd201c7, 88a9b3be, 9bb75aa0, 1cc6662e); garage 01:15 (30703040); home 01:50 (468919b3).
  - 01:52 to Lucía: "back home" (c7a83af5).
- **Documents, fact.**
  - Tow invoice 1187 records the call at 22:31, on scene at 23:20 and cleared at 01:15 on 13 April; driver Mateo Ruiz, truck 7TW-0142.
  - Vint paid $185 on 15 April (Ruiz shop ledger fe746a2a).
- **Distance, fact.** Hobbet Mill is 27.4 km from Brightwater.

### N3 — Friday 3 to Saturday 4 May (CCPD-24-1174; 18 items, $4,762)
- **Crew messages, fact.**
  - Night crew: fa83e757, d061cd6d, 99bc6e59, 9c33e9e8, ed590c70, 0aa1e013.
  - Then d597b819 / 04d2b354; 4ef943b7 / 714195a0; 8beddeff, 9cb12e2b / c9479319, 2c6b902b; 8af7a6b0, 7e6115b5.
- **Crew places, fact.** Phone 3: 94f394ee, 90e3f349, cac21e80.
- **Kell ↔ Cole, fact.**
  - 01:58 "count these for me tomorrow" (105df170).
  - Reply "counted. 18 boxes" (a2613f58). The police report lists 18 items.
- **Media, fact.**
  - Phone 5 receives IMG-20240504-WA0001.jpg at 01:58 (41aba324). Its camera is "Phone PH2", with GPS at Brightwater (25d1b4e8).
  - Phone 5 creates IMG_2188 at Stowell at 10:52 (43893d24).
- **Kell e-mail, fact.** At 14:20 Kell e-mails "Gary P": "Torvane 20V hammer drill x14, $85 each. Keldar 10in table saw x4, $240 each… check to me" (819b84ac).
  - The N3 loss list holds 14 hammer drills and 4 table saws.
  - The e-mailed prices total $2,150. Penn's check 1066 on 10 May is $4,100, so the amounts do not match.
- **Ruiz, the emergency department, fact.**
  - 22:41 Lucía: "the pain is worse" (80e87685). Ruiz: "getting the car, vamos a Ferrowmere" (3c342e47).
  - Phone 1 positions: home 22:40 (29847c62); emergency department 23:10–03:40 (dbc6cb54, 12bd6d1c, 91f332a1, 6552c96c, 7953abd0, 8bdc648b, f0e21572, 9eef379f, 66e1bf20, 97b5141d); home 04:05 (4483ff9a).
  - 23:25 message to Mamá (ef286ccb).
  - Phone 1 **creates** IMG_4410.JPG at 23:24 with its own camera, GPS at the ED (7de86ce2 / b64843f3).
  - 03:44 "ya nos vamos a casa" (2cdfe82e).
- **Documents, fact.**
  - The ER discharge (er-discharge-2024-05-04.pdf) records arrival at 23:08 and discharge at 03:38. The triage note says Mateo was present throughout.
  - The Ruiz ledger records the ED copay of $150 on 6 May (ebfe78d4).

### N4 — Friday 17 to Saturday 18 May (CCPD-24-1211; 14 items, $4,656)
- **Crew messages, fact.**
  - Night crew: c63ced74, c5e6b9ad, f014a7a4, 04e8c73c, 46ed354a, 6b28637b.
  - Then 3f3230aa / 06eb1f3d; d343472b / ca70a39d; 787d1825, 03383c53 / e0376bc5, 30918cef; c9fa6949, 37e0371d.
- **Crew places, fact.** Phone 3: f4f0bcdf, fd5d4825, e0b06917.
- **Badge, fact.** Kell's badge still opens Dock 3. The HR deactivation request was sent on 20 April (brightwater-hr-termination-kell-2024-04-20.eml).
- **Ruiz, fact.**
  - "movie tonight?" (82929978) / "sí, I'll make popcorn" (8b95f3bb).
  - Phone 1 at the Ruiz home cluster: 42f7490a, 8d83f723, bb36208f, 04d8f94d, 20e0248b.

### N5 — Friday 31 May to Saturday 1 June (CCPD-24-1248; 20 items, $4,780)
- **Crew messages, fact.**
  - Night crew: 0966af71, 86338352, ce36cb16, fff00259, 96f124d6, a422f7bc.
  - Then 00974366 / a27c94fb; 913ab516 / 0c4c77f8; ce4f21b4, 324cf87e / 2c6c0ea3, ac50ec15; 90e58183, 957eb2f4.
- **Crew places, fact.** Phone 3: f748755e, 92e71f04, 8e1c9e6e, 106e00db, d9469482, 0a211457.
- **Kell ↔ Cole, fact.** "last ones fit. Gary said he'd take them next week" (3082cbe4).
- **Media, fact.** Phone 5 creates IMG_2240 at Stowell at 11:05 (33240c9c).
- **Ruiz, fact.**
  - At 21:30 Ruiz texts: "dejé las llaves del camión en la oficina, I'll get them mañana" — he left the truck keys at the office (83aff4e7).
  - Phone 1 at the Ruiz home cluster through the window: bbc3d936, 33c5194b, 981eb312, ee043a07, 68683947.
- **The tow-truck sighting, fact.**
  - This is the only night on which Marsh later reports the RUIZ tow truck. Her supplementary report is dated 3 June; the original N5 report logs no vehicles after 22:45.
  - Kell holds the only key to bay 4 at Ruiz's premises (bay4-lease-2023-10-01.pdf).
- **Inference.** If a tow truck was there, the keys were not with Ruiz, and Ruiz's phone was at home. Whether Kell could reach the office is not shown by any record.

---

## 6. Flagged communications

| # | Local date and time | Phones | Content | Why it matters | Grade | Citations |
|---|---|---|---|---|---|---|
| 1 | Each incident Friday, 16:10–16:15 | Kell ↔ Okafor (night crew) | "tonight. 11. same as before" / "dock 3" | Plans the entry time and door | A | N1 c73b4872 … N5 a422f7bc (section 5) |
| 2 | Each Friday, 22:05 | Phone 3 → D.O. 0142 | "bay 4 is clear" | The only bay-4 reference; the goods then go to Stowell. **Inference:** it reports that bay 4 holds nothing, not that goods go there | A | def38f2a, aa853dde, d597b819, 3f3230aa, 00974366 |
| 3 | Each Friday, 22:10 | Phone 3 → Marsh | "be on the gate at 11. same as before" | Puts the guard in the plan | A | f257e290, c5c36737, 4ef943b7, d343472b, 913ab516 |
| 4 | Each Saturday, 01:40 | Phone 3 ↔ D.O. | "unit's open" / "on the way" | Matches the Stowell gate entries at 02:38–02:50 | A | 87ec5f98 … ce4f21b4 |
| 5 | Each Saturday, 09:30 | Phone 3 ↔ G (Penn) | "got more for you, saturday" / "same price. come to the back" | Fencing; Penn's checks to Kell follow | A | d8481e9b … 957eb2f4 |
| 6 | Each Saturday, 09:15 | Pocketwire → Phone 6 | "You received $500.00 from Travis K." | Pays the guard; contradicts "Nobody has paid me anything" | A | e857592d, 3e01c222, d8e0ee50, 25cf3faa, 7c697932; Kell ledger 2ab64344, 5f071792, 97803e74 |
| 7 | 1 Feb 2024 | Kell → Cole | "can you rent a unit at Stowell tomorrow, in your name. I'll pay with my card" / "why my name?" / "just do it babe, it's for the side work" | Kell sets up the storage under a nominee | A | b432ccf4, ae60427a, 70313123; 2 Feb 37b1d374, 20275457; rental agreement |
| 8 | 16 Mar 02:05; 4 May 01:58 | Kell → Cole | "loaded"; "count these for me tomorrow" with photos taken on Kell's phone camera at Brightwater | Places Kell's camera at the warehouse during the theft. Phone 5 received these images and did not create them | A | c55075de, e4b81bef; 105df170, 41aba324 |
| 9 | 4 May 14:20 | Kell → Penn (e-mail) | "hammer drill x14 … table saw x4 … check to me" | Matches the N3 loss list | A | 819b84ac |
| 10 | 20 Apr 18:30 | Kell → Okafor | "they let me go today. doesn't change anything, my badge still works" | Explains the Dock 3 entries on N4 and N5 | A | 92a60e1e, 17026fb5; badge log; HR e-mail |
| 11 | 9 Jun 17:20 | Kell → Ruiz | "did you find a phone in the truck? think I left it in the cab" | Kell claims the phone later found in the truck | A | 1ec57976 / d4e2f1be; reply 33abe1c7 |
| 12 | 9 Jun 19:42 | Kell → Okafor | "left something in the tow truck, need it back" — **deleted** by Kell, recovered | Deleted after sending; consciousness of guilt is for the court | A | 60857dd1 (Phone 2, recovered); 0e5afb34 (Phone 4, intact) |
| 13 | 9 Jun 19:51 | Kell → Okafor | "the other one. don't text it" | Kell calls the truck phone his "other one" | A | ae7b0d60 / c28f8471 |
| 14 | 9 Jun 20:03 | Okafor → Kell | Voice note PTT-20240609-0001.opus | Not transcribed; content unknown | C | 027c03fe, attachment d81c5462, file ce8f1f79 |
| 15 | 11 Jun 19:10–19:40 | Marsh ↔ Joanie | "I'll say I saw a tow truck. white one, with the name on it. that's all I'm saying" / "Lena did you see one or not" / "I saw what I saw" | Shapes the only identification evidence a day before her interview | A | a49eae4e, bac4a4af, 14b6f5e6, bd2f0b9a, e2257c88 |
| 16 | 11 Jun 09:15 | Cole → Kell | "they arrested you?? what do I do about the unit" | Cole ties the unit to Kell | B | 569f2e3b |
| 17 | 18 May 12:05 | Okafor → Kell | "you good? saw you at Quillan's lol" | See section 8: Kell's phone was at Penn's then | C | 86b52d25 / ec8d622d |
| 18 | 26 Mar 01:29; 19 May 22:10; 28 May 01:27 | 0181 "Mateo 🔧" ↔ Okafor | Long late calls; no content | The State may attribute 0181 to Ruiz; it is not his number | C | e7b5b310, 635bd497, 4d993776 |

---

## 7. Cross-checks with documents and money

### Money follows Kell
- **Kell's account, fact.** After every incident Kell's Kestrel account 7730-554471 shows:
  - $500 Pocketwire to Marsh (2ab64344, 5f071792, 97803e74).
  - $1,200 to Okafor the next day (b02fe788, 33bccbe0, a9e97443).
  - A cash deposit just under $10,000 two days later: $9,800, $9,650, $9,900, $9,750, $9,850 (459c951a, 01fb900b, 796e85d8, plus the statement images). **Inference:** deposits held under the $10,000 reporting line are consistent with structuring.
- **Penn's account, fact.** Penn's Used Tools (Old Ferrow 5518-020931) pays Kell by check:
  - 1043: $3,400, 22 Mar (5b1748d6).
  - 1051: $2,950, 19 Apr (a99c066c).
  - 1066: $4,100, 10 May (5b7d1693).
  - 1072: $3,600, 24 May (872de884).
  - 1080: $3,900, 7 Jun (9713b762).
- **Kell's phone, fact.** Phone 2's notifications mirror each payment: sends 929f9bc0 … c2b73d97; deposits 22a4a0ff … 3c938b97; checks ed833fb2 … 00e3782c.
- **Stolen goods on sale, fact.** Penn's listings export shows Penn sold ten serials from the loss lists: TVN20-118207, KLD-CS7-55024, LMT55-70315, TVN20I-30449, KLD-TS10-8814, TVN20-118312, LMT65-41103, KLD-CS7-55105, TVNK-6627 and LMTSB-2293.
- **Ruiz's accounts, fact.**
  - Ruiz's personal account 0042-118830 shows mortgage, groceries and owner draws of $2,500 twice a month. It shows no unexplained credit.
  - The shop account 0042-118847 shows steady card settlements.
  - No Ruiz account receives money from Penn, Okafor, Marsh or Cole.

### The $650
- **Fact.** "KELL T BAY 4 RENT" of $650 arrives in Ruiz's shop account every month from October 2023 (a0c6c34a … 9294fb00). The amount never changes.
- **Fact.** The lease began on 1 October 2023 (signed 28 September). The first theft was on 15 March 2024.
- **Fact.** The money flows from Kell to Ruiz.
- **Fact.** Each month Phone 1 carries "sent the bay rent" / "got it, thanks Travis".
- **Kell's account versus the records.** Kell's proffer calls the $650 "Mateo's cut". The affidavit relies on the same payments. A cut paid from Kell to Ruiz five months before any theft does not fit the records.

### Ruiz's tools
- **Fact.** Search items 2 and 3 are a drill (TVN20-099812) and a saw (KLD-CS7-40920). Penn's export lists both as sold on 22 May to "M. Ruiz (in store)".
- **Fact.** Ruiz's receipt (item 4) and ledger row 8ee5b10b show the $240 sale. Penn's bank shows "CARD SALE M RUIZ" $240 the same day.
- **Fact.** Neither serial appears on any loss list.
- **Fact.** Carla Ruiz's saw, KLD-CS7-31877 ($95 on 8 May), is not on any loss list either.
- **Fact.** The search found no listed property; bay 4 held pallets and shrink-wrap (item 5).

### Storage and gate
- **Fact.** Stowell unit 212 is rented to Brianna Cole from 2 February 2024. It is paid by Travis Kell's card ending 4471, and Kell is the authorised person.
- **Fact.** The gate entries (16 Mar 02:41, 13 Apr 02:38, 4 May 02:50, 18 May 02:44, 1 Jun 02:47) fall within minutes of Phone 3's 02:30 point and Phone 4's 02:45 point at Stowell.
- **Kell's proffer.** "Never rented storage".

### Cell-site report (state-cell-site-report.pdf)
- **Fact.** The evening activity on 0131 uses cell 4471 sector 2. The report says this sector covers the garage and Larkmont Apartments (Kell's address), and gives the sector as about 2.1 km deep.
- **Fact.** Loupe's location clusters put the Kell apartment cluster 1.00 km from the garage cluster and 2.06 km from the Ruiz home cluster.
- **Inference.** The sector cannot tell Kell's home from Ruiz's garage.
- **Fact.** After midnight the phone uses 5180-1 (Fenwick Ridge) and 6022-3 (Tallow Creek Road). The opinion does not discuss them.
- **Fact.** No drive test was done.
- **Inference.** These match Phone 3's own points at Brightwater at 00:40 and Stowell at 02:30. The report does not say where 6022-3 serves.

### Kell's proffer against the records

| Proffer statement | Records |
|---|---|
| "The goods always went to bay 4" | Cole's 212 messages, the gate log, Phone 5's photos and the "unit's open" messages place the goods at Stowell |
| "Never rented storage" | Kell's card pays unit 212; he asked Cole to rent it (b432ccf4) |
| The prepaid phone is Mateo's | Kell asked Ruiz for "a phone in the truck" and called it "the other one" |
| "Nobody at the warehouse" helped | Okafor's night-crew messages and payments; Marsh's gate messages and payments |

---

## 8. Explained items and decoys

### Stock phrases
- **Fact.** About 800 short messages recur on every phone, including the Ruiz family chats. Examples: "keep this between us", "half now, half on Friday", "meet at the usual place", "did you get the package", "left it by the side door", "that price is too high". They appear between unrelated parties at random times. Examples: Mateo to Mamá "left it by the side door", 8 June (da100c0e); Lucía to Mateo, the same phrase, 15 June (5220b795); Mateo to Mamá "not tonight, tomorrow works", 13 June (166ffb6e).
- **Inference.** This is background traffic. It carries no weight.

### Deleted messages
- **Fact.** Phone 2 has eight deleted messages and Phone 5 has one. Only 60857dd1 has case content; the other eight are stock phrases.

### Quillan's, 18 May
- **Fact.** Phone 1 is at Quillan's at 11:20, 11:32 and 11:44 (2ca50252, 9f7d60fb, e3b9a95b). Ruiz paid $86.40 there (6fdf5e61).
- **Fact.** Phone 4 is there at 11:35 and 11:50 (4b0c0529, 2dbf0ffd).
- **Fact.** At 12:05 Okafor tells Kell "saw you at Quillan's lol" (86b52d25).
- **Fact.** Kell's Phone 2 is at Penn's at 11:40 (f04be52f), 17.8 km away.
- **Inference.** Either Okafor saw someone else or the remark is loose. One overlap at a busy store on a Saturday midday is ordinary chance. It happens once in four months, and no message or call links Phone 1 and Phone 4 at any time.

### "Mateo 🔧" (0181)
- **Fact.** See section 3. The name is a label on Okafor's phone, not ownership. The number belongs to no Ruiz phone.

### "Curtis Fallowby" on 0131
- **Inference.** A stale label from an earlier user of a recycled number.

### The 8 June co-location
- **Fact.** Phones 1, 2 and 3 meet once, at Ferrow Ave at 14:10–14:25. That is the recorded tow (tow invoice 1242; Kell's request 1f65175d; call 97e57a08; Ruiz to Lucía "tow job, Travis from bay 4", c9596d19).
- **Inference.** It is the moment the prepaid phone entered the truck. It is not evidence of a joint enterprise.

### "bay 4 is clear"
- **Inference.** The message uses Ruiz's premises in name only. No night's goods go there.

### Bank-statement text artefact
- **Fact.** The loaded text of Kell's March statement splits the cash deposit as "800.00 / 9". The ledger row reads $9,800 correctly.

---

## 9. What this means for the defence

1. **Attribution of Phone 3 is the centre of the State's phone case, and the records point to Kell.** Develop the 8–9 June sequence and the 14-night co-location with Phone 2. Use Kell's own words: "a phone in the truck", "the other one", and the deleted 19:42 message. Ruiz's phone never contacted the prepaid phone or any crew member.
2. **Alibi on every night.**
   - N2 and N3 rest on third-party documents (the tow invoice and Vint's payment; the ER discharge and copay) and on a photo Ruiz's phone created.
   - N1, N4 and N5 rest on Phone 1's home location and ordinary home messages.
   - N5 adds the truck keys left at the office.
   - **Caution.** Phone location on N1, N4 and N5 shows where the phone was, not the man. The prosecution will say so.
3. **Impeach Marsh.**
   - Five payments from "Travis K." against "Nobody has paid me anything".
   - Gate messages from the "T 2" number on N4 and N5, after Kell's firing (d343472b / ca70a39d, 913ab516 / 0c4c77f8), against "I haven't talked to him since he left". This point holds only if Phone 3 is attributed to Kell (inference).
   - The 11 June chat that scripts her account.
   - Her own N5 report, which logs no vehicles.
4. **Impeach Kell.** Every core proffer claim is contradicted by documents (table in section 7).
5. **Answer the money theory.** The $650 is rent paid to Ruiz since October 2023. The theft proceeds run Penn → Kell and Kell → Marsh and Okafor. Ruiz's tools are receipted and not stolen.
6. **Attack the cell-site opinion.** The sector covers both addresses. The opinion leaves out the after-midnight cells, which place the phone at the warehouse and the storage site, and no drive test was done.

---

## 10. Limits, gaps and recommended next steps

### Limits
- Phone 2 is a Logical extraction and has no overnight location on incident nights. A full file-system extraction may hold more, including deleted Telegram content.
- Phone 3's eight scrambled-message records and its 11 e-mails (generic subjects) are not decoded.
- The Okafor voice note of 9 June 20:03 (027c03fe) is real Ogg Opus audio with no transcript in Loupe. Its content is unknown.
- Kell's May 2024 statement (kell-2024-05.pdf) is marked "Page 1 of 2", but the produced file has one page.
  - The May rows are missing from the ledger entirely; May figures in this report come from the page image.
  - Page 2 should hold the 24 May check deposit ($3,600), which Phone 2's notification fcd6632b shows.
- Kell's original April statement is not in the ledger; State's Exhibit 14, with identical content, is used instead.
- Phone location points are periodic. Gaps between points are not evidence of absence.
- The place names "Kell apartment cluster", "Ruiz home cluster", "garage" and "Penn's" are inferred from routine. The Brightwater, Stowell, ED, Hobbet Mill and Quillan's points match document addresses or receipts.

### Requests and subpoenas
1. **Extraction E-7**, the second handset from Kell's vehicle, listed in the State's discovery index and not produced. Ask for the image, the report and the chain of custody.
2. **Subscriber and activation records** for 443-555-0131: purchase point, payment, activation date, and any earlier subscriber ("Curtis Fallowby", 2022). Ask for the same records for 443-555-0142 and 443-555-0181.
3. **Carrier CDRs with cell sites** for 0131, 0121 and 0112 on all five nights, and an independent drive test of cells 4471-2, 5180-1 and 6022-3.
4. **A full file-system re-extraction of Phone 2.**
5. **Page 2 of Kell's May 2024 Kestrel statement** and the original April statement.
6. **Pocketwire records** for the Travis K. → Lena Marsh and → Desmond Okafor transfers.
7. **Kestrel cash-deposit records.** Deposit slips, branch video and any currency transaction or suspicious-activity filings for the five sub-$10,000 deposits.
8. **Brightwater records.** The badge-system audit showing why B-11032 stayed active after the 20 April deactivation request, and the camera 4 maintenance record.
9. **Stowell records.** Gate video for the five entries and the card-on-file records for unit 212.
10. **Penn's Used Tools.** Buyer records for the ten stolen serials, the deposit images for checks 1043–1080, and Penn's purchase records from Kell.

### Interviews
- **Harold Vint**, on the N2 tow.
- **The ER staff** named on the triage note, for N3.
- **Joanie (0162)**, on the 11 June chat.
- **Brianna Cole**, on the unit rental and the 1 February request.
- **The mechanic behind 0181**, once subscriber records identify him.
- **Ruiz**, on the following:
  - Who can reach the garage office and the truck keys, including through bay 4.
  - The 9 June phone question.
  - Whether he ever saw a phone in the cab.

### Forensic work
- Transcribe the 9 June voice note with a human listener and record the transcription method.
- Decode Phone 3's scrambled records.
- Examine the EXIF and hash of every image Cole received against Phone 2's camera roll.
