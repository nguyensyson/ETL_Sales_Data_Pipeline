# Part 1: Architecture Design

## Task 1.1: Architecture Diagram

### Architecture Overview

The pipeline is designed as a fully event-driven, serverless architecture on AWS. It automatically processes CSV sales files uploaded by 50 stores each morning, validates data quality, transforms and aggregates the data, and makes results available for BI consumption — replacing the manual Excel process entirely.

**Diagram:** See `docs/architecture-diagram.png`

---

### Data Flow: End-to-End

```
CSV on local
    │
    │ (1) Manual/automated upload
    ▼
S3 Raw-data bucket
    │
    │ (2) S3 Event Notification
    ▼
Amazon EventBridge
    │
    │ (3) Rule triggers workflow
    ▼
AWS Step Functions (Orchestrator)
    │
    │ (4) Invoke validation step
    ▼
AWS Lambda — Validate CSV file
    │
    ├─── (5a) Invalid file ──► S3 Error-data bucket
    │                               │
    │                               └──► Amazon SNS (error notification)
    │
    └─── (5b) Valid file ───► S3 Stage-data bucket
                                    │
                                    │ (6) Trigger ETL job
                                    ▼
                               AWS Glue (ETL Job)
                                    │
                                    │ (7) Write processed output
                                    ▼
                          S3 Processed-data bucket
                                    │
                                    │ (8) Trigger crawler
                                    ▼
                     Glue Crawler — Create/update schema
                                    │
                                    │ (9) Register table metadata
                                    ▼
                          AWS Glue Data Catalog
                                    │
                          ┌─────────┴──────────┐
                          │ (Analytics layer)   │
                          ▼                     ▼
                    Amazon Athena        Amazon QuickSight
                                    │
                          (10) SNS success notification
```

---

### AWS Services Selection

| Step | Service | Reason |
|------|---------|--------|
| **Ingestion** | **Amazon S3 (Raw)** | Durable, scalable object storage. Native event notification support. Cost-effective for storing raw CSV files with lifecycle policies. |
| **Event trigger** | **Amazon EventBridge** | Decouples the S3 upload event from the processing workflow. Supports fine-grained filtering (e.g., only `.csv` files matching `store_*` pattern), retry policies, and dead-letter queues — more robust than direct S3→Lambda triggers for orchestration. |
| **Orchestration** | **AWS Step Functions** | Manages the multi-step workflow (validate → transform → notify) with built-in error handling, retries, and state visibility. Avoids chaining Lambda functions directly, which is fragile and hard to monitor. |
| **Validation** | **AWS Lambda** | Lightweight, fast execution for schema validation and data quality checks. Stateless and cost-efficient for short-lived tasks (< 15 min). Ideal for the validation step which does not require heavy compute. |
| **Staging** | **Amazon S3 (Stage)** | Temporary holding area for validated files before ETL. Separates concerns between validation and transformation. |
| **ETL / Transform** | **AWS Glue** | Managed Spark environment suited for processing 50 files × up to 5,000 rows. Handles deduplication, aggregation, and Parquet conversion natively. Scales automatically without managing servers. See ADR-002. |
| **Processed storage** | **Amazon S3 (Processed)** | Stores output in Parquet format partitioned by date. Optimized for analytical queries via Athena. |
| **Error storage** | **Amazon S3 (Error)** | Isolates bad records for auditing and reprocessing. Keeps the processed bucket clean. |
| **Schema registry** | **AWS Glue Crawler + Data Catalog** | Automatically infers and registers the schema of processed Parquet files. Enables Athena and QuickSight to query data without manual DDL. |
| **Query layer** | **Amazon Athena** | Serverless SQL on S3. No infrastructure to manage. Pay-per-query model is cost-efficient for BI team ad-hoc queries. |
| **Visualization** | **Amazon QuickSight** | Native AWS BI tool with direct Athena integration. Supports scheduled dashboard refresh aligned with the daily pipeline run. |
| **Notifications** | **Amazon SNS** | Sends success/failure alerts to the BI team via email or SMS. Triggered by Step Functions on both error paths and successful completion. |
| **Observability** | **CloudWatch + CloudWatch Alarms** | Centralized logging for Lambda and Glue jobs. Alarms on error rates, job duration, and DLQ depth. |

---

## Task 1.2: Architecture Decision Records (ADRs)

### ADR-001: Use Amazon EventBridge as the Pipeline Trigger

**Context:**
The pipeline must start automatically whenever a new CSV file is uploaded to S3. With 50 stores uploading files in a 2-hour window (6:00–8:00 AM), the trigger mechanism needs to be reliable, filterable, and decoupled from the processing logic. A direct S3 event notification to Lambda or Step Functions is possible but tightly couples storage to compute.

