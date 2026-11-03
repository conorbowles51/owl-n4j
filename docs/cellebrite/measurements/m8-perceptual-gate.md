# 05 section 11.6, perceptual-tier gate: measured result (counts only)

Gate: build the perceptual tier only if a sample of 20 attachment pairs known to be the same message (approach 2
`both_sides` media messages) shows exact MD5 failing on at least a quarter of them.

**Verdict: gate not met; perceptual tier not built on this gate.** The server corpus does not hold 20 such
pairs. With the matching rule as specified there is 1 pair (MD5 equal). With 05's own K3 rule, which also
accepts a group chat's participants, there are 14 pairs where both sides have an MD5, and 1 of 14 (7.1%) differs.
With the loosest rule tried there are 17 such pairs and 3 of 17 (17.6%) differ. No rule reaches 20 pairs, and
none reaches 25%. Images, the only media the perceptual tier would handle, are too few to decide on: 1 of 3
differs under 05 K3 and 3 of 6 under the loosest rule. **What would reverse this:** a case with at least
20 image pairs where both sides have an MD5 and at least 25% of them differ.

## Data

Server corpus `/mnt/owl-data/cellebrite-corpus`, all multi-phone reports. Used:

- the 10-report case: A-C1a, A-C1b, A-C2, A-C3, A-C4, A-C5, A-C6, A-C7, A-C8, A-C9 (P02 to P11);
- the 3-phone case: B-C1, B-C2, B-C3 (P12 to P14).

All 45 phone pairs within the 10-report case and all 3 pairs within the 3-phone case were matched in both
directions. Every result pair is counted; there is no sampling.

## Method

- **Pass 1, per phone** (`p8_extract.py`). This pass reuses the A3 report parsing in `a3_extract.py` (`conv`,
  `walk`, `fv`, `ts`, `id_key`, `Salt`, and `Report.direction`) and streams each report once. For every
  `InstantMessage` (nested ones included, deduplicated by model id) that has an `Attachment` model or a file
  jump target, it keeps: family (Sms/Mms = sms, IMessage = imessage, otherwise the `Source` app), direction
  (A3 rule), time (TimeStamp with an explicit offset), the sender and recipient identifier keys, the
  participants of the enclosing `Chat`, and for each attachment whether its `file_id` or jump target resolves
  to a tagged file and that file's MD5 and `Tags` category. Identifiers, MD5s and bodies were held only as
  salted HMACs. The owner identifiers are every Party with `IsPhoneOwner` = True, as in A3.
- **Pass 2, matching** (`p8_cross.py`). A pair needs the same family (K1), the sender copy outgoing and the
  receiver copy incoming (K2), the K3 rule of the row (below), and |dt| <= 120 s with offset 0 (K5). K4
  (content) is not used, because MD5 is what is being measured. Assignment follows 05 5.3.4: greedy by |dt|;
  at equal |dt| competing candidates are left unassigned. A pair is a media pair when at least one side has an
  attachment with an MD5.
- **Comparison.** Each side's set of attachment MD5s is compared. The outcomes are: equal; different (the sets
  are disjoint); partial overlap; one side has no file (its attachment resolves to no tagged file); and one side
  has a file but no MD5.

## Results

| K3 rule used | Pairs | MD5 equal | MD5 different | One side no file | One side no MD5 | Different among both-MD5 |
|---|---|---|---|---|---|---|
| A. As briefed: sender copy's recipients include receiver phone's owner identifier, and receiver copy's sender is sender phone's owner identifier | 1 | 1 | 0 | 0 | 0 | 0 of 1 (0%) |
| B. 05 5.3.2 K3: as A, but the sender copy's chat participants also count (group messages) | 58 | 13 | 1 | 44 | 0 | 1 of 14 (7.1%) |
| C. Receiver side only: receiver copy's sender is sender phone's owner identifier; recipients not checked (loosest; not a rule in 05) | 62 | 14 | 3 | 45 | 0 | 3 of 17 (17.6%) |

