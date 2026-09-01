# AWS RDS PostgreSQL Handoff

This procedure connects the lead-sourcing application to an AWS RDS for
PostgreSQL database. Run it from an approved AWS account and workstation.

## 1. Prerequisites

The operator needs:

- Access to the `buraakh-ai/lead-source` GitHub repository.
- Python 3.11 or 3.12 and Git.
- An AWS identity allowed to manage RDS, EC2 security groups, and Secrets
  Manager. An administrator can instead create the infrastructure and give the
  operator the endpoint and database credential.
- A selected AWS region and VPC. Use the same VPC as the deployed backend.

Never commit `.env`, database passwords, access keys, or secret values.

## 2. Clone and verify the application

```powershell
git clone https://github.com/buraakh-ai/lead-source.git
cd lead-source
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## 3. Provisioned PostgreSQL target

The application targets the existing `crmdb` database, `leadsource` schema, and
the pre-created `companies`, `leads`, and `social_profiles` tables. The runtime
does not create or alter database objects.

Attach a database security group whose inbound rule allows PostgreSQL TCP 5432
from the backend security group, not from `0.0.0.0/0`. Keep the deployed RDS
instance private.

For initialization from a developer workstation, use a VPN/bastion into the
VPC. A temporary public RDS endpoint may be used only when approved: restrict
TCP `5432` to that developer's current `/32` public IP and remove the rule after
initialization.

## 4. Configure the local connection

Copy `.env.example` to `.env` and set:

```env
AWS_POSTGRES_DSN=postgresql://buraq_ai:URL_ENCODED_PASSWORD@RDS_ENDPOINT:5432/crmdb?sslmode=require
```

URL-encode special characters in the password. Keep `.env` local. For a
deployed service, store the DSN in AWS Secrets Manager and inject it as the
`AWS_POSTGRES_DSN` environment variable instead of creating an `.env` file.

The application user needs `CONNECT` plus `SELECT`, `INSERT`, and `UPDATE` on
the existing `leadsource.companies`, `leadsource.leads`, and
`leadsource.social_profiles` tables. It does not need schema-creation rights.

## 5. Test the database handoff

From the repository root:

```powershell
python -m uvicorn backend.main:app --reload
```

Open `http://localhost:8000/health` and confirm that
`database_configured` is `true`. Then open `http://localhost:8000/docs`, execute
`POST /run-sourcing-campaign`, and set `persist_to_database` to `true`.
The response must report:

```json
{
  "database_saved": true
}
```

The property appears inside `run_summary`. Verify persisted qualified leads
with a PostgreSQL client:

```sql
SELECT lead_id, full_name, email, lead_score, created_at
FROM leadsource.leads
ORDER BY created_at DESC
LIMIT 20;
```

The application also writes related records to `leadsource.companies` and
`leadsource.social_profiles`. It performs no DDL. Remove any temporary
workstation security-group rule after the test and retain only the backend
security group's access to RDS.
