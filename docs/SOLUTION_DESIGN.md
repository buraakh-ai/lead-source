# AGFINTAX Lead Sourcing — Solution Design

## 1. Document purpose

This document describes the implemented AGFINTAX public-source lead-sourcing
product: its capabilities, workflows, logical components, data contracts,
integrations, deployment model, security boundaries, operational behavior, and
known limitations. It is the primary design reference for engineering,
operations, QA, and product stakeholders.

Related documents:

- [Architecture](ARCHITECTURE.md)
- [Product and Operations Guide](PRODUCT_OPERATIONS_GUIDE.md)
- [AWS RDS Handoff](AWS_RDS_HANDOFF.md)
- [V2 Multi-Source Discovery](V2_MULTI_SOURCE_DISCOVERY.md)

## 2. Product summary

The product turns a user-defined market campaign into structured business leads
using public sources. A campaign specifies geography, industries,
subcategories, decision-maker roles, inclusion/exclusion keywords, and desired
result counts. The system discovers candidate businesses, enriches public
contact information, validates and scores results, displays evidence and funnel
metrics, exports CSV, and optionally persists records to PostgreSQL for
downstream use.

The solution is a Python application composed of:

- a Streamlit frontend;
- a FastAPI backend;
- Agno-based research and enrichment agents;
- deterministic public-source discovery adapters;
- a bounded multi-engine scraping chain;
- deterministic lead scoring and deduplication;
- AWS PostgreSQL persistence;
- local or S3-hosted non-secret frontend configuration.

## 3. Goals and scope

### 3.1 Implemented goals

- Define reusable, time-bound sourcing campaigns.
- Discover real businesses from Google Places and indexed public-web sources.
- Enrich public phone, email, website, decision-maker, LinkedIn, location, and
  evidence fields when available.
- Avoid fabricating a requested lead count when evidence is insufficient.
- Normalize every provider through common `LeadSource` and `Lead` contracts.
- Produce deterministic completeness scores and verification statuses.
- Deduplicate results before presentation and persistence.
- Export results as UTF-8 CSV and reusable campaign JSON.
- Persist idempotently to `crmdb.leadsource` using a least-privilege database
  user.
- Run locally, in Docker, or as a Lambda-compatible backend container.
- Externalize non-secret Streamlit configuration to JSON and optionally S3.

### 3.2 Out of scope in the current repository

- CRM campaign execution, email delivery, advertising execution, or billing.
- Purchasing or querying paid lead databases such as Apollo or ZoomInfo.
- Bypassing authentication, CAPTCHAs, robots controls, or platform access
  restrictions.
- Guaranteed lead counts when public evidence is unavailable.
- Infrastructure-as-code for VPC, RDS, S3, ECS/App Runner, CloudFront, or IAM.
- User authentication, tenant isolation, role-based access control, and an
  administrative UI.
- Scheduled campaigns and background job queues.
- Formal data-retention/deletion automation.
- An MCP server; the current API is designed so MCP can be added later.

## 4. Users and stakeholders

| Role | Responsibility |
|---|---|
| Campaign operator | Defines targeting, runs campaigns, reviews evidence, exports results. |
| Marketing/Ad Generator consumer | Uses qualified companies and leads stored in PostgreSQL. |
| Application operator | Deploys containers, configures secrets, S3, networking, and logs. |
| Data/platform team | Owns `crmdb`, the `leadsource` schema, permissions, backups, and downstream contracts. |
| Engineering/QA | Extends providers and agents, validates output quality, cost, security, and regressions. |

## 5. Feature catalogue

### Campaign management

- Stable UUID campaign identifier.
- Name, lifecycle status, start/end dates, country, state/region, cities/areas,
  industries, subcategories, desired decision-maker roles, and keyword filters.
- Save a campaign as JSON and reload it later.
- Non-secret UI defaults controlled by bundled or S3 JSON configuration.

### Discovery

- V1 agent-directed discovery through Google Places, SerpAPI public search, and
  sitemap contact-page discovery.
