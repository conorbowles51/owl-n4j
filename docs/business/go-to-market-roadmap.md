# Go-To-Market Roadmap

Prepared: 2026-06-04

## Reader And Use

This roadmap is for the founders. After reading it, the team should be able to sequence product readiness, first US licences, Irish funding/support applications, and later sales hires without trying to do everything at once.

The core question is: how does Owl move from a powerful working platform to a real company with customers, repeatable deployment, defensible IP, and enough funding or revenue to keep growing?

## Strategic View

Owl has a strong wedge: investigation teams have more documents and data than they can manually understand, and the important answer is often in the relationships between people, entities, money, places, communications, and time. Owl's graph-first AI workflow is a credible answer to that pain.

The next phase should prove three things:

1. **Trust:** real customer data can be handled securely, privately, and recoverably.
2. **Value:** a paying investigator or legal team gets meaningful insight faster than their current workflow.
3. **Repeatability:** the team can deploy, support, update, and sell Owl without heroic one-off effort each time.

## Current Position

Known strengths:

- Comprehensive investigation workspace.
- AI-assisted data exploration.
- Graph, timeline, map, table, and financial views.
- Case management and user system.
- Docker-based isolated deployment model.
- Per-customer GCP instance concept.
- Strong domain feedback from Alex and Owl Consultancy.
- Likely first US sales path through Alex's investigator network.

Known risks:

- Security and deployment processes need production hardening.
- Company/IP/founder structure is not yet formalised.
- First-customer contract and data-processing terms are not yet settled.
- Sales motion is unproven beyond Alex's relationships.
- Grant/funding applications need a clear Irish company and evidence of export potential.
- The product may be powerful but still needs a simple buyer-facing story.

## Roadmap Summary

| Phase | Timing | Primary Goal | Exit Criteria |
|---|---:|---|---|
| 0. Foundation | June 2026 | Lock structure, release blockers, pilot offer | Irish structure path chosen, legal docs started, release blockers owned |
| 1. V1 Release Readiness | June to mid-July 2026 | Make Owl safe for first external customer data | Security, MFA, backup/restore, deployment, docs, and support drill complete |
| 2. First Paid US Licences | July to August 2026 | Convert Alex's warm network into paid validation | 1-3 paid pilots/licences with defined success metrics |
| 3. Irish Funding And Credibility | July to September 2026 | Pursue Enterprise Ireland/LEO/credits using customer validation | PSSF/LEO path submitted or actively advised; cloud credits/support pursued |
| 4. Repeatable Sales Motion | September to December 2026 | Turn founder-led sales into a repeatable process | Case studies, pricing, demo flow, objection handling, reference customers |
| 5. Scale Decisions | 2027 | Decide whether to hire sales, raise, partner, or bootstrap | Clear revenue signal, customer segment focus, support load understood |

## Phase 0: Foundation

Target: June 2026.

### Company And Founder Setup

Decide the working structure before any new customer contract:

- Irish LTD parent/product company.
- Platform IP assigned to the Irish company.
- Founder shares and vesting/reverse vesting agreed.
- Shareholder agreement drafted.
- Alex's role documented separately from Owl Consultancy's role.
- No exclusive US sales rights unless deliberately negotiated.

Output:

- Founder/shareholder structure brief for solicitor.
- IP assignment checklist.
- Alex/Owl Consultancy role decision.

### First Licensing Package

Create a simple paid pilot/licence offer:

- Target customer: small investigation firm, legal/investigation consultancy, or complex-case investigator.
- Offer: isolated GCP instance, onboarding, limited support, defined number of users/cases, defined pilot period.
- Success criteria: time saved, insights found, evidence processed, renewal decision.
- Price: enough to confirm willingness to pay, even if discounted for first customers.

Avoid over-custom pricing at first. The goal is learning and commitment, not maximising early revenue.

### Release Blocker Ownership

Use the release readiness checklist to assign owners and decide what is truly blocking. The highest-risk areas are:

- Unique secrets and hardened deployment.
- MFA and role-based access.
- Backup and restore.
- Multi-instance deployment and rollback.
- Audit logs.
- Evidence integrity and source citations.
- Customer legal/data-processing terms.

## Phase 1: V1 Release Readiness

Target: June to mid-July 2026.

### Product Readiness Goal

The product does not need every enterprise feature. It needs to be safe enough for real investigation data and polished enough that the first customer trusts it.

Minimum complete V1 release drill:

1. Provision a clean isolated instance.
2. Create users and enforce MFA.
3. Upload representative evidence.
4. Run ingestion.
5. Review graph, timeline, map, table, financial, and AI assistant.
6. Export a case/report.
7. Back up the full instance.
8. Restore into a clean environment.
9. Deploy an update.
10. Roll back the update.
11. Review audit logs.
12. Complete the workflow using documentation only.

If the team cannot complete this drill, the product is not ready for unsupervised customer data.

### Security And Trust Pack

Prepare a plain-English security pack for prospects:

- Per-customer isolated instance model.
- Where data is stored.
- Who can access customer data.
- How backups work.
- How deletion/offboarding works.
- What AI providers are used.
- Whether data is sent to external model APIs.
- How source citations and audit logs work.
- What the customer is responsible for.

This does not need to be SOC 2. It needs to be honest, specific, and confidence-building.

### Documentation

Create or update documentation for:

- Admin setup.
- User onboarding.
- Evidence upload and ingestion.
- Graph/timeline/map/financial workflows.
- AI assistant usage and limitations.
- Export/import.
- Backup/restore.
- Support escalation.

Documentation is a sales tool here. If a customer cannot understand the system, they will assume it is risky.

## Phase 2: First Paid US Licences

Target: July to August 2026.

### Role Of Alex's Network

Alex's contacts are the best near-term route to paid validation. Treat those contacts as a structured pilot funnel:

- Alex identifies warm prospects.
- Founders qualify fit and data sensitivity.
- Demo uses a clean anonymised case.
- Customer signs pilot/licence and data terms.
- Customer gets an isolated instance.
- Team measures success and support load.

Alex's contribution should be recognised, but the process should produce company-owned learning: objections, pricing evidence, feature gaps, testimonials, and deployment lessons.

### Ideal First Customer Profile

Best first customers:

- Small to mid-sized private investigation firms.
- Criminal defence or white-collar investigation teams.
- Litigation support consultants.
- Forensic accounting/investigation boutiques.
- Firms with document-heavy, relationship-heavy cases.

Avoid first if possible:

- Law enforcement/government procurement.
- Customers requiring CJIS/agency-level compliance immediately.
- Very large enterprises with long procurement cycles.
- Customers demanding heavy bespoke features before payment.

### Sales Assets Needed

Before the first serious sales conversations:

- One-page product overview.
- Five-minute demo script.
- Security/trust summary.
- Pilot/licence proposal template.
- Customer onboarding guide.
- Pricing hypothesis.
- FAQ for objections.

Important objections to prepare for:

- Is my data used to train AI models?
- Where is the data stored?
- Can your team see my case?
- What happens if the AI is wrong?
- Can I export everything?
- What if the system goes down?
- What happens at the end of the pilot?
- How do I delete my data?

## Phase 3: Irish Funding And Credibility

Target: July to September 2026.

### Enterprise Ireland

Enterprise Ireland's Pre-Seed Start Fund is a strong candidate if Owl fits the eligibility criteria. It supports early-stage companies with MVP/beta product, customer validation, innovation, internationalisation potential, and capacity to grow jobs/sales in Ireland. It offers EUR 50k or EUR 100k investment in the form of a convertible loan note, plus mentoring and market research access.

Action path:

- Speak with a Local Enterprise Office or Irish BIC advisor.
- Contact Enterprise Ireland HPSU enquiries or a relevant advisor.
- Ask specifically how Alex's US residency and one-third shareholding affects eligibility.
- Prepare customer validation evidence from Owl Consultancy and first US prospects.
- Prepare an export-focused plan: US investigation/legal market first, Ireland/EU later.
- Prepare a cost plan for salaries, travel, consultancy, product testing, security hardening, and commercial milestones.

### Local Enterprise Office

LEO may be useful for early-stage supports, especially if the company qualifies as a microenterprise or is still in the right start-up window. The Priming Grant and Market Explorer Grant should be checked with the local office because eligibility and county-level processes matter.

Potential uses:

- Early commercial planning.
- Market exploration.
- Consultancy.
- Training.
- Marketing materials.
- Trade/market research activity.

### Google Cloud Credits

Because the intended deployment model uses per-customer Google Cloud instances, apply to Google for Startups Cloud. Google describes up to USD 200k in cloud credits generally, and up to USD 350k for qualifying AI-first startups depending on tier and eligibility.

If the company is not venture-backed, the largest AI tier may not be available, but the starter tier may still be useful.

### IP Advice

Enterprise Ireland's Access Advice: IP Start can fund external IP advisory support for eligible companies. Whether or not that specific grant applies, an IP audit is worth doing:

- Who wrote what?
- What code/assets/prompts/configuration are owned by whom?
- Are there open-source licensing issues?
- Is the Owl name/trademark clear?
- What should be assigned to the Irish company?
- Is there anything patentable or better protected as trade secret?

## Phase 4: Repeatable Sales Motion

Target: September to December 2026.

The goal after the first paid licences is not just more demos. It is repeatability.

### What To Learn From Each Pilot

For every pilot/licence, capture:

- Buyer type and role.
- Case type.
- Data volume.
- Time to deploy.
- Time to first useful graph.
- Time to first useful AI answer.
- Support questions asked.
- Failed or confusing workflows.
- Security/procurement objections.
- Price sensitivity.
- Renewal/expansion likelihood.
- Quote/testimonial potential.

### Case Studies

Create anonymised case studies:

- "Processed X files / Y pages."
- "Found key relationships between A, B, and C."
- "Built a timeline in hours instead of days."
- "Reduced manual review burden."
- "Improved confidence in evidence coverage."

Avoid exaggerated claims. Investigation buyers will trust specific, modest proof more than broad AI promises.

### Pricing Evolution

Start simple:

- Setup/onboarding fee.
- Monthly licence per instance or per firm.
- User/case limits if needed.
- AI usage pass-through or included allowance.
- Support tier.

Do not build automated billing too early. Manual invoices are fine until customer count proves the need.

### Sales Hire Decision

Do not hire a full-time salesperson until:

- At least 3 paid customers or pilots exist.
- The buyer persona is clearer.
- A demo reliably produces qualified interest.
- Common objections have answers.
- Pricing is not pure guesswork.
- Deployment/support load is understood.

Before full-time sales, consider:

- Founder-led sales with Alex introductions.
- Fractional legal-tech/investigation sales advisor.
- Commission-only referral partners.
- Specialist reseller/channel partnerships.

## Phase 5: Scale Decisions

Target: 2027.

By early 2027, the team should decide which path Owl is on.

### Path A: Focused Investigation SaaS

Best if small/mid investigation and legal teams buy repeatedly.

Priorities:

- Product polish.
- Simple onboarding.
- Reliable cloud deployment.
- Strong documentation.
- Repeatable pricing.
- Customer support process.

### Path B: Legal Defence / Litigation Intelligence Platform

Best if lawyers and litigation support teams show strongest willingness to pay.

Priorities:

- Bates support.
- Exhibit-ready exports.
- Privilege and confidentiality features.
- Legal terminology/UX.
- Court/client-ready reporting.
- Law-firm security questionnaires.

### Path C: Enterprise / Government Investigation Platform

Best only if a large buyer pulls the company there.

Priorities:

- SSO/SAML.
- Compliance certifications.
- Procurement support.
- Dedicated customer success.
- Formal SLAs.
- Possibly US entity/subsidiary.
- Security audits.

This path may be lucrative, but it is slow and expensive. It should not be the first default unless the customer demand is strong.

### Path D: Services-Enabled Product

Best if buyers want Alex/Owl Consultancy or expert investigators to help run analyses.

Priorities:

- Clear separation between software licence and services.
- Data access controls.
- Reseller/services agreement.
- Repeatable investigation templates.
- Margin model for service delivery.

This may fit Alex's role well, but needs careful boundaries so services do not swallow the product company.

## Role Split

Suggested default:

| Role | Primary Owner |
|---|---|
| Product and engineering | Irish product founders |
| Security and deployment readiness | Irish product founders |
| Domain workflow and investigator feedback | Alex plus pilot users |
| US warm introductions | Alex |
| Customer demos | Founders plus Alex |
| Contracts/company structure | Founders with solicitor/accountant |
| Irish funding applications | Irish founders |
| Pilot measurement | Shared |
| Support process | Irish product founders initially |

## Near-Term Weekly Cadence

For the next six weeks:

- Weekly founder meeting on release readiness.
- Weekly Alex sales/pilot pipeline update.
- Weekly deployment/security drill until green.
- Fortnightly legal/company setup check-in.
- Fortnightly Irish funding/support progress check.

Keep a single decision log for:

- Company structure.
- Founder equity/vesting.
- Release blockers.
- Pricing.
- Customer commitments.
- Security promises.
- Product limitations disclosed to customers.

## Metrics To Track

### Product Metrics

- Files/pages processed per case.
- Extraction success rate.
- Graph size and load time.
- AI answer citation coverage.
- Time to first useful insight.
- Export success.
- Backup success.
- Restore test success.

### Commercial Metrics

- Warm introductions.
- Demos booked.
- Pilots proposed.
- Pilots signed.
- Monthly recurring revenue.
- Setup fees.
- Renewal intent.
- Referral/testimonial availability.

### Operational Metrics

- Time to provision customer instance.
- Time to deploy update.
- Rollback success.
- Support tickets per customer.
- Security incidents.
- Backup age.
- Restore drill frequency.

## What Not To Do Yet

Avoid these until evidence justifies them:

- Do not hire a full-time salesperson before paid pilot evidence.
- Do not give exclusive US rights casually.
- Do not let Owl Consultancy own product IP by accident.
- Do not pursue government procurement as the first main route.
- Do not create a US parent just because it sounds more startup-like.
- Do not overbuild billing before manual invoicing becomes painful.
- Do not sell "AI certainty"; sell faster investigation with source-backed outputs.

## Board-Level Milestones

The founders should be able to answer these by the end of each period.

### By End Of June 2026

- What company owns the product?
- Has each founder assigned IP?
- What are the V1 release blockers?
- What must be done before first customer data?
- What is the pilot offer?
- Who are the first 10 prospects?

### By End Of July 2026

- Can Owl provision, update, roll back, back up, and restore a customer instance?
- Has at least one external prospect agreed to paid terms?
- Are customer docs and security answers ready?
- Has the Irish funding path been validated with an advisor?

### By End Of September 2026

- How many paid pilots/customers exist?
- What customer segment is showing strongest pull?
- What price is credible?
- What features are repeatedly requested?
- What security/procurement objections appear?
- Is Enterprise Ireland/LEO support in motion?

### By End Of 2026

- Is there repeatable revenue?
- Is a sales hire justified?
- Is a US subsidiary justified?
- Is the product best positioned for investigators, legal defence, corporate investigations, or another segment?
- Can the founders fund the next year through revenue, grants, investment, or a mix?

## Key Sources

- Enterprise Ireland, [Pre-Seed Start Fund](https://www.enterprise-ireland.com/en/supports/pre-seed-start-fund)
- Enterprise Ireland, [Innovative HPSU Fund](https://www.enterprise-ireland.com/en/innovative-hpsu-fund)
- Enterprise Ireland, [Access Advice: IP Start](https://www.enterprise-ireland.com/en/supports/access-advice-ip-start)
- Local Enterprise Office, [Priming Grant example](https://www.localenterprise.ie/limerick/financial-supports/priming-grant)
- Google Cloud, [Google for Startups Cloud Program](https://startup.google.com/cloud/)
- Google Cloud, [AI startup program](https://cloud.google.com/startup/ai)
- Revenue, [Corporation Tax basis of charge](https://www.revenue.ie/en/companies-and-charities/corporation-tax-for-companies/corporation-tax/basis-of-charge.aspx)
- Revenue, [R&D Corporation Tax Credit eBrief 085/26](https://www.revenue.ie/ga/tax-professionals/ebrief/2026/no-0852026.aspx)
