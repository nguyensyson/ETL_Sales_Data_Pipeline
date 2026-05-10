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
│   ├── sns.tf                   # SNS alert topic
│   └── analytics.tf             # Athena workgroup, named queries, QuickSight data source
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
| `enable_quicksight` | `false` | Enable QuickSight Athena data source |
| `quicksight_admin_user` | `""` | QuickSight IAM username (required when `enable_quicksight = true`) |

### Destroy

```bash
terraform destroy -var="alert_email=your-team@example.com"
```

---

## Analytics Setup — Athena & QuickSight

The analytics layer allows the BI team to query processed sales data directly using SQL (Athena) and build dashboards (QuickSight). It sits on top of the Glue Data Catalog populated by the pipeline.

### Step 1: Athena (automatically provisioned)

Athena is fully provisioned by Terraform as part of the base deployment — no extra steps needed. After `terraform apply`, the following are ready to use:

- **Workgroup**: `shopmart-dev-workgroup`
- **Query results bucket**: `shopmart-dev-athena-results-<account-id>`
- **3 pre-built named queries** available in the Athena console:

| Query name | Description |
|---|---|
| `shopmart-dev-daily-revenue` | Total revenue, orders, and unique customers per day |
| `shopmart-dev-top-products` | Top 20 products by revenue |
| `shopmart-dev-payment-success-rate` | Daily payment success rate (%) |

**Run a query via AWS Console:**

1. Open **Amazon Athena** in the AWS Console
2. Select workgroup `shopmart-dev-workgroup`
3. Select database `shopmart_dev_catalog`
4. Open **Saved queries** tab → select a named query → click **Run**

**Run a query via AWS CLI:**

```bash
aws athena start-query-execution \
  --query-string "SELECT order_date, SUM(line_revenue) AS total_revenue FROM shopmart_dev_catalog.processed GROUP BY order_date ORDER BY order_date DESC" \
  --work-group shopmart-dev-workgroup \
  --region ap-southeast-1
```

> **Note:** Athena requires the Glue Crawler to have run at least once so the `processed` table schema is registered. The pipeline does this automatically on each daily run.

---

### Step 2: QuickSight Setup

QuickSight requires a **manual subscription step** before Terraform can provision the data source. This is an AWS account-level action that cannot be automated via Terraform.

#### 2.1 Subscribe to QuickSight

1. Open the [Amazon QuickSight console](https://quicksight.aws.amazon.com)
2. Click **Sign up for QuickSight**
3. Choose edition: **Enterprise** (recommended) or Standard
4. Set **QuickSight account name** (e.g., `shopmart`)
5. Set **notification email**
6. Under **IAM role**, select **Use an existing role** and choose the role output by Terraform:
   ```bash
   terraform output quicksight_role_arn
   # → arn:aws:iam::<account-id>:role/shopmart-dev-quicksight-role
   ```
7. Complete subscription

#### 2.2 Get your QuickSight username

After subscribing, find your QuickSight username:

```bash
aws quicksight list-users \
  --aws-account-id $(aws sts get-caller-identity --query Account --output text) \
  --namespace default \
  --region ap-southeast-1 \
  --query "UserList[*].UserName"
```

#### 2.3 Provision the Athena data source via Terraform

```bash
cd terraform

terraform apply \
  -var="alert_email=your-team@example.com" \
  -var="enable_quicksight=true" \
  -var="quicksight_admin_user=your-quicksight-username"
```

This creates an **Athena data source** in QuickSight named `ShopMart Sales Pipeline (Athena)` pointing to the `shopmart-dev-workgroup`.

#### 2.4 Create a Dataset in QuickSight

1. Open **QuickSight** → **Datasets** → **New dataset**
2. Select data source: **ShopMart Sales Pipeline (Athena)**
3. Select database: `shopmart_dev_catalog`
4. Select table: `processed`
5. Choose **Import to SPICE** (for fast dashboard performance) or **Direct query**
6. Click **Edit/Preview data** to verify columns, then **Save & publish**

#### 2.5 Build Dashboards

Suggested analyses for the BI team:

| Dashboard | Fields to use |
|---|---|
| Daily Revenue Trend | `order_date` (X-axis), `line_revenue` SUM (Y-axis) — Line chart |
| Top Products | `product_id` (dimension), `line_revenue` SUM (metric) — Bar chart |
| Payment Success Rate | `order_date`, `payment_status` — Donut or KPI chart |
| Revenue by Store | `store_id` (if available), `line_revenue` SUM — Heat map |

---

### Analytics Architecture Summary

```
Glue Data Catalog (processed table schema)
        ↓
Amazon Athena (shopmart-dev-workgroup)
  - Queries S3 Processed Bucket (Parquet, partitioned by year/month/day)
  - Results stored in S3 Athena Results Bucket (auto-expire 30 days)
        ↓
Amazon QuickSight
  - Data source: Athena workgroup
  - Dataset: processed table
  - Dashboards: daily revenue, top products, payment success rate
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