- V2 deterministic query planning across category × location × provider.
- Current V2 provider names: `google_places`, `web_search`, `yellow_pages`,
  `chambers`, and `sulekha`.
- Provider pagination, query caps, result caps, oversampling, rejection reasons,
  provider errors, and funnel metrics.
- Common provider adapter output ensures new providers normalize to the same
  `LeadSource` shape.

### Enrichment and verification

- Public website scraping with a bounded fallback chain.
- Contact extraction prioritizes JSON-LD, footer data, `mailto:`/`tel:` links,
  and then broader page evidence.
- Sitemap-based discovery of Contact, About, Team, Service, and Location pages.
- Public phone, business/personal email, decision-maker name/role, company and
  professional LinkedIn URLs, Google metadata, and evidence URLs.
- No guessing of URLs or contact details; incomplete results remain incomplete.

### Quality and outputs

- Deterministic 0–100 lead score.
- `verified`, `enriched`, or `incomplete` status.
- Deduplication by official domain, then phone, then normalized business name
  and city.
- Streamlit metrics for sources, contacts, decision makers, run duration,
  database status, and the V2 discovery funnel.
- CSV export and structured API responses.

### Persistence

- Writes companies, leads, and social profiles in one PostgreSQL transaction.
- Targets `leadsource.companies`, `leadsource.leads`, and
  `leadsource.social_profiles` in database `crmdb`.
- Uses `SELECT`, `INSERT`, and `UPDATE`; runtime DDL and deletes are not used.
- Application-managed matching plus transaction-scoped advisory locks supports
  safe retries even though the supplied schema has no natural unique keys.
- Preserves flexible campaign, evidence, and source payloads in JSONB.

## 6. End-to-end workflows

### 6.1 Campaign workflow used by Streamlit

1. The frontend loads bundled configuration or an S3 override.
2. The operator defines a campaign and selects V1 or V2.
3. Streamlit sends one request to the corresponding campaign endpoint.
4. The backend validates that industry/subcategory and geography exist.
5. Candidate sources are discovered.
6. The Lead Puller agent scrapes and enriches candidates.
7. Deterministic scoring and global deduplication are applied.
8. If requested, the backend persists results to PostgreSQL.
9. The API returns sources, leads, metrics, and database status.
10. Streamlit displays results and enables JSON/CSV downloads.

### 6.2 V1 workflow

V1 creates a synthetic `BusinessResearch` profile from campaign fields, then
uses the Lead Source Research agent to decide which discovery tools to call.
The returned `LeadSource` list is enriched by the Lead Puller agent and passed
through deterministic quality processing. V1 is flexible but candidate coverage
depends on agent tool decisions.

### 6.3 V2 workflow

V2 constructs a deterministic plan from every configured location, category,
and provider, bounded by `max_queries`. Provider adapters fetch pages until the
raw target is met or sources are exhausted. Candidates missing a name/URL,
closed businesses, and duplicates are rejected. Accepted sources are enriched
in bounded batches, after which leads are globally scored and deduplicated.

The raw target is:

```text
min(1000, max(source_count, lead_count) × oversampling_factor)
```

### 6.4 URL research workflow

The separate `/run-pipeline` surface accepts a target business URL and runs
three sequential Agno workflow steps:

1. Business Research Agent analyzes the business and its ideal customer profile.
2. Lead Source Research Agent finds matching public business sources.
3. Lead Puller Agent extracts and qualifies contacts.

The three stages are also exposed as individual API endpoints.

## 7. Component design

