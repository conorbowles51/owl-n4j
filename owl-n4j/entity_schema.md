# Entity Schema

Each entity must have at least:

## type

One of: Person, Company, Account, Organisation, Bank, Location, Transaction, Document, Communication, Meeting, Payment, Login, Alert, PhoneCall, Email, Contract, Invoice, Withdrawal, Deposit, Transfer, Investigation, Warrant, Subpoena, etc.

## id

A random UUID, immutable (internal technical identifier).

## key

A stable, human-readable identifier used for merges and lookups. Derived from a normalised name, e.g. "John Smith" → john-smith.

## name

Human-readable label, e.g. "John Smith", "Emerald Imports Ltd".

## notes

A map of document → observations, for example:

```
{
  "docs/doc_001.pdf": "Introduced as director of Emerald Imports Ltd; signs transfer orders.",
  "docs/doc_014.pdf": "Appears as account holder of ACC-003 at GreenBank."
}
```

Every time the entity appears in a document, this field is updated with a new entry (or appended to an existing entry for that doc).

## summary

An AI-generated, compact description of the entity that is periodically refreshed. This is the "current understanding" of the entity across all docs:

> "Shane O'Brien is the director of Emerald Imports Ltd and appears to control several accounts involved in suspicious transfers between 2021–2022…"

### Optional but useful fields:

- created_at, updated_at
- domain-specific props (role, bank, country, risk_score, etc.)

---

# Event Type Nodes

These temporal entities are critical for timeline construction and investigation sequencing:

## Transaction
- type: "Transaction"
- amount, currency, date, time
- from_account, to_account
- status (completed, pending, failed, reversed)
- method (wire, ACH, card, cash, crypto)

## Payment
- type: "Payment"
- amount, currency, date
- payer, payee
- purpose, invoice_reference
- payment_method

## Communication
- type: "Communication"
- subtype: email, phone, sms, chat, letter
- date, time, duration (for calls)
- participants (from, to, cc, bcc)
- subject, summary

## Email
- type: "Email"
- date, time, sender, recipients
- subject, attachments
- email_address, domain

## PhoneCall
- type: "PhoneCall"
- date, time, duration
- caller, recipient
- phone_numbers
- call_type (incoming, outgoing, missed)

## Meeting
- type: "Meeting"
- date, time, location
- attendees, organiser
- purpose, outcome

## Login
- type: "Login"
- date, time, ip_address
- user_account, device
- location (inferred from IP)
- status (successful, failed)

## Withdrawal
- type: "Withdrawal"
- amount, currency, date, time
- account, location (ATM/branch)
- method (ATM, teller, transfer)

## Deposit
- type: "Deposit"
- amount, currency, date, time
- account, source, location
- method (cash, cheque, transfer)

## Transfer
- type: "Transfer"
- amount, currency, date, time
- from_account, to_account
- transfer_type (internal, external, international)
- reference_number

## Alert
- type: "Alert"
- date, time, alert_type
- triggered_by (entity/transaction)
- risk_score, status
- alert_reason (AML, KYC, velocity, pattern)

## Contract
- type: "Contract"
- date_signed, effective_date, expiry_date
- parties, contract_type
- value, terms_summary

## Invoice
- type: "Invoice"
- date_issued, date_due, date_paid
- amount, currency, invoice_number
- issuer, recipient, items

## AccountOpening
- type: "AccountOpening"
- date, account_number
- account_holder, bank
- initial_deposit, account_type

## AccountClosure
- type: "AccountClosure"
- date, account_number
- account_holder, bank
- closing_balance, reason

## Investigation
- type: "Investigation"
- date_opened, date_closed
- investigators, subjects
- investigation_type, status

## Warrant
- type: "Warrant"
- date_issued, date_executed
- issuing_authority, target
- warrant_type (search, arrest, seizure)

## Subpoena
- type: "Subpoena"
- date_issued, date_served, date_due
- issuing_authority, recipient
- requested_documents/testimony

## CourtFiling
- type: "CourtFiling"
- date_filed, case_number
- court, parties, filing_type
- documents_filed

## PropertyTransaction
- type: "PropertyTransaction"
- date, property_address
- buyer, seller, price
- transaction_type (sale, lease, mortgage)

## TravelEvent
- type: "TravelEvent"
- date, departure_location, arrival_location
- traveler, booking_reference
- flight/train/vehicle details

