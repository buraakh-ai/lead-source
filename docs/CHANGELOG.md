# Project Change Tracker

This file is the team-readable record of product, code, configuration,
deployment, database, documentation, and operational changes. Git commits remain
the technical source of truth.

## How to maintain this tracker

- Add every user-visible, operational, architectural, security, dependency, or
  data-contract change under **Unreleased** in the same pull request.
- Use short bullets under: **Added**, **Changed**, **Fixed**, **Security**,
  **Deployment actions**, **Documentation**, and **Known issues**.
- Include the commit or pull-request reference after merge.
- State whether the deployment team must rebuild, change an AWS/Google setting,
  migrate data, or restart a service.
- Never include API keys, passwords, DSNs, customer data, or other secrets.
- At deployment time, move the Unreleased bullets into a dated release section
  and create a Git tag when the team adopts release versioning.

Recommended bullet format:

```text
- [Area] What changed and why. Impact: <user/runtime impact>.
  Deployment: <none/rebuild/configuration/migration/restart>. Ref: <commit/PR>.
```

---

## Unreleased

### Added

- None.

### Changed

- None.

### Fixed

- None.

### Security

- None.

### Deployment actions

- Google Cloud/AWS configuration remains required for full Google Places
  coverage: enable billing and **Places API**, restrict the key to Places API,
  allow the AWS backend's stable outbound IP, inject it as
  `GOOGLE_PLACES_API_KEY`, and restart the backend.

### Documentation

- Added this project change tracker and linked it from the repository README so
  future product, operational, and deployment changes have one chronological
  team-readable record.

### Known issues

- Google Places returns `REQUEST_DENIED` until the deployment configuration
  above is completed. SerpAPI-backed web discovery remains available as a
  fallback.

---

## 2026-09-01 — Scraping runtime and Places diagnostics

Reference: `1a33090`

### Fixed

- Replaced the incomplete base Scrapling installation with the supported
  `scrapling[fetchers]` extra, including `curl_cffi`, `browserforge`, and other
  required fetcher dependencies.
- Changed the Scrapling fallback engine from browser-oriented
  `StealthyFetcher` to lightweight static `Fetcher.get` with bounded timeout and
  retry behavior; this preserves the Lambda requests → Scrapling fallback.
- Added safe, actionable diagnostics for Google Places `REQUEST_DENIED` errors
  and V2 provider failure logging without exposing the API key.
- Added runtime dependency and diagnostics regression tests; the suite increased
  to 22 tests.

### Deployment actions

- Rebuild and redeploy the backend image to install the new Scrapling extras.
- Complete the external Google Places configuration listed under Unreleased.

---

## 2026-08-31 — Complete product documentation

Reference: `cdc9657`

### Added

- Added the complete solution design covering capabilities, workflows,
  components, contracts, persistence, security, reliability, limitations, and
  roadmap.
- Added architecture diagrams for system context, components, V2 sequence,
  S3 configuration fallback, PostgreSQL relationships, AWS deployment, and
  trust boundaries.
- Added the product and operations guide covering setup, usage, API examples,
  AWS deployment, troubleshooting, smoke testing, and rollback.

### Changed

- Corrected legacy database and V2 branch references in existing documentation.

### Deployment actions

- None; documentation-only release.

---

## 2026-08-31 — Streamlit JSON and S3 configuration

Reference: `31d7172`

### Added

- Extracted non-secret Streamlit defaults, geography, targeting options,
  providers, limits, timeouts, and persistence behavior into
  `frontend/streamlit_config.json`.
- Added S3 loading through `STREAMLIT_CONFIG_S3_URI` and local override loading
  through `STREAMLIT_CONFIG_FILE`.
- Added shape and semantic validation, partial override merging, visible warning
  behavior, bundled-default fallback, and process-level caching.
- Added tests for S3 retrieval, dynamic states/providers, invalid JSON, missing
  files, invalid ranges, and fallback behavior.

### Deployment actions

- Upload the JSON to the approved S3 folder when using remote configuration.
- Set `STREAMLIT_CONFIG_S3_URI` on the frontend and grant its workload role
  `s3:GetObject` for that object.
- Rebuild/redeploy the frontend image because the loader, JSON, and `boto3`
  dependency are packaged into the image.

### Security

- Secrets, API keys, DSNs, and backend credentials remain environment/secret
  manager values and are explicitly excluded from frontend JSON.

---

## 2026-08-31 — CRM schema persistence migration

Reference: `8d965f3`

### Changed

- Replaced persistence to retired `lead_sourcing_*` tables with writes to the
  provisioned `crmdb` database and `leadsource.companies`, `leadsource.leads`,
  and `leadsource.social_profiles` tables.
- Removed runtime DDL and the `DATABASE_AUTO_CREATE_TABLES` setting.
- Mapped campaign, evidence, verification, and source payloads into standard
  columns and JSONB fields.

### Fixed

- Added application-managed idempotent matching and transaction-scoped advisory
  locks for company, lead, and social-profile retries.
- Prevented shared directory domains such as Yellow Pages from being treated as
  official company identities.

### Deployment actions

- Configure `AWS_POSTGRES_DSN` for database `crmdb` through AWS Secrets Manager.
- Confirm `buraq_ai` has connect/select/insert/update permissions on the three
  existing `leadsource` tables; create/delete permissions are not required.

---

## 2026-08-30 — V2 multi-source discovery merged

References: `2724c01`, `957f1c4`, `593f8a6`

### Added

- Added deterministic category × location × provider discovery with Google
  Places, public web, Yellow Pages-indexed, chamber-indexed, and Sulekha-indexed
  providers.
- Added pagination, oversampling, query/page/result limits, candidate rejection
  reasons, provider errors, enrichment batches, and funnel metrics.
- Added the V2 FastAPI endpoint and Streamlit controls/metrics.

### Changed

- Opened the provider-name contract so new adapters can normalize through the
  same `Candidate` → `LeadSource` output format.
- Enabled PostgreSQL persistence by default in both API versions and Streamlit;
  missing DSN configuration still fails safely to CSV.

### Fixed

- Added deterministic candidate and global lead deduplication tests.

### Deployment actions

- Rebuild both backend and frontend images.
- Configure Google Places and/or SerpAPI credentials for useful V2 coverage.

---

## 2026-08-22 to 2026-08-29 — AWS/Lambda and initial RDS handoff

References: `d831d0e`, `a8e65e7`, `4c41766`

### Added

- Split backend and frontend Docker images.
- Added a Lambda Web Adapter-compatible backend image with lightweight scraper
  limits.
- Added optional PostgreSQL persistence and AWS handoff documentation.
- Added health reporting for database configuration.

### Security

- Removed the tracked environment file and documented external secret handling.

---

## 2026-08-09 — Lead verification improvements

Reference: `96fa4d0`

### Changed

- Strengthened public-source verification, evidence handling, contact
  extraction, and decision-maker rules.
- Prohibited guessed URLs/contact details, restricted-platform bypass, and
  sensitive-trait inference in agent instructions.

---

## 2026-08-07 — Initial application

Reference: `23f3de8`

### Added

- Added the initial Agno, FastAPI, and Streamlit lead-sourcing application.
- Added business research, source discovery, lead enrichment, scraping tools,
  campaign models, and local execution workflow.