| Component | Implementation | Responsibility |
|---|---|---|
| Frontend | `frontend/streamlit_app.py` | Campaign controls, API invocation, metrics, JSON/CSV export. |
| Frontend config loader | `frontend/config_loader.py` | S3/local JSON retrieval, validation, merge, fallback, process caching. |
| API | `backend/main.py` | Request validation, orchestration calls, persistence handoff, health and errors. |
| Pipeline | `orchestration/lead_pipeline.py` | V1/V2 sequencing, batching, enrichment, scoring, summaries. |
| V2 discovery | `orchestration/discovery_v2.py` | Query plan, provider adapters, pagination, normalization, rejection metrics. |
| Agents | `agents/` | Structured LLM research and enrichment behavior. |
| Prompts | `prompts/*.yaml` | Version-controlled agent instructions and evidence restrictions. |
| Skills | `skills/` | Reusable ICP and contact-extraction guidance/scripts. |
| Model router | `llm/router.py` | Low/high model selection, retry, fallback, Groq parser model. |
| Tools | `tools/` | Places, search, sitemap discovery, page fetch, contact extraction. |
| Scraping engines | `tools/scraping/` | Requests → Scrapling → Crawl4AI → Playwright fallback. |
| Quality | `lead_quality.py` | Evidence normalization, scoring, verification status, deduplication. |
| Persistence | `database.py` | Transactional CRM mapping and application-managed upserts. |
| Contracts | `schemas.py` | Pydantic request, response, campaign, source, lead, and metric models. |

## 8. Data design

### 8.1 Primary application contracts

- `CampaignTarget`: market and campaign controls.
- `BusinessResearch`: business identity, services, ICP, and ICP categories.
- `LeadSource`: normalized candidate business and supporting discovery evidence.
- `Lead`: enriched contact, provenance, quality, and business metadata.
- `DiscoveryMetrics`: V2 query, candidate, rejection, provider, and batching data.
- `RunSummary`: run timing, result counts, verification counts, and database status.

### 8.2 PostgreSQL mapping

| Table | Content | Match order |
|---|---|---|
| `leadsource.companies` | Business identity, domain, location, contacts, Google metadata, JSONB evidence/raw data. | Google Place ID → official domain → normalized name/location. |
| `leadsource.leads` | Person/business lead, contact, company association, source, score, status, JSONB evidence/raw data. | Email → phone/company → full name/company. |
| `leadsource.social_profiles` | Individual LinkedIn URL and other profiles, including company LinkedIn in JSONB. | Lead ID. |

Shared directory domains are excluded from official-domain matching so two
businesses on the same directory do not collapse into one company.

### 8.3 Lead score

| Evidence | Points |
|---|---:|
| Business email | 25 |
| Phone | 20 |
| Decision-maker name | 20 |
| Decision-maker role | 10 |
| LinkedIn URL | 10 |
| Website | 10 |
| At least one evidence URL | 5 |

`verified` requires email, phone, decision-maker name and role, plus evidence.
Scores of at least 45 otherwise become `enriched`; lower scores are
`incomplete`.

## 9. API design

| Method and path | Use |
|---|---|
| `GET /` | Service discovery response. |
| `GET /health` | Process health and whether a database DSN is configured. |
| `POST /run-sourcing-campaign` | V1 campaign discovery, enrichment, quality, optional persistence. |
| `POST /v2/run-sourcing-campaign` | Deterministic multi-provider workflow and funnel metrics. |
| `POST /research-business` | URL → `BusinessResearch`. |
| `POST /find-lead-sources` | Research + target → normalized source candidates. |
| `POST /pull-leads` | Sources + target → enriched leads. |
| `POST /run-pipeline` | Complete three-stage URL workflow. |

FastAPI publishes the exact OpenAPI schema at `/docs` and `/openapi.json`.

## 10. Configuration design

### Backend/secrets

Backend settings use environment variables loaded through
`config/settings.py`. API keys and `AWS_POSTGRES_DSN` must be injected by the
runtime or a secret manager and must never be stored in frontend JSON.

### Frontend

`frontend/streamlit_config.json` is the complete non-secret default. Resolution:

1. If `STREAMLIT_CONFIG_S3_URI` exists, read that S3 object.
2. Otherwise, if `STREAMLIT_CONFIG_FILE` exists, read the local path.
3. Otherwise, use the bundled JSON.
4. Validate known keys, types, ranges, providers, and default selections.
5. Merge partial valid overrides over bundled defaults.
6. On retrieval, parsing, or validation error, show a warning and use defaults.

