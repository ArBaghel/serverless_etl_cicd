# Real-Time Air Quality ETL Pipeline (S3 → Lambda → DynamoDB)

A serverless ETL pipeline that fetches live Air Quality Index (AQI) readings from the WAQI API, stores raw data in S3, auto-triggers a Lambda function to clean and validate the data, and loads the results into DynamoDB — with full audit logging via CloudWatch.

---

## Architecture Overview

```
┌─────────────────────┐
│   WAQI Public API   │  (third-party data source)
│  waqi.info/api/     │
└────────┬────────────┘
         │ HTTP GET (city AQI readings)
         ▼
┌─────────────────────┐
│  fetch_and_upload   │  (local Python script)
│       .py           │  Builds raw JSON/CSV → uploads to S3
└────────┬────────────┘
         │ s3.put_object()
         ▼
┌─────────────────────────────────────────┐
│         Amazon S3                       │
│   Bucket: serverless-etl-aqi-pipeline   │
│   Prefix: raw/                          │
│   ├── aqi_raw_*.json                    │
│   └── city_aqi_data.csv                 │
└────────┬────────────────────────────────┘
         │ s3:ObjectCreated:Put event
         │ (prefix: raw/, suffix: .csv / .json)
         ▼
┌─────────────────────┐
│    AWS Lambda       │
│  lambda_function.py │
│  ┌───────────────┐  │
│  │   Extract     │  │  Read raw file from S3
│  │   Transform   │  │  Validate + clean + enrich
│  │   Load        │  │  Write to DynamoDB
│  │   Audit       │  │  Log summary to CloudWatch
│  └───────────────┘  │
└────────┬────────────┘
         │
    ┌────┴─────────────────────┐
    │                          │
    ▼                          ▼
┌──────────────────┐   ┌──────────────────────┐
│  Amazon DynamoDB │   │  Amazon CloudWatch   │
│  clean_aqi_      │   │  Logs                │
│  records table   │   │  AUDIT_SUMMARY log   │
└──────────────────┘   └──────────────────────┘
```

---

## ETL Flow (inside Lambda)

```
S3 Event Trigger
      │
      ▼
┌─────────────────────────────┐
│  EXTRACT                    │
│  Read file from S3          │
│  Detect format (.json/.csv) │
│  Parse into list of dicts   │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  VALIDATE (per record)      │
│  ┌──────────────────────┐   │
│  │ city present?        │   │
│  │ aqi is numeric?      │   │
│  │ aqi >= 0?            │   │
│  └──────┬───────────────┘   │
│         │                   │
│    Pass │        Fail       │
│         │          │        │
│         │     rejected++    │
└─────────┼───────────────────┘
          │
          ▼
┌─────────────────────────────────────────────┐
│  TRANSFORM                                  │
│  city   → Title Case (standardized)         │
│  aqi    → int (type-safe)                   │
│  pollutant → lowercase                      │
│  aqi_category → derived (EPA classification)│
│  record_id → city + timestamp + uuid suffix │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────┐
│  LOAD                       │
│  DynamoDB.put_item()        │
│  Table: clean_aqi_records   │
│  PK: record_id (String)     │
└──────────────────┬──────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  AUDIT LOG → CloudWatch                     │
│  {                                          │
│    total_input_records: N,                  │
│    inserted_records: N,                     │
│    rejected_records: N,                     │
│    timestamp: "2026-06-30T..."              │
│  }                                          │
└─────────────────────────────────────────────┘
```

---

## AQI Classification (Derived Field)

```
AQI Value       →   aqi_category
─────────────────────────────────────────────
0   – 50        →   Good
51  – 100       →   Moderate
101 – 150       →   Unhealthy_for_Sensitive_Groups
151 – 200       →   Unhealthy
201 – 300       →   Very_Unhealthy
301+            →   Hazardous
```

---

## CI/CD Pipeline

```
Developer pushes code to GitHub
          │
          ├──────────────────────────────────┐
          ▼                                  ▼
┌─────────────────────┐          ┌───────────────────────┐
│  GitHub Actions     │          │  AWS CodePipeline      │
│  .github/workflows/ │          │                        │
│  ci.yml             │          │  ┌──────────────────┐  │
│                     │          │  │ Source Stage     │  │
│  • Checkout repo    │          │  │ Pull from GitHub │  │
│  • Setup Python 3.11│          │  └────────┬─────────┘  │
│  • pip install deps │          │           │             │
│  • py_compile check │          │           ▼             │
│    lambda_function  │          │  ┌──────────────────┐  │
│    fetch_and_upload │          │  │ Build Stage      │  │
│                     │          │  │ CodeBuild runs   │  │
│  ✅ Syntax valid?   │          │  │ buildspec.yml    │  │
│  ❌ Fail on error   │          │  │ • pip install    │  │
└─────────────────────┘          │  │ • py_compile     │  │
                                 │  │ • Build artifact │  │
                                 │  └──────────────────┘  │
                                 └───────────────────────┘
```

---

## Dataset