**Decision:**
Use Amazon EventBridge with an S3 event source rule to trigger the Step Functions workflow. The rule filters on `s3:ObjectCreated:*` events where the object key matches the pattern `store_*_*.csv`, ensuring only valid store files initiate the pipeline.

**Alternatives Considered:**

| Alternative | Reason Rejected |
|-------------|-----------------|
| S3 → Lambda (direct trigger) | Tightly couples S3 to Lambda. No built-in filtering by key pattern at the event level. Harder to add routing logic later. |
| S3 → SQS → Lambda | Adds operational overhead. SQS is better suited when consumers need to pull at their own pace; here we want immediate push-based triggering. |
| Scheduled EventBridge rule (cron) | Polling-based approach. Would process all files at a fixed time rather than reacting to each upload. Increases latency and complicates partial-failure handling. |

**Consequences:**
- ✅ Loose coupling — S3 and Step Functions are independent; either can be replaced without affecting the other.
- ✅ Fine-grained filtering — only files matching the naming convention trigger the pipeline, preventing accidental triggers from unrelated uploads.
- ✅ Built-in retry and dead-letter queue support on the EventBridge rule.
- ⚠️ Slight added latency (~1–2 seconds) compared to a direct S3 trigger, which is acceptable given the batch nature of the workload.
- ⚠️ EventBridge has a limit of 300 rules per event bus by default — not a concern at 50 stores but worth noting for future scale.

---

### ADR-002: Use AWS Glue Instead of Lambda for ETL Processing

**Context:**
After validation, each CSV file must be cleaned (deduplication, null handling), enriched (`line_revenue = quantity * unit_price`), aggregated (daily revenue, top products, payment success rate), and written to S3 in an analytics-friendly format. Lambda has a 15-minute execution limit and 10 GB memory cap, which may be insufficient for large files (up to 5,000 rows × 50 files = 250,000 rows/day) and complex aggregations.

**Decision:**
Use AWS Glue (PySpark ETL job) for the transformation step. Glue provides a managed Apache Spark environment that scales horizontally, supports native Parquet output, and integrates directly with the Glue Data Catalog for automatic schema registration.

**Alternatives Considered:**

| Alternative | Reason Rejected |
|-------------|-----------------|
| AWS Lambda (Python + pandas) | 15-minute timeout and memory limits are risky for large files. Pandas is not distributed — cannot scale horizontally. Dependency packaging (pandas, pyarrow) adds complexity. |
| AWS EMR | Significantly higher cost and operational overhead for this data volume. Cluster startup time (3–5 min) adds latency. Overkill for 250K rows/day. |
| AWS Glue DataBrew | Visual, no-code tool — less flexible for custom aggregation logic. Cannot be version-controlled as cleanly as a PySpark script. |
| ECS / Fargate (containerized Python) | More control but requires container management, ECR, and task definition maintenance. No native Data Catalog integration. |

**Consequences:**
- ✅ Handles current and future data volume without code changes — just adjust DPU allocation.
- ✅ Native integration with Glue Data Catalog — schema is registered automatically after each run.
- ✅ Built-in job bookmarking to avoid reprocessing already-handled files (supports BR-7).
- ⚠️ Glue job startup time is ~1–2 minutes (cold start for Spark context). Acceptable for a daily batch pipeline but not suitable for real-time use cases.
- ⚠️ Higher cost per run compared to Lambda for very small files. Mitigated by using Glue's 1/16 DPU (Flex execution) for non-urgent jobs.

---

### ADR-003: Store Processed Data in Parquet Format

**Context:**
Processed data must be stored in a format suitable for analytics queries (BR-4) and accessible by BI tools like QuickSight (BR-6). The BI team will run queries such as daily revenue aggregations, top product rankings, and payment success rates — typically column-oriented access patterns on large datasets.

**Decision:**
Store all processed output in Apache Parquet format, partitioned by `order_date` (e.g., `s3://processed/year=2024/month=01/day=15/`). Use Snappy compression. Register the schema in the Glue Data Catalog so Athena can query it directly.

**Alternatives Considered:**

| Alternative | Reason Rejected |
|-------------|-----------------|
| CSV (plain text) | No compression, no columnar optimization. Full table scans on every query — expensive with Athena (pay per byte scanned). No schema enforcement. |
| JSON / NDJSON | Verbose format, larger file size than Parquet. Row-oriented — inefficient for column-selective analytical queries. |
| ORC | Also columnar and compressed, but Parquet has broader ecosystem support (Athena, Glue, Spark, pandas all prefer Parquet). Less tooling friction. |
| Delta Lake / Iceberg | Adds ACID transaction support and time-travel, but introduces significant complexity. Not justified for an append-only daily batch pipeline at this scale. |

