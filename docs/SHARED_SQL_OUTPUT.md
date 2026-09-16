# Shared AWS SQL output demo

## Preview without AWS or a frontend

With the backend running, scrape actual leads and print their mapped destination
rows in one command (PowerShell):

```powershell
.\scripts\run_terminal_demo.ps1 -City Irvine -State California -Industry Restaurants -Count 2
```

This disables database saving and stores the response in the Git-ignored
`output/actual-campaign-response.json`. It uses the configured scraping/LLM
providers and may take several minutes.

Run `python scripts/preview_sql_output.py` for clearly labeled illustrative
business and individual rows. This calls the actual export mapper and never
connects to a database. Business first/last names are NULL even with a known owner.

To preview real results, run the PowerShell API example below with
`persist_to_database = $false`, then save and map the response:

```powershell
$result | ConvertTo-Json -Depth 30 | Set-Content -Encoding utf8 campaign-response.json
python scripts/preview_sql_output.py --input campaign-response.json
```

Use `--config config/aws_output.json` to preview a team's custom source settings.
Keep saved responses containing contact information out of Git.

## Configure the database later

The team reference is [SHARED_DESTINATION_SCHEMA.md](SHARED_DESTINATION_SCHEMA.md),
with standalone DDL in `sql/shared_destination_schema.sql` and illustrative
multi-source inserts in `sql/shared_destination_examples.sql`.

The repository's existing database driver is PostgreSQL. This adapter uses it
to insert qualified leads into the single shared table from the supplied image.
Confirm the actual AWS engine and table name before connecting.

1. Copy `config/aws_output.example.json` to `config/aws_output.json` and set
   `schema_name` and `table_name` to the existing destination.
2. Set these values in the local `.env` (or inject environment variables):

   ```env
   AWS_POSTGRES_DSN=postgresql://USER:URL_ENCODED_PASSWORD@HOST:5432/DATABASE?sslmode=require
   AWS_OUTPUT_CONFIG_FILE=config/aws_output.json
   ```

3. Start the backend with `python -m uvicorn backend.main:app`.
4. Run from PowerShell, without starting the frontend:

   ```powershell
   $body = @{
     campaign = @{ campaign_name = "Client demo"; industries = @("Restaurants"); cities_or_areas = @("Irvine") }
     source_count = 3
     lead_count = 3
     persist_to_database = $true
   } | ConvertTo-Json -Depth 5
   $result = Invoke-RestMethod -Method Post -Uri http://localhost:8000/run-sourcing-campaign -ContentType application/json -Body $body
   $result.run_summary
   ```

Both `/run-sourcing-campaign` and `/v2/run-sourcing-campaign` use this mapping
when the config path is set. Check `database_saved` and `database_message` in
the response; a successful HTTP response alone does not prove database saving.
An empty config path retains the existing three-table CRM behavior.

| Destination column | Mapping |
| --- | --- |
| id | Omitted; destination must generate unique row IDs |
| business_name | Business name, falling back to lead name for businesses |
| category | `business` by default; `individual` only for explicitly individual leads |
| source_id | Configurable: `lead:0` for businesses, `lead:1` for individuals |
| source_name / source_type | Configurable: `leadsource` / `web_scraping` |
| first_name / last_name | NULL for businesses, including those with a known owner; split individual decision-maker name or name at first whitespace |
| email | Business email for businesses; personal email then business email for individuals |
| phone | Original string, retaining prefixes and leading zeros |
| comment | JSON containing the complete original lead, campaign and run ID |
| loaded_at | UTC export timestamp |
| webinar_id / file_name | NULL; this app does not originate webinar/file imports |

The image's IDs 3 and 4 are treated as example row IDs, not fixed IDs to reuse.
If 3 and 4 are instead your assigned source identifiers, set
`business_source_id` to `"3"` and `individual_source_id` to `"4"`.
Industry categories and all enrichment fields remain in the JSON comment.
The destination `comment` must accommodate the full payload (PostgreSQL `text`);
optional fields must allow NULL. No schema creation or changes are performed.
Discovered candidate pages are not inserted as additional leads.

Each export is one transaction and only inserts rows; it never updates rows
from Zoom, Bitrix or other sources. Repeating a successful run inserts another
batch. Retry deduplication requires an agreed destination unique key, which
the screenshot does not specify. The destination account needs INSERT and
permission to use the ID sequence if applicable.