**Source:** [World Air Quality Index Project (WAQI)](https://waqi.info/) — free public API providing live AQI readings for thousands of monitoring stations worldwide.

**Cities monitored:** Major Dhyan Chand National Stadium (Delhi), Mumbai US Consulate, T T Nagar (Bhopal), Hyderabad US Consulate, Chennai US Consulate, Maninagar (Ahmedabad), Marhatal (Jabalpur), City Center (Gwalior), and more.

---

## AWS Services Used

| Service | Role |
|---|---|
| **Amazon S3** | Raw data lake — stores `.json` and `.csv` files under `raw/` prefix |
| **AWS Lambda** | ETL engine — triggered on S3 PUT events, runs validate/transform/load |
| **Amazon DynamoDB** | Clean record store — on-demand capacity, one item per city per reading |
| **AWS IAM** | Least-privilege execution role for Lambda (`s3:GetObject`, `dynamodb:PutItem`) |
| **Amazon CloudWatch Logs** | Audit trail — `AUDIT_SUMMARY` log line per Lambda execution |
| **AWS CodePipeline** | CD — Source (GitHub) → Build (CodeBuild) on every push |
| **AWS CodeBuild** | Runs `buildspec.yml`: install deps + compile check |
| **GitHub Actions** | CI — pre-merge syntax validation on every push/PR |

---

## DynamoDB Table Design

**Table name:** `clean_aqi_records`  
**Partition key:** `record_id` (String)  
**Capacity mode:** On-demand

```
record_id (PK)              │ city          │ aqi │ aqi_category  │ dominant_pollutant │ reading_time         │ ingested_at
────────────────────────────┼───────────────┼─────┼───────────────┼────────────────────┼──────────────────────┼──────────────────────
delhi_2026-06-30T..._a1b2   │ Delhi         │ 194 │ Unhealthy     │ pm10               │ 2026-06-30T18:00:00  │ 2026-06-30T14:15:03
bhopal_2026-06-23T..._c3d4  │ T T Nagar,.. │  50 │ Good          │ pm25               │ 2026-06-23T10:00:00  │ 2026-06-30T14:15:03
```

`record_id` is built from `city + reading_time + uuid suffix` to guarantee uniqueness across runs and prevent overwriting historical records.

---

## ETL Validation Rules

| Field | Rule | Action on Failure |
|---|---|---|
| `city` | Must be present and non-empty | Reject record |
| `aqi` | Must be numeric and ≥ 0 | Reject record |
| `aqi` (dash `-`) | Non-numeric string | Reject record |
| Both valid | Proceed to transform | Insert to DynamoDB |

---

## Repository Structure

```
etl-s3-lambda-dynamodb/
├── README.md                     # This file
├── lambda_function.py            # ETL Lambda (extract, validate, transform, load, audit)
├── fetch_and_upload.py           # Local script: fetch WAQI API → upload raw JSON to S3
├── requirements.txt              # Python dependencies (boto3, requests)
├── buildspec.yml                 # AWS CodeBuild build spec
├── screenshots/                  # Evidence screenshots (S3, Lambda logs, DynamoDB)
└── .github/
    └── workflows/
        └── ci.yml                # GitHub Actions: syntax check on push/PR
```

---

## Setup & Testing Steps

### 1. Fetch and Upload Raw Data
```bash
python fetch_and_upload.py
```
Calls the WAQI API for each configured city, writes a timestamped JSON file, and uploads it to `s3://<bucket>/raw/`.

### 2. Verify S3 Trigger Fires
Check the S3 bucket event notification is configured:
- **Prefix:** `raw/`
- **Suffix:** `.csv` or `.json`
- **Event type:** `s3:ObjectCreated:Put`

### 3. Check CloudWatch Logs
After upload, Lambda fires automatically. Verify in CloudWatch:
```json
AUDIT_SUMMARY: {
  "total_input_records": 8,
  "inserted_records": 7,
  "rejected_records": 1,
  "timestamp": "2026-06-30T14:15:03Z"
}
```

### 4. Verify DynamoDB Records
Open DynamoDB → Tables → `clean_aqi_records` → **Explore table items**.  
Confirm records appear with `aqi_category` populated correctly.

### 5. Test CI/CD
Push any code change to GitHub:
- GitHub Actions runs syntax validation automatically
- AWS CodePipeline triggers Source → Build stages

---

## Reflection

**Why DynamoDB?**  
Fully managed and serverless — fits naturally with a Lambda-based pipeline. No servers to provision, scales automatically, and on-demand capacity means you only pay for the writes this project generates.

**Why this partition key?**  
`record_id = city + reading_time + uuid` spreads writes across many distinct keys (good for DynamoDB hot-partition avoidance) and preserves the full history of readings per city instead of overwriting previous values on each ETL run.

**What transformations does Lambda apply?**  
Rejects records with missing city or invalid AQI; normalizes city name to Title Case and AQI to integer; derives `aqi_category` from the EPA AQI scale; adds `ingested_at` timestamp.

**What files should never be committed to GitHub?**  
`.env` files and AWS credentials (leak risk), `*.zip` build artifacts (regenerable), `__pycache__/` (bytecode), and large raw `.csv` / `.json` datasets (regenerable from the API).
