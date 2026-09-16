# Shared AWS destination: team reference

Use **AWS RDS PostgreSQL**, with one table named **public.leads** for all
producers. This matches `config/aws_output.example.json`. A different schema or
table name can be selected by updating both the DDL and app configuration.

The local demo returned two business leads and successfully mapped them to the
destination columns. Neither lead was marked verified. AWS connectivity and
insertion have not been tested because no destination is configured yet.

## Files and deployment

- `sql/shared_destination_schema.sql`: standalone table DDL for the database team.
- `sql/shared_destination_examples.sql`: illustrative Zoom, Bitrix, business
  and individual inserts, displayed with RETURNING and rolled back.
- `docs/SHARED_SQL_OUTPUT.md`: app configuration and terminal demo commands.

Run the schema script manually in the intended database. It intentionally
fails if the table exists; it is not a migration for an existing table. The
older numbered SQL scripts describe a different design and are not prerequisites.
The app itself does not create tables. Configure each producer separately to
insert into this table; the lead-sourcing app does not import Zoom/Bitrix data.

## Column contract

| Column | PostgreSQL type | Required/default | Meaning |
| --- | --- | --- | --- |
| id | bigint identity | Generated primary key | Globally unique destination row ID; omit from inserts |
| business_name | text | Nullable | Business name; may also identify an individual's employer |
| category | text | Required; defaults to individual | business or individual; industry is retained in comment |
| source_id | text | Required | Producer's identifier/code: zoom:0, bitrix:0, lead:0, lead:1 |
| source_name | text | Required | zoom, bitrix, leadsource, or another producer |
| source_type | text | Required | webinar_registration, contact, web_scraping, etc. |
| first_name | text | Nullable | NULL for businesses |
| last_name | text | Nullable | NULL for businesses |
| email | text | Nullable | Available email; not required or unique |
| phone | text | Nullable | Preserve country codes, leading zeros and extensions |
| comment | text | Nullable | Plain-text notes or serialized JSON; accepts both source formats |
| loaded_at | timestamptz | Required; current timestamp default | Ingestion instant; app supplies UTC |
| webinar_id | text | Nullable | External webinar identifier, retaining original formatting |
| file_name | text | Nullable | Import filename when applicable |

Importers should write SQL NULL for missing values, not the display marker `—`
shown in the screenshot. Existing Zoom/Bitrix person importers can omit
business_name and category using explicit INSERT column lists; category defaults
to individual. Business importers must explicitly set category to business and
leave first_name and last_name NULL. The database enforces that rule.

The app supplies email and phone when discovered, full lead/campaign/run details
in comment, and loaded_at for both categories. Business email is used for
business rows; individuals use personal email with business email as fallback.
The app leaves webinar_id and file_name NULL.

## Combining sources and retries

All producers append rows into the same table. Combining sources here means
shared storage, not automatically merging two records describing the same
person or business. Existing records are not overwritten.

Do not make source_id unique: the app currently uses lead:0 for every business
and lead:1 for every individual. Do not make email unique either: the same
contact can occur in Zoom, Bitrix and scraping output. Repeated successful
exports currently insert additional rows. Before enabling automatic retries,
agree on a stable per-record ingestion key and deduplication policy across
producers; the screenshot does not define one.

Once provisioned, configure AWS_POSTGRES_DSN and AWS_OUTPUT_CONFIG_FILE as
described in the output guide, restart the backend, run a small campaign with
persist_to_database=true, check database_saved, and verify the inserted rows:

```sql
SELECT id, business_name, category, source_id, source_name, source_type,
       first_name, last_name, email, phone, comment, loaded_at, webinar_id, file_name
FROM public.leads
ORDER BY id DESC
LIMIT 20;
```

PostgreSQL references: [identity columns](https://www.postgresql.org/docs/17/ddl-identity-columns.html)
and [timestamp/timezone behavior](https://www.postgresql.org/docs/18/datatype-datetime.html).
The database stores timestamptz instants in UTC; query display uses the session timezone.
