# 4. Cellebrite formats and the market of tools that read them

Web research on 2026-10-29. Research, not legal advice. Labels: **[vendor]** vendor marketing or
documentation; **[anecdotal]** single practitioner or forum; **[inference]** the researcher's conclusion;
**[Owl sample]** structure of Owl's own samples.

## 1. Cellebrite product line

- **Inseyets** is the current flagship: extraction (UFED, Premium) plus Physical Analyzer decoding.
  https://cellebrite.com/en/cellebrite-inseyets-faq/ ; Inseyets.PA 10.x is the evolution of PA 8.x / PA Ultra:
  https://cellebrite.com/en/understanding-cellebrite-inseyets-a-deep-dive-with-the-dream-team/ . The October
  2025 fact sheet calls Inseyets "Premium + next-generation UFED + PA" and lists "Core Offline" for
  non-experts: https://media.cellebrite.com/wp-content/uploads/2025/10/Cellebrite_Autumn25-Release_FactSheet_ENGLISH_v2.pdf **[vendor]**
- **Physical Analyzer** makes reports: Report menu, Generate Report, choose data types and time range,
  optionally hashes, optionally include Cellebrite Reader:
  https://cellebrite.com/en/series/tip-tuesday/different-methods-for-creating-reports-in-cellebrite-reader/ .
  Outputs UFDR, PDF, HTML (https://fileinfo.com/extension/ufdr); a forum adds xlsx, docx and XML
  (https://www.forensicfocus.com/forums/general/cellebrite-concordance-load-file-for-ediscovery-platforms/) **[anecdotal]**.
- **Reader**: free, portable viewer for UFDR with search, filters, timeline, tags, reports:
  https://cellebrite.com/en/reader/ ; no raw-data or memory-image view:
  https://cellebrite.com/en/cellebrite-reader-the-first-stop-for-digital-intelligence-collaboration/
- **Pathfinder**: multi-device analytics, "30+ digital sources", link analysis, timeline, media AI,
  speech-to-text, person attribution, translation in 60+ languages: https://cellebrite.com/en/pathfinder-x/
  **[vendor]**. The Autumn 2025 fact sheet adds decoding of "Financial Account and Transfer of Funds" events
  **[vendor]**.
- **Guardian**: cloud evidence sharing; "Guardian Collaborate" shares UFDRs by link with "investigators,
  prosecutors and defense attorneys": https://cellebrite.com/en/guardian **[vendor]**; 2025 adds Graykey
  ingestion, Collaborate for Enterprise, and Guardian Investigate (AI SaaS, beta, GA early 2026) **[vendor]**.
- Others: Digital Collector, Smart Search, Corellium. Autopsy is not Cellebrite and has no native support.

## 2. Output formats

- **.ufd / .ufdx**: .ufd is INI-style text, .ufdx small XML
  (https://sleuthkit.discourse.group/t/can-autopsy-open-ufed-files/409) **[anecdotal]**; .ufdx is metadata
  about the image and extraction (https://www.magnetforensics.com/blog/loading-cellebrite-images-into-magnet-axiom/).
- Raw data comes as .bin or ZIP/TAR plus an HTML report; the NACDL model motion asks for all of these:
  https://www.nacdl.org/getattachment/132e6f26-f6e2-4de5-9c19-9cedf47d0355/cellebrite-reader-request-language.pdf
- **CLBX**: newer container for full-file-system extractions:
  https://www.magnetforensics.com/blog/magnet-axiom-6-6-parse-keychains-from-clbx-extractions-in-magnet-axiom/
- **UFDR**: a ZIP with `report.xml` at its root; files grouped by category; original paths only in the XML:
  https://github.com/DFIRScience/UFDR2DIR . IPED opens `report.xml` (fallback `Report.xml`):
  https://github.com/sepinf-inc/IPED/blob/master/iped-engine/src/main/java/iped/engine/datasource/UfedXmlReader.java
- **Protection**: UFDRs can be protected; IPED detects a protected `report.xml` by magic bytes `2D 06 52 6D`
  and refuses ("Generate the UFDR file again with protection disabled"); Relativity rejects encrypted UFDRs
  ("Decrypt them in Cellebrite Reader first"):
  https://help.relativity.com/RelativityOne/Content/Relativity/Processing/SupportedFileTypes-Cellebrite.htm
- **No public schema**: "The UFDR XML file is not documented publicly and an XML schema is not available.
  Therefore, reverse engineering was used… there might be changes between the XML schema of different
  Cellebrite versions." https://github.com/FlorianRudolf/autopsy-udfr
- **What `report.xml` carries** [Owl sample, confirmed by IPED source]: root `<project>` with
  `reportVersion`, `extractionType`, `NodeCount`, `ModelCount`, `containsGarbage`, namespace
  `http://pa.cellebrite.com/report/2.0`, `licenseID` (7.48). Children: `sourceExtractions/extractionInfo`
  (`deviceName`, `fullName`, `type`, `IsPartialData`, `IsSelectiveExtraction`, and `IsTriageExtraction` in
  8.5), `caseInformation`, `metadata section="Extraction Data"`, `images`, `taggedFiles`, `decodedData`,
  `carvedFiles`, `infectedFiles`, `HashSetsInfo`, `MalwareScanner`, `extraInfos`, `projectConfigurations`.
  Extraction Data items include `UFDIntegrity`. Each tagged file has `fs`, `fsid`, `path`, `size`, `id`,
  `extractionId`, `deleted`, `embedded`, `source_index`, and metadata MD5, SHA256, Local Path, MAC times,
  Tags, EXIF; `<sourcemodels><ownerid>` links a file to its owning message. `decodedData/modelType/model`
  with `id`, `deleted_state` (Intact, Deleted, Trash, Unknown), `decoding_confidence`, `isrelated`,
  `source_index`, `extractionId`, `originalId` (8.5). Timestamps carry an explicit offset;
  `timeZoneConfigurations` records the examiner's display settings.
- **Split section files** (`.xmlModel`, `.xmlTagged` and siblings) [Owl sample]: no public documentation
  found **[inference: one report split by section; a parser must stitch them]**.
- **Version drift**: 7.48 to 8.5 adds `originalId` and `IsTriageExtraction`, drops `licenseID`, and the
  split packaging appears [Owl sample]. Relativity advises re-exporting from Reader "to get the latest schema".

## 3. Who reads Cellebrite outputs

| Product | Ingests | Notes |
|---|---|---|
| Relativity / RelativityOne | UFDR | Chats to RSMF; email to .eml without attachments or deleted flags; calls, contacts, locations to Excel. App Usage, Cell Tower, Powering Event, Credit Card not processed; encrypted and multi-device UFDRs and tags unsupported; dedupe on identical timestamp, sender, body, attachments; disabled options skipped silently (Relativity URL above). Partnership: https://edrm.net/2024/12/unleashing-the-relativity-and-cellebrite-integration-available-now/ |
| Everlaw | Cellebrite chat data | Chat view for uploads after January 2024; no hit highlights or redactions in Chat view: https://support.everlaw.com/hc/en-us/articles/55242442449819-Chat-Review |
| Nuix Workstation | .ufdr / .zip | Mobile processing profile; shows metadata for deleted files: https://documentation.nuix.com/en/content/server/general/projects_frameless/Nuix%20Workstation%20Online%20Help/user_guide/add_cellebrite_mobile_data_as_evidence.htm ; imports and exports RSMF |
| CloudNine LAW | UFDR | https://cloudnine.com/?p=23244 [vendor] |
| Reveal, DISCO, Exterro/FTK | not confirmed | |
| Magnet AXIOM | .ufd, .ufdx, .clbx | Re-parses the raw image ("verify your UFED results"); no UFDR import documented; AXIOM Cyber exports RSMF in time slices: https://www.magnetforensics.com/blog/magnet-axiom-cyber-rsmf-exports-grouping-ediscovery/ |
| Oxygen Forensic Detective | UFDR since 13.6 | https://www.forensicfocus.com/news/oxygen-forensic-detective-13-6-introduces-support-for-qualcomm-based-huawei-devices/ |
| MSAB XRY / XAMN | UFDR converted to .xry | https://www.msab.com/updates/released-today-xry-7-12-xamn-4-0-xec-5-0/ ; imported data not decoded by XRY parsers [anecdotal] |
| Belkasoft X | UFD, UFDX, UFDR | https://belkasoft.com/whats_new_in_belkax_2_2 ; BelkaGPT covers Cellebrite sources [vendor] |
| Paraben E3 | Cellebrite XML and UFD | https://paraben.com/?p=11535 [vendor] |
| Autopsy | no native support | third-party module, last pushed 2020 |
| IPED (Brazilian Federal Police, open source) | .ufdr and report.xml | most complete open parser found; 3,078 stars, active: https://github.com/sepinf-inc/IPED |
| ALEAPP / iLEAPP | raw extractions, not UFDR | "independent testing and validation"; https://github.com/abrignoni/ALEAPP , https://github.com/abrignoni/iLEAPP |

Other open projects: kalink0/crush-forensics (browses UFDR 10.x file systems, verifies hashes),
DFIRScience/UFDR2DIR, SEilers/UFEDLib (C#, 43 models), alephdata/followthemoney-cellebrite (2020). **No
well-maintained Python library for report.xml exists.**

## 4. What defense-side recipients struggle with

- Reader and UFDR are a selected subset: "When the prosecution provides only PDF and UFED Reader reports…
  this is not complete discovery… an incomplete data set that can easily be redacted and must be validated
  with the original extraction." https://forensicresources.org/?p=14928 ; the examiner "can choose which
  data elements to include": https://www.envistaforensics.com/knowledge-center/insights/articles/attorneys-is-your-cell-phone-report-missing-data/ [vendor]
- Multiple extractions of one device are common:
  https://www.publicdefenders.nsw.gov.au:443/Documents/Nick%20Broadbent%20Electronic%20Evidence%20PD%20Conference%20Presentation.pdf
- Time zones: mixed UTC labels within one report and uniform offsets after a setting change
  (https://www.forensicfocus.com/forums/general/need-help-with-timestamps/ [anecdotal]); Cellebrite advises
  checking decoded timestamps against hex:
  https://cellebrite.com/en/series/tip-tuesday/how-to-verify-timestamps-in-cellebrite-physical-analyzer-for-digital-investigations/ ;
  a carved location's time is "the last time that service saw that particular location":
  https://cellebrite.com/en/series/tip-tuesday/explaining-timestamps-associated-with-carved-locations/
- Tool integrity: Signal (2021-04-21) showed a crafted file could make UFED/PA execute code and "undetectably
  alter previous reports": https://signal.org/blog/cellebrite-vulnerabilities/ ; a Maryland new-trial motion
  followed: https://www.abajournal.com/news/article/lawyer-seeks-new-trial-based-on-alleged-cybersecurity-flaws-in-phone-cracking-product
- Validation: NIST CFTT tests are old (UFED 1.1.8.6, 2012):
  https://nij.ojp.gov/library/publications/test-results-mobile-device-acquisition-tool-cellebrite-ufed-1186-report
- Courts: the Fifth Circuit (US v. Williams, 2023) admitted extraction evidence through a lay witness:
  https://www.ca5.uscourts.gov/Opinions/pub/22/22-10316-CR0.pdf **[inference: defense leverage comes from
  specific, sourced discrepancies]**
- Training demand: Reader CLEs for defense bodies.

## 5. Market gaps (mostly inference)

- **Phone and financial fusion**: no reviewed tool joins a UFDR to bank-statement ledgers.
- **Defense-oriented review without Reader**: parse every model type, show Unknown and Deleted plainly, and
  report what was not included (IsSelectiveExtraction, IsPartialData, chosen types and ranges).
- **Provenance and citation** to record and file, with hash re-verification.
- **RSMF export** for counsel's review platforms.
- **Grounded AI** with citations, built for the defense side.
- **Robust ingestion**: protected UFDRs, split files, version drift, no public schema.

## 6. Legal and licensing (research, not advice)

- The Reader EULA text could not be located; it needs a direct read before relying on anything here.
- Contract terms against reverse engineering can bind a licensee (Bowers v. Baystate, Fed. Cir. 2003):
  https://law.resource.org/pub/us/case/reporter/F3/320/320.F3d.1317.01-1109.01-1108.html **[inference:
  parsing a ZIP and XML without installing Reader differs from decompiling Reader]**.
- 17 U.S.C. §1201(f) interoperability exception read narrowly:
  https://project-disco.org/intellectual-property/070617-interoperability-and-the-copyright-offices-section-1201-report/
  **[inference: decoding protected UFDRs without Reader is the riskiest path]**.
- IPED, Autopsy module, UFEDLib, Relativity, Nuix, Oxygen, XRY and Belkasoft all parse UFDR or report.xml
  publicly; no dispute found. Absence of evidence is not clearance.

## Ten most decision-relevant facts

1. A UFDR is a ZIP with `report.xml` at the root; no public schema; parsers break across versions.
2. `report.xml` carries enough to cite every finding to its record and file, plus extraction metadata
   including `UFDIntegrity` and the selective and partial flags.
3. Owl has already received a split production with no public documentation of the layout.
4. Protected UFDRs are a real blocker; IPED and Relativity refuse them.
5. Reader is free with no raw-data view; defense resources describe Reader and UFDR productions as
   incomplete, redactable subsets.
6. Relativity's conversion silently skips categories, dedupes and drops deleted flags from email.
7. Time zones are a recurring practitioner complaint.
8. Report integrity depends on the tool; courts admit Cellebrite output, so value lies in specific discrepancies.
9. Cellebrite is moving into AI, financial events and legal sharing, aimed at agencies and corporations.
10. No maintained Python report.xml library exists; Loupe's parser is the asset.
