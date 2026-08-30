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

## 3. Create PostgreSQL in AWS

In **AWS Console > RDS > Databases > Create database**:

1. Choose **Standard create**, **PostgreSQL**, and a currently supported engine
   version approved by the team.
2. For a development environment, choose **Dev/Test**, database identifier
   `lead-source-dev`, and instance class `db.t4g.micro` where available.
3. Set the master username to `postgres_admin`. Generate a strong password and
   store it in AWS Secrets Manager or an approved password manager.
4. Use 20 GiB GP3 storage and disable storage autoscaling only if the team wants
   a strict development cost ceiling.
5. Select the backend's VPC and private subnets. Set **Public access** to **No**
   for a deployed backend.
6. Attach a database security group whose inbound rule allows PostgreSQL TCP
   `5432` from the backend security group, not from `0.0.0.0/0`.
7. Under additional configuration, set the initial database name to
   `lead_generation`, enable password authentication, backups, and deletion
   protection according to the environment policy.
8. Create the database and wait until its status is **Available**. Record its
   endpoint and port.

For initialization from a developer workstation, use a VPN/bastion into the
VPC. A temporary public RDS endpoint may be used only when approved: restrict
TCP `5432` to that developer's current `/32` public IP and remove the rule after
initialization.

## 4. Configure the local connection

Copy `.env.example` to `.env` and set:

```env
AWS_POSTGRES_DSN=postgresql://postgres_admin:URL_ENCODED_PASSWORD@RDS_ENDPOINT:5432/lead_generation?sslmode=require
DATABASE_AUTO_CREATE_TABLES=true
```

URL-encode special characters in the password. Keep `.env` local. For a
deployed service, store the DSN in AWS Secrets Manager and inject it as the
`AWS_POSTGRES_DSN` environment variable instead of creating an `.env` file.

## 5. Initialize and test the database

From the repository root:

```powershell
python scripts/init_database.py --with-sample-data
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
SELECT lead_record_id, business_name, business_email, lead_score, created_at
FROM ad_generator_leads_v
ORDER BY created_at DESC
LIMIT 20;
```

The initializer creates or upgrades these application objects:

- `lead_sourcing_campaigns`
- `lead_sourcing_runs`
- `lead_sourcing_sources`
- `lead_sourcing_leads`
- `ad_generator_leads_v`

Do not use `--with-sample-data` in production. Remove any temporary workstation
security-group rule after the test. Retain only the backend security group's
access to RDS.