## CompanyRegistration
- type: "CompanyRegistration"
- date_registered, registration_number
- company_name, jurisdiction
- directors, shareholders, registered_address

## LicenseIssuance
- type: "LicenseIssuance"
- date_issued, date_expires
- license_type, license_holder
- issuing_authority

## Audit
- type: "Audit"
- date_conducted, auditor
- audited_entity, audit_type
- findings_summary, compliance_status

---

# Relationship Schema

Each relationship should have:

## type

e.g. OWNS_ACCOUNT, OWNS_COMPANY, TRANSFERRED_TO, MENTIONED_IN, ASSOCIATED_WITH, RELATED_TO, PART_OF_CASE, CALLED, EMAILED, MET_WITH, ATTENDED, SIGNED, TRIGGERED, ISSUED_TO, RECEIVED_FROM, etc.

## from / to

References to entity key or internal id.

## doc_refs

A list/map of docs where this relationship is evidenced, e.g.:

```
{
  "docs/doc_001.pdf": "Bank statement shows transfer from ACC-001 to ACC-002.",
  "docs/doc_009.pdf": "Email where Shane instructs this transfer."
}
```

### Optional: date - important to include.

---

# Document Ingestion Process

The LLM goes through docs (one doc or chunk at a time) and each time it decides it has found an entity:

## 1️⃣ Build a candidate entity object from the text

Example:

```
{
  "type": "Person",
  "name": "Shane O'Brien",
  "key": "shane-obrien",
  "notes": "In this document, Shane authorises a transfer of 50,000 EUR from ACC-003.",
  "proposed_properties": {
    "role": "director of Emerald Imports Ltd"
  }
}
```

It should also output candidate relationships involving this entity in this document.

## 2️⃣ Search for this entity in the graph DB

### First, try exact key:

```
MATCH (e {key: "shane-obrien"})
```

If not found, optionally try a fuzzy search by normalised name:

```
toLower(e.name) = toLower("Shane O'Brien")
```

Or similar-name candidates (for disambiguation step).

---

## Case A: entity exists

### 3.1 Fetch existing entity + top N neighbours

Pull:
- the entity node (e),
- its current summary and key properties,
- top N neighbours (most important related nodes)

### 3.2 Ask LLM how to update

Provide:
- existing summary,
- this doc's new notes snippet,
- relevant neighbour context.

Ask the LLM to decide:
- What new information should be appended to notes[e][doc_path]
- Which properties should be added/updated
- Which new relationships should be created or enriched

### 3.3 Apply updates

- Update notes (append or merge)
- Update summary
- Upsert relationships (MERGE + new doc_refs)

---

## Case B: entity does not exist

### 4.1 Optionally run a disambiguation check

If fuzzy matches found:

Ask LLM: *same or new?*
- If "same", switch to Case A
- If clearly new → continue

### 4.2 Create a new entity

Assign:
- id: new UUID
- key: normalised name
- name, type, notes, summary

Connect to case and related nodes:

```
(e)-[:PART_OF_CASE]->(case)
(e)-[:ASSOCIATED_WITH]->(primary_subject)
```

Create relationships found in doc.

---

## Repeat for all entities / chunks in the document

End result:
- Existing nodes enriched with new evidence
- New nodes added where needed
- Relationships updated with doc-level evidence

---

# Summary Maintenance

Two options:

### Inline Updates

After each major update → regenerate summary immediately

### Batch Updates

Mark as "dirty" then periodically refresh:
- read full notes
- generate updated summary
- store on entity node

Summaries:
- improve future ingestion prompts
- displayed in UI as the current truth model

---

# Timeline Construction

Event type nodes enable powerful temporal analysis:

- All event types should include temporal properties (date, time, timestamp)
- Events can be queried chronologically to build investigation timelines
- Events link entities through temporal relationships (e.g., Person → MADE → PhoneCall → TO → Person)
- Pattern detection: sequences of events (e.g., Login → Transfer → Withdrawal within minutes)
- Gap analysis: identifying suspicious periods of activity or inactivity

Example timeline query:
```
MATCH (e:Event)-[:INVOLVES]->(subject)
WHERE e.date >= '2021-01-01' AND e.date <= '2022-12-31'
RETURN e.date, e.type, e.summary
ORDER BY e.date ASC
```