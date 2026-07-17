# Brand Identity Inventory - DKT-511

Source: release backlog BRAND-001, parent story DKT-509 "Freeze and apply the production identity".

Inventory date: 2026-07-17.

Scanned revision: `5352bdff417e9ec87aad1b44ec4c027f172783c2`.

Method: `python3 scripts/brand_identity_scan.py --strict`, plus targeted checks for generated documents, public assets, favicons, and outbound email markers.

Cleared production identity: **Loupe**. Customer-visible release artifacts must present Loupe only. Legacy or alternate names below are documented release blockers for DKT-512/513 unless explicitly marked internal-only.

## 1. Customer-Visible Cleared Loupe Surfaces

| Surface | Location | Evidence | Status |
| --- | --- | --- | --- |
| App document title | `frontend_v2/index.html:8` | `Loupe Investigation Console` | Cleared |
| App meta description | `frontend_v2/index.html:7` | `Loupe enterprise investigations platform` | Cleared |
| App favicon | `frontend_v2/index.html:5` | Inline neutral SVG data favicon; no `.ico` file found | Cleared |
| App logo assets | `frontend_v2/public/loupe-logo.png`, `frontend_v2/public/loupe-logo-transparent.png` | Loupe logo files are present in the public bundle | Cleared |
| Sidebar brand | `frontend_v2/src/components/ui/sidebar.tsx:218,241` | ARIA label and collapsed tooltip use Loupe | Cleared |
| Logo component | `frontend_v2/src/components/brand/LoupeLogo.tsx:15,20,24` | Uses `loupe-logo-transparent.png`; default alt is Loupe | Cleared |
| Login footer | `frontend_v2/src/features/auth/components/LoginPage.tsx:178` | Copyright string uses Loupe | Cleared |
| Setup/update UI copy | `frontend_v2/src/features/admin/components/SetupWizard.tsx:50`, `frontend_v2/src/features/admin/components/PlatformUpdatesPage.tsx:208` | Visible admin copy uses Loupe | Cleared |
| UI design/dev references | `frontend_v2/src/stories/DesignSystem.mdx`, Storybook examples | Storybook references Loupe, but is not a production customer surface | Cleared/internal |

Current app-shell scan result: the production app shell is Loupe-clean except for retained internal technical identifiers listed in section 4.

## 2. Customer-Visible Legacy Or Alternate Identity - Open Release Blockers

These are not fixed by DKT-511. They are recorded so DKT-512/513 can remove or deliberately version them before pilot acceptance.

| Surface | Location | Finding | Owner |
| --- | --- | --- | --- |
| Generated user guide PDF, Python generator | `scripts/generate_user_guide_pdf.py:3,34,57,65,277,279` | Uses "Owl Consultancy Group", "Owl Investigation Platform", broken logo path `frontend/public/owl-logo.webp`, and year `2024` | DKT-512/513 |
| Generated user guide PDF, Node generator | `scripts/generate_user_guide_pdf.js:3,12,34,36,42,48,54` | Same legacy Owl brand and broken `frontend/public/owl-logo.webp` path | DKT-512/513 |
| Orphaned public asset | `frontend_v2/public/owl.webp` | Legacy Owl asset exists in the public directory; no `frontend_v2/src` or `frontend_v2/index.html` references found | DKT-512 |
| Landing page identity | `landing/index.html:7,10,12,15` | Active landing metadata is branded `Arclight`, not Loupe | DKT-513 |
| Landing page favicon | `landing/index.html:5`, `landing/public/favicon.svg` | Landing app has a separate SVG favicon tied to the Arclight visual system | DKT-513 |
| Landing page UI copy | `landing/src/components/Hero.tsx:19`, `landing/src/components/HowItWorks.tsx:7`, `landing/src/components/Trust.tsx:38`, `landing/src/components/FinalCta.tsx:15`, `landing/src/components/Footer.tsx:17`, `landing/src/components/Nav.tsx:28`, `landing/src/components/brand/Wordmark.tsx:11`, `landing/src/lib/demoRequest.ts:17` | Visible or logged landing copy uses Arclight | DKT-513 |
| Landing page visual identity comments/styles | `landing/src/components/brand/Mark.tsx:6`, `landing/src/components/hero-scene/scene.ts:2`, `landing/src/styles/global.css:2`, `landing/src/styles/sections.css:2` | Internal source comments/style headers name Arclight and explain the mark | DKT-513 |
| Agent-generated-output prompt | `backend/services/agent/graph.py:392,624` | System prompt says "You are the OWL AI Agent"; not rendered directly, but output-adjacent because the model can self-identify from it | DKT-513 |

## 3. Email Copy

Status: **N/A / empty today**.

Evidence: `python3 scripts/brand_identity_scan.py --strict` found zero outbound email markers. A direct marker search across `backend/`, `evidence-engine/`, `frontend_v2/src/`, `landing/src/`, and `scripts/` for `smtp`, `sendmail`, `EmailMessage`, `mailto`, `noreply`, `from_email`, `send_email`, and `reply-to` also returns no outbound-email implementation.

The landing demo request form currently accepts an email field and logs a stubbed request (`landing/src/lib/demoRequest.ts:17`), but it does not send email.

## 4. Internal-Only Technical Identifiers - Retained And Invisible

These identifiers are retained for stability and are not customer-visible release branding. They should be versioned deliberately if changed later.

| Identifier | Location | Why retained | Visibility |
| --- | --- | --- | --- |
| Docker project and container names | `docker-compose.yml:1,6,28,41,50,59,104` | Renaming containers and databases can affect local volumes, operator scripts, and environment assumptions | Internal deployment/runtime |
| Docker database credentials | `docker-compose.yml:33-35,64,108` | Local development service credentials and DSNs | Internal runtime |
| Systemd service/path names | `deploy/owl-self-update.service.example`, `deploy/owl-self-update.sudoers.example`, `/opt/owl-n4j` references in tests and config | Renaming requires coordinated server migration and sudoers/systemd updates | Operator-only |
| Deployment service names | `deploy/deploy.sh`, `deploy/setup-server.sh`, `deploy/install-frontend-service.sh`, `deploy/rollback.sh`, `deploy/README.md` | Shell scripts and server service names are operational identifiers | Operator-only |
| Theme localStorage key | `frontend_v2/src/lib/theme-provider.tsx:17,33` | Preserves existing user theme preference; can be migrated separately | Browser storage key, not visible UI copy |
| CSS compatibility alias | `frontend_v2/src/styles/globals.css:271` | `--ease-owl` aliases the Loupe easing token for compatibility | CSS variable only |
| Persisted store and event keys | `frontend_v2/src/stores/ui.store.ts:90`, `frontend_v2/src/features/table/stores/table.store.ts:175`, `frontend_v2/src/features/financial/stores/financial.store.ts:222`, `frontend_v2/src/hooks/use-global-shortcuts.ts:22,28`, `frontend_v2/src/features/agent/components/AgentPage.tsx:107` | Browser state and internal event names | Hidden technical identifiers |
| Storybook namespace | `frontend_v2/src/stories/*.tsx` using `@owl/ui` | Internal component-library namespace; not production app copy | Developer-only |
| Triage docstrings | `backend/routers/triage.py:654,678`, `backend/services/triage/ingest_bridge.py:4,29,125,129`, `backend/services/triage/triage_service.py:748` | Internal docstrings explaining legacy case terminology | Not API response copy |
| Backend service docstrings/defaults | `backend/services/evidence_engine_client.py:6`, `backend/services/neo4j/cellebrite_service.py:5`, `backend/services/geocoder.py:11,322`, `backend/config.py:158`, `backend/services/platform_update_service.py:87` | Internal implementation names, defaults, and user-agent strings | Not customer branding |
| Repository path | `owl-n4j` worktree path | Technical repository identifier | Not included in customer artifacts |
| Internal docs and brand research | `docs/**`, including `docs/frontend/brand-kit-v2.html` and `docs/brand-rebrand/**` | Historical planning, incorporation, audit, and brand exploration evidence | Internal documentation |
| Root planning files | `BACKLOG.md`, `INTEGRATION_PLAN.md`, `WORKING_CHANGELOG.md` | Internal project history | Internal documentation |

## 5. Deduce Historical Note

No live product occurrence of `Deduce` was found. The historical mention is in `docs/business/release-readiness-audit-2026-07-10.md:421`, and this inventory repeats it as audit evidence only.

## 6. Scan And Allowlist

Repeatable command:

```bash
python3 scripts/brand_identity_scan.py --strict
```

The scanner records:

- Cleared Loupe findings.
- Documented open customer-visible blockers in `DOCUMENTED_OPEN_CUSTOMER_VISIBLE`.
- Retained internal identifiers in `INTERNAL_ONLY`.
- Outbound email markers as a review-required boundary.

The automated test fixture in `backend/tests/test_brand_identity_scan.py` exercises the successful repository path, the empty email boundary, and a synthetic regression where a new customer-visible Owl string fails the scan unless it is documented.