**Consequences:**
- ✅ 60–90% storage reduction compared to CSV due to columnar compression.
- ✅ Athena query costs reduced significantly — only columns referenced in the query are scanned.
- ✅ Partition pruning on `order_date` means daily queries scan only the relevant partition, not the entire dataset.
- ✅ QuickSight can connect directly via Athena with no additional transformation.
- ⚠️ Parquet files are not human-readable — debugging requires Athena, Glue, or a local Parquet reader.
- ⚠️ Small file problem: if each store produces a separate Parquet file, Athena performance degrades. Mitigated by having the Glue job merge all store files for a given day into a single partitioned output.

---

## Task 1.3: Failure Scenarios

### Scenario 1: Malformed or Corrupt CSV File

**What happens?**
A store uploads a CSV file with incorrect column names, wrong data types, or encoding issues (e.g., UTF-16 instead of UTF-8). The Lambda validation step fails to parse the file.

**How does the system detect it?**
The Lambda function performs schema validation on every file: checks for required columns (`order_id`, `customer_id`, `product_id`, `order_date`, `quantity`, `unit_price`, `payment_status`), validates data types, and checks file encoding. Any failure raises a structured exception caught by Step Functions.

**Recovery strategy:**
Step Functions routes the file to the `S3 Error-data` bucket with a metadata tag indicating the failure reason. The original file is preserved in `S3 Raw-data` for manual inspection. The pipeline continues processing other files — one bad file does not block the rest.

**Who needs to be notified?**
SNS sends an alert to the BI team and the store operations team, including the store ID, filename, and error description. The store is expected to re-upload a corrected file.

---

### Scenario 2: AWS Glue ETL Job Failure

**What happens?**
The Glue job fails mid-execution due to an out-of-memory error, a Spark exception on unexpected data values (e.g., non-numeric `unit_price`), or a transient AWS service issue.

**How does the system detect it?**
Step Functions monitors the Glue job status via the `GlueStartJobRun` + `GlueGetJobRun` integration. If the job transitions to `FAILED` or `ERROR` state, Step Functions catches the error and transitions to the failure branch.

**Recovery strategy:**
Step Functions retries the Glue job up to 2 times with exponential backoff (supports BR-8). If all retries are exhausted, the staged file remains in `S3 Stage-data` (not deleted) so the job can be manually re-triggered or automatically retried in the next pipeline run. Glue job bookmarking ensures already-processed records are not duplicated on retry.

**Who needs to be notified?**
SNS sends an alert to the data engineering team with the job run ID, error message, and affected file. CloudWatch Alarm triggers if the Glue job failure rate exceeds a threshold within a time window.

---

### Scenario 3: Missing Store Files (Incomplete Daily Upload)

**What happens?**
One or more stores fail to upload their CSV file during the 6:00–8:00 AM window due to network issues, store system downtime, or human error. The pipeline processes only the files that arrived, resulting in incomplete daily aggregations.

**How does the system detect it?**
A scheduled EventBridge rule triggers a Lambda function at 8:30 AM (after the upload window closes) to audit the `S3 Raw-data` bucket. It compares the list of received files against the expected list of 50 store IDs for the current date. Any missing store IDs are flagged.

**Recovery strategy:**
The audit Lambda publishes a report of missing stores to SNS. The daily aggregation job proceeds with available data and marks the output with a `partial=true` metadata flag so downstream consumers (Athena, QuickSight) can identify incomplete days. When the missing store uploads its file late, the pipeline reprocesses it and updates the aggregation for that day.

**Who needs to be notified?**
SNS notifies the BI team and store operations team with the list of missing store IDs. The BI team is aware that the day's dashboard may show incomplete data until all files are received.

---

### Scenario 4: S3 Bucket Unavailable or Permission Denied

**What happens?**
A misconfigured IAM policy change or an S3 service disruption causes the Lambda or Glue job to fail when attempting to read from `S3 Stage-data` or write to `S3 Processed-data`.

**How does the system detect it?**
Lambda and Glue jobs throw `AccessDeniedException` or `NoSuchBucket` errors, which are caught by Step Functions error handlers. CloudWatch Logs capture the full error stack trace.

**Recovery strategy:**
Step Functions transitions to the error state and sends an SNS alert immediately — no retries are attempted for permission errors (retrying would not resolve the root cause). For transient S3 service issues, Step Functions retries with backoff. The IAM team is alerted to review recent policy changes via CloudTrail audit logs.

**Who needs to be notified?**
SNS alerts the data engineering team and cloud infrastructure team. For `AccessDeniedException`, the alert includes the IAM principal and the denied action to accelerate diagnosis.
