# PDF Ingestion Cost Estimate (GPT-4o)

## How Pages Map to LLM Calls

Pages are chunked into **8,000-character chunks** with 1,600-char overlap. A typical page is ~2,000–4,000 characters, so roughly **2–4 pages per chunk**.

## LLM Calls Per Chunk

| Call | When | Est. Tokens |
|------|------|-------------|
| Entity/Relationship Extraction | Always (1 per chunk) | ~3,500–4,000 input + ~1,000–1,500 output |
| Entity Disambiguation | Conditional (0–N per chunk) | ~500–1,000 each |
| Entity Summary Generation | Per new/updated entity | ~500–800 each |
| Document Summary | Once per document | ~2,000–3,000 |

## GPT-4o Pricing

**$2.50 / 1M input tokens, $10.00 / 1M output tokens**

## Cost Per Page

| Scenario | Cost Per Page |
|----------|---------------|
| Low (text-light, few entities) | ~$0.003 |
| Typical (standard document) | $0.005–$0.01 |
| High (dense tables, many entities) | $0.01–$0.02 |

## Practical Examples

| Document | Est. Cost |
|----------|-----------|
| 10-page simple report | $0.05–$0.10 |
| 50-page financial document (table-heavy) | $0.25–$0.50 |
| 100-page case file | $0.35–$0.75 |

---

## GPT-5.2 Estimate

### GPT-5.2 Pricing

**$1.75 / 1M input tokens, $14.00 / 1M output tokens**

Input is 30% cheaper than GPT-4o, but output is 40% more expensive. Since entity extraction produces structured JSON output, the higher output cost dominates — making GPT-5.2 roughly **~10% more expensive** overall for this workload.

### Cost Per Page (GPT-5.2)

| Scenario | Cost Per Page |
|----------|---------------|
| Low (text-light, few entities) | ~$0.003–$0.004 |
| Typical (standard document) | $0.006–$0.011 |
| High (dense tables, many entities) | $0.011–$0.022 |

### Practical Examples (GPT-5.2)

| Document | Est. Cost |
|----------|-----------|
| 10-page simple report | $0.06–$0.11 |
| 50-page financial document (table-heavy) | $0.28–$0.55 |
| 100-page case file | $0.39–$0.83 |

### GPT-4o vs GPT-5.2 Comparison

| | GPT-4o | GPT-5.2 |
|--|--------|---------|
| Input price (per 1M) | $2.50 | $1.75 |
| Output price (per 1M) | $10.00 | $14.00 |
| 100-page case file | $0.35–$0.75 | $0.39–$0.83 |
| Better for | Output-heavy workloads | Input-heavy workloads |

GPT-5.2 would only be cheaper if the workload were predominantly input tokens (e.g., large-context summarization with short outputs). For entity extraction where output is ~25–30% of total tokens, GPT-4o remains the more cost-effective choice.

---

## Real-World Calibration (GPT-4o)

A real ingestion run of **200 files** using GPT-4o cost **~$180–200**, or roughly **$0.90–1.00 per file**.

This is ~2–3x higher than the theoretical estimates above, likely due to:
- **Entity disambiguation scales non-linearly** — as more entities accumulate across files, each new chunk triggers more fuzzy-match comparisons and disambiguation LLM calls.
- **Dense/long files** — investigative case files tend toward the "high" end of the per-page range.
- **Entity summary regeneration** — entities that appear across multiple files get their summaries regenerated on each update.

### Revised Estimates (Calibrated to Real Data)

Using the empirical $0.90–1.00/file baseline for GPT-4o:

| Batch Size | GPT-4o (actual) | GPT-5.2 (projected, +10%) |
|------------|-----------------|---------------------------|
| 50 files | $45–$50 | $50–$55 |
| 100 files | $90–$100 | $99–$110 |
| 200 files | $180–$200 | $198–$220 |
| 500 files | $450–$500 | $495–$550 |

> **Note:** Per-file cost increases with batch size due to disambiguation scaling. The 500-file estimate may be higher in practice.

---

## Notes

- The main cost variable is **entity disambiguation** — documents with many overlapping entities trigger extra LLM calls per chunk.
- Actual costs are tracked in `cost_tracking_service.py` for real ingestion runs.
