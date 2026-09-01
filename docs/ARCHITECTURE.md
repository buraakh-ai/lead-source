# AGFINTAX Lead Sourcing — Architecture

This document provides visual and technical architecture views. Solid paths are
implemented in the repository. AWS service placement is a reference topology;
the repository does not currently contain infrastructure-as-code.

## 1. System context

```mermaid
flowchart LR
    Operator[Campaign operator] --> UI[Streamlit frontend]
    UI --> API[FastAPI backend]
    API --> LLM[OpenAI / Groq / Ollama]
    API --> Places[Google Places API]
    API --> Search[SerpAPI]
    API --> Web[Public business websites]
    API --> DB[(AWS RDS PostgreSQL\ncrmdb / leadsource)]
    S3[(AWS S3\nnon-secret UI config)] --> UI
    DB --> Downstream[Ad Generator / CRM consumers]
```

## 2. Container and component view

```mermaid
flowchart TB
    subgraph FrontendContainer[Frontend container]
        Streamlit[streamlit_app.py]
        Config[config_loader.py]
        Defaults[streamlit_config.json]
        Config --> Streamlit
        Defaults --> Config
    end

    subgraph BackendContainer[Backend container]
        FastAPI[backend/main.py]
        Pipeline[orchestration/lead_pipeline.py]
        Discovery[orchestration/discovery_v2.py]
        Agents[Agno agents]
        Router[LLM model router]
        Tools[Places / search / sitemap / contact tools]
        Scrapers[requests → Scrapling → Crawl4AI → Playwright]
        Quality[lead_quality.py]
        Persistence[database.py]

        FastAPI --> Pipeline
        Pipeline --> Discovery
        Pipeline --> Agents
        Agents --> Router
        Agents --> Tools
        Tools --> Scrapers
        Pipeline --> Quality
        FastAPI --> Persistence
    end

    Streamlit -->|HTTPS/JSON| FastAPI
    Config -->|GetObject when configured| S3[(S3)]
    Router --> Models[LLM providers]
    Discovery --> Providers[Places and SerpAPI]
    Tools --> PublicWeb[Public web]
    Persistence --> RDS[(RDS PostgreSQL)]
```

## 3. Campaign sequence (V2)

```mermaid
sequenceDiagram
    actor User
    participant UI as Streamlit
    participant API as FastAPI
    participant D as V2 Discovery
    participant P as Provider APIs
    participant A as Lead Puller Agent
    participant W as Public Websites
    participant Q as Quality Engine
    participant DB as PostgreSQL

    User->>UI: Define campaign and run controls
    UI->>API: POST /v2/run-sourcing-campaign
    API->>D: campaign + discovery options
    loop bounded category × location × provider queries
        D->>P: Search/page request
        P-->>D: Candidate records or error
    end
    D->>D: Validate, normalize, deduplicate
    loop bounded enrichment batches
        D->>A: LeadSource batch
        A->>W: Sitemap/page/contact requests
        W-->>A: Public evidence
        A-->>D: Structured leads
    end
    D->>Q: Score and globally deduplicate
    Q-->>API: Ranked leads + metrics
    opt persist_to_database
        API->>DB: Transactional SELECT/INSERT/UPDATE
        DB-->>API: Commit or error
    end
    API-->>UI: Sources, leads, summary, funnel, DB status
    UI-->>User: Results, evidence, CSV, metrics
```

## 4. Frontend configuration flow

```mermaid
flowchart TD
    Start[Streamlit process starts] --> URI{S3 URI configured?}
    URI -- Yes --> Get[GetObject from S3]
    URI -- No --> Local{Local override configured?}
    Local -- Yes --> File[Read local JSON]
    Local -- No --> Bundled[Read bundled JSON]
    Get --> Parse[Parse and validate]
    File --> Parse
    Bundled --> Parse
    Parse --> Valid{Valid?}
    Valid -- Yes --> Merge[Merge partial override over defaults]
    Valid -- No --> Fallback[Warn and use bundled defaults]
    Merge --> Cache[Cache for process lifetime]
    Fallback --> Cache
    Cache --> Render[Render Streamlit UI]
```

S3 takes precedence over a local override. Secrets are deliberately outside
this flow.

## 5. Data relationship view

The supplied PostgreSQL DDL contains no foreign keys; relationships are managed
by the application.

```mermaid
erDiagram
    COMPANIES ||--o{ LEADS : "company_id (application-managed)"
    LEADS ||--o| SOCIAL_PROFILES : "lead_id (application-managed)"

    COMPANIES {
        bigint company_id PK
        varchar company_name
        varchar website
        varchar domain
        varchar email
        varchar phone
        varchar google_place_id
        jsonb attributes
        jsonb raw_data
    }
    LEADS {
        bigint lead_id PK
        bigint company_id
        varchar full_name
        varchar email
        varchar phone
        varchar source
        numeric lead_score
        boolean is_verified
        jsonb attributes
        jsonb raw_data
    }
    SOCIAL_PROFILES {
        bigint social_id PK
        bigint lead_id
        varchar linkedin_url
        jsonb other_profiles
        jsonb raw_data
    }
```

## 6. Reference AWS deployment

```mermaid
flowchart LR
    Internet[Approved internal users] --> Entry[HTTPS endpoint / load balancer]

    subgraph AWS[AWS account]
        subgraph PublicOrEdge[Ingress layer]
            Entry
        end

        subgraph AppNetwork[Application network]
            FE[Frontend container service]
            BE[Backend container service\nor Lambda Web Adapter]
            FE --> BE
        end

        subgraph DataNetwork[Private data subnets]
            RDS[(RDS PostgreSQL\ncrmdb)]
        end

        S3[(S3 config object)] -->|s3:GetObject| FE
        Secrets[Secrets Manager] -->|API keys + DSN| BE
        BE -->|TCP 5432| RDS
        FE --> Logs[CloudWatch Logs]
        BE --> Logs
    end

    BE --> External[LLM, Places, SerpAPI, public websites]
```

Recommended boundaries:

- TLS on public/internal ingress.
- Authentication in front of both frontend and API.
- Frontend role: only its S3 configuration object and logging.
- Backend role: required secrets and logging; network access to RDS and approved
  external services.
- RDS is private; its security group accepts PostgreSQL only from backend
  compute.
- Separate S3 objects, secrets, databases or schemas, and log groups per
  environment.

## 7. Runtime variants

| Variant | Frontend | Backend | Scraping |
|---|---|---|---|
| Local Python | Streamlit process | Uvicorn process | All installed engines. |
| Docker Compose | Dedicated frontend container | Dedicated backend container | Full backend image installs Chromium. |
| AWS containers | Container service chosen by platform team | Container service chosen by platform team | Full image when browser resources are supported. |
| Lambda-compatible backend | External/separate frontend | Lambda Web Adapter image | Defaults to requests + Scrapling (`SCRAPER_MAX_ATTEMPTS=2`). |

## 8. Trust boundaries and sensitive flows

```mermaid
flowchart TB
    ConfigJSON[Non-secret UI JSON] --> Frontend
    UserInput[Campaign input] --> Frontend
    Frontend -->|campaign JSON; no API keys| Backend
    Secrets[Runtime secrets] --> Backend
    Backend -->|public queries| ExternalProviders
    ExternalProviders -->|public source data| Backend
    Backend -->|contact data| Database[(RDS)]
    Backend -->|optional structured details| Logs[(Logs)]
```

The highest-risk paths are secret injection, unrestricted API exposure,
contact-data logging, and external-source compliance. See the security section
of the solution design before production approval.
