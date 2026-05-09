# ShopMart Sales Data Pipeline

Automated AWS data pipeline that processes daily CSV sales uploads from 50 stores, replacing a manual Excel workflow that previously took 3–4 hours per day.

---

## Project Structure

```
shopmart-pipeline/
├── docs/
│   ├── architecture.md          # Architecture documentation (ADRs, failure scenarios)
│   └── architecture-diagram.png # System architecture diagram
│
├── data/
│   ├── sample/                  # Sample CSV files for testing
│   ├── raw/                     # Drop CSV files here to run the local pipeline
│   ├── stage/                   # Intermediate validated files
│   ├── processed/               # Parquet output (partitioned by year/month/day)
│   ├── errors/                  # Rejected records and failed files
│   └── archive/                 # Successfully processed source files
│
├── src/
│   ├── main.py                  # Pipeline entry point (local execution)
│   ├── processor.py             # Orchestrates the ETL flow per file
│   ├── validator.py             # Schema and row-level validation
│   ├── transformer.py           # Dedup, line_revenue, partition columns
│   ├── aggregator.py            # Daily revenue, orders/customer, payment rate
│   ├── logger.py                # Centralised logging setup
│   ├── config.py                # All configuration constants and env vars
│   ├── lambda/
│   │   └── handler.py           # AWS Lambda CSV validation handler
│   └── glue/
│       └── glue_etl_job.py      # AWS Glue PySpark ETL job
│
├── tests/
│   ├── conftest.py              # Shared pytest fixtures
│   ├── test_validator.py        # Validation logic tests
│   ├── test_transformer.py      # Transformation logic tests
│   ├── test_aggregator.py       # Aggregation logic tests
│   └── test_pipeline.py         # End-to-end integration tests
│
├── terraform/
│   ├── main.tf                  # Provider, locals, data sources
│   ├── variables.tf             # Input variables
│   ├── outputs.tf               # Output values
│   ├── s3.tf                    # S3 buckets (raw, stage, processed, errors, archive)
│   ├── iam.tf                   # IAM roles and least-privilege policies
│   ├── lambda.tf                # Lambda validation function
│   ├── glue.tf                  # Glue database, ETL job, crawlers
│   ├── stepfunctions.tf         # Step Functions state machine
│   ├── eventbridge.tf           # EventBridge Scheduler daily trigger
│   ├── cloudwatch.tf            # CloudWatch alarms
│   └── sns.tf                   # SNS alert topic
│
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- pip
- Terraform >= 1.5.0 (for IaC deployment)
- AWS CLI configured with appropriate credentials (for deployment)

### Python Environment

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Run Pipeline (Local)

The local pipeline reads CSV files from `data/raw/`, processes them, and writes output to `data/processed/`. After each run, source files are moved to `data/archive/` (success) or `data/errors/` (failure), leaving `data/raw/` empty.

```bash
# Copy sample files to the raw folder
cp data/sample/*.csv data/raw/

# Run the pipeline
python src/main.py
```

Output locations:
- `data/processed/` — Parquet files partitioned by `year/month/day`
- `data/processed/aggregations/` — CSV aggregation summaries
- `data/errors/` — Rejected records with validation error descriptions
- `data/archive/` — Successfully processed source files

---

## Run Tests

```bash
pytest
```

Run with coverage report:

```bash
pytest --cov=src --cov-report=term-missing
```

All tests should pass without any AWS credentials or network access.

---

## Terraform — Infrastructure Deployment

### Prerequisites

- Terraform >= 1.5.0
- AWS credentials with permissions to create S3, Lambda, Glue, Step Functions, EventBridge, SNS, IAM, and CloudWatch resources

### Deploy

```bash
cd terraform

# Initialise providers and backend
terraform init

# Preview changes
terraform plan -var="alert_email=your-team@example.com"

# Apply infrastructure
terraform apply -var="alert_email=your-team@example.com"
```

### Key Variables

| Variable | Default | Description |
|---|---|---|
| `project` | `shopmart` | Resource name prefix |
| `environment` | `dev` | Deployment environment |
| `aws_region` | `ap-southeast-1` | AWS region |
| `alert_email` | *(required)* | Email for SNS pipeline alerts |
| `pipeline_schedule` | `cron(15 1 * * ? *)` | EventBridge cron (UTC) — 8:15 AM UTC+7 |
| `glue_worker_type` | `G.1X` | Glue worker type |
| `glue_number_of_workers` | `2` | Number of Glue workers |

### Destroy

```bash
terraform destroy -var="alert_email=your-team@example.com"
```

---

## Data Flow Summary

```
CSV Upload (stores)
    ↓
S3 Raw Bucket
    ↓ (EventBridge Scheduler — 8:15 AM daily)
Step Functions
    ↓
Lambda: CSV Validation
    ├── FAIL → S3 Error Bucket + SNS Alert
    └── PASS → S3 Stage Bucket
                ↓
           Glue Crawler (raw schema)
                ↓
           Glue ETL Job
           - Dedup, clean, compute line_revenue
           - Partition by year/month/day
                ↓
           S3 Processed Bucket (Parquet)
                ↓
           Glue Crawler (processed schema)
                ↓
           Glue Data Catalog → Athena → QuickSight
```

---

## Input File Format

Files must follow the naming convention: `store_{store_id}_{YYYYMMDD}.csv`

```
order_id,customer_id,product_id,order_date,quantity,unit_price,payment_status
ORD001,CUST001,PROD101,2024-01-15,2,29.99,paid
```

| Column | Type | Rules |
|---|---|---|
| `order_id` | string | Required, unique |
| `customer_id` | string | Required |
| `product_id` | string | Required |
| `order_date` | date | Required, format `YYYY-MM-DD` |
| `quantity` | number | Required, must be > 0 |
| `unit_price` | number | Required, must be >= 0 |
| `payment_status` | string | Must be `paid`, `pending`, or `failed` |