No partial overlaps occurred. In every row, no "different" pair has the sender's MD5 on any other message on
the receiving phone, so none of them is an obvious mispairing. Each of rows A and B gives the same both-MD5
counts whether or not both sides must already be media messages (the briefed definition).

**Row B by phone pair.** All pairs are in the 10-report case. A-C2 & A-C6: 6 pairs, 5 equal, 1 different.
A-C3 & A-C6: 4 pairs, 4 equal. A-C8 & A-C9: 4 pairs, 4 equal. A-C5 & A-C6: 44 pairs, all with one side
lacking a file. The 3-phone case has 0 pairs under rules A and B. Under rule C it has 4 pairs (B-C2 & B-C1):
1 equal, 2 different, 1 one side no file.

**Row B by app family.** WhatsApp: 54 pairs, 9 equal, 1 different, 44 one side no file (1 of 10 differs).
Telegram: 4 pairs, 4 equal. Row C, WhatsApp: 3 of 13 differ (23.1%); Telegram: 0 of 4.

**Row B by file category.** Audio: 32 pairs, 11 equal, 0 different, 21 one side no file. Image: 26 pairs,
2 equal, 1 different, 23 one side no file (1 of 3 differs). Row C, Image: 3 of 6 differ; Audio: 0 of 11.

**Row B by time class.** dt exactly 0: 4 pairs, all equal. dt non-zero: 54 pairs, 9 equal, 1 different,
44 one side no file.

**Matching diagnostics.**

- Under rule A only 1 to 15 media messages per directed phone pair pass the identity condition: these phones
  exchange few media messages directly.
- Captions as an independent content key gave 0 pairs on both cases. The pairing used: same family, opposite
  direction, an equal normalised caption of at least 10 characters occurring at most 3 times on each phone,
  and |dt| <= 120 s.
- The "one side no file" pairs are mostly A-C5 & A-C6. One copy's attachment references no tagged file, so it
  is a file-presence gap, not an MD5 failure.

## Deviations from the brief

1. The briefed rule (row A) yields 1 pair, so a sample of 20 was impossible. Rows B (05's own K3, which
   includes group participants) and C (loosest) were added to look for 20. Neither reaches it.
2. Pairing was done over messages with at least one attachment that is not URL-only. A pair was kept when at
   least one side has an MD5, so that the "one side no file" category can exist. The strict variant, where both
   sides must be media messages under the briefed definition, gives the same both-MD5 counts.
3. Assignment is 05 5.3.4 greedy with tie exclusion, not "single candidate on both sides". Ties left
   unassigned: 0 under rules A and B, 1 under rule C.
4. All phone pairs of both cases were used instead of one chosen pair, to maximise the sample.

## What was not possible

- A sample of 20 known-same media pairs: the corpus has 1 (rule A), 14 (rule B) or 17 (rule C) where both
  sides have an MD5.
- Reviewed identity merges (02) do not exist. Identity is by exact normalised identifier only, which in 05's
  terms is `identity_unreviewed`.
- Per-pair clock offsets do not exist, so offset 0 and tau = 120 s were used, as 05 5.3.5 sets before an
  offset is known.
- Perceptual hashing was not run (out of scope; no file bytes read).

## Run times (server, nice 19, idle IO, MemoryMax 2G, one report at a time)

- Pass 1 per report, last full run: P02 17 s, P03 32 s, P04 65 s, P05 18 s, P06 10 s, P07 14 s, P08 131 s,
  P09 7 s, P10 43 s, P11 74 s, P12 4 s, P13 92 s, P14 122 s. That is about 629 s for 13 reports, with a peak
  RSS of 440 MiB (P14).
- Pass 1 ran three times as fields were added (caption hash, chat participants). Each full run took about
  8 to 11 minutes.
- Pass 2: 19 s for all rules.

Scripts: `/mnt/owl-data/tmp/cbm-p8/p8_extract.py` and `/mnt/owl-data/tmp/cbm-p8/p8_cross.py`. Intermediate data
(the salt, the salted pickles and the cross JSON) is deleted.