The result is cached for the Streamlit process; restart the frontend to load an
updated S3 object.

## 11. Security and privacy

- Keep keys and DSNs in AWS Secrets Manager or runtime secrets.
- The frontend image contains no backend agents, search keys, or database code.
- Grant the frontend role only `s3:GetObject` for its configuration object.
- Grant `buraq_ai` only connect/select/insert/update permissions already defined
  by the data team.
- Keep RDS private and allow TCP 5432 only from the backend security group.
- Disable `LOG_SOURCING_DETAILS` in production if contact information should
  not be retained in application logs.
- Review CORS before public deployment; the current API allows all origins.
- Add authentication and authorization before exposing the product beyond a
  trusted internal network.
- The prompts prohibit sensitive-trait inference and bypassing access controls.
- Provider terms, directory licensing, retention periods, and applicable privacy
  obligations require organizational approval before production use.

## 12. Reliability and failure behavior

- LLM primary requests retry with exponential backoff; cloud failures can fall
  back to Ollama when configured and reachable.
- Scraping engines are ordered cheapest-to-heaviest and bounded by
  `SCRAPER_MAX_ATTEMPTS`.
- V2 caps queries, pages, results, target candidates, enrichment batches, and
  final results.
- Provider failures are counted without fabricating candidates.
- Database failure does not discard discovered results; the response reports
  failure and CSV remains available.
- PostgreSQL writes occur in one transaction.
- S3 frontend configuration failures fall back to bundled defaults.

## 13. Observability

- FastAPI emits campaign start/completion/failure logs.
- V2 responses expose planned/executed queries, provider counts/errors,
  rejection reasons, enrichment batches, and funnel exhaustion.
- `/health` reports process readiness and DSN presence, not a live database
  connectivity check.
- `DEBUG_MODE` enables verbose agent/tool traces.
- `LOG_SOURCING_DETAILS` controls per-source/per-lead structured logging.
- In ECS, configure the `awslogs` driver to send stdout/stderr to CloudWatch.

## 14. Deployment design

The repository supplies separate backend and frontend Dockerfiles plus Docker
Compose for local execution. It also supplies a Lambda Web Adapter backend
image. The exact production AWS compute service and network topology are an
environment decision; no Terraform/CloudFormation is included.

The normal AWS boundary is:

- frontend compute reads non-secret config from S3 and calls the backend;
- backend compute reads secrets, calls LLM/search/public-web providers, and
  connects privately to RDS;
- RDS stores normalized CRM records;
- CloudWatch receives container/Lambda logs.

## 15. Testing and acceptance

The offline suite covers campaign models, quality scoring/deduplication,
provider normalization, V2 discovery metrics/batching, CRM SQL mapping and
retry behavior, and S3 configuration validation/fallback. Run:

```bash
python -m unittest discover -s tests -v
```

Production acceptance additionally requires live tests for configured LLMs,
Google Places, SerpAPI, representative websites, S3/IAM, RDS connectivity,
container health, cost, latency, and output quality.

## 16. Known limitations and recommended next steps

1. Add authentication, authorization, rate limiting, and restrictive CORS.
2. Add infrastructure-as-code and explicit dev/test/prod environment profiles.
3. Add a queue/worker architecture for long campaigns instead of holding one
   HTTP request for up to the frontend timeout.
4. Add database-native unique constraints where the data team approves them;
   advisory locks protect application concurrency but constraints provide a
   stronger cross-client guarantee.
5. Add live dependency health checks and metrics/alerts.
6. Add retention, erasure, consent/legal-basis, and audit procedures.
7. Replace indexed-directory adapters with approved official APIs or licensed
   feeds where required.
8. Add contract/integration tests against a disposable PostgreSQL schema.
9. Remove or archive legacy SQL initialization artifacts after confirming no
   external workflow still relies on them.
10. Promote V2 after representative quality, cost, and load acceptance.
