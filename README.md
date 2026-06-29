# Serverless ETL: Air Quality Index (AQI) Pipeline

## 1. Project Title
**Real-Time Air Quality ETL Pipeline (S3 → Lambda → DynamoDB)**

## 2. Dataset Source
[World Air Quality Index Project (WAQI) API](https://aqicn.org/api/) — a free, real-world public API
that provides live AQI readings for thousands of monitoring stations worldwide.

## 3. Scenario
Air quality readings for a set of cities are fetched from the WAQI API, dropped into S3 as raw JSON,
and automatically cleaned and loaded into DynamoDB so that the **latest validated AQI reading per
city** is always queryable — the classic "weather / air quality: clean readings and store latest
metrics" scenario from the assignment brief.

## 4. Architecture Diagram

```
WAQI API (third-party data source)
        |
        v
fetch_and_upload.py  (local script)
        |
        v
Amazon S3  (raw/ prefix)  --- S3:ObjectCreated event --->  AWS Lambda (lambda_function.py)
                                                                  |
                                                                  v
                                                       Amazon DynamoDB (clean_records table)
                                                                  |
                                                                  v
                                                       CloudWatch Logs (audit summary)
```

GitHub Actions validates code on every push. AWS CodePipeline pulls from GitHub and runs the same
validation via CodeBuild, simulating a real CI/CD release process.

## 5. AWS Services Used
- **Amazon S3** – stores raw AQI JSON files under `raw/`
- **AWS Lambda** – runs the ETL (extract, transform, load, audit)
- **Amazon DynamoDB** – stores clean records (`clean_records` table)
- **AWS IAM** – least-privilege execution role for Lambda
- **Amazon CloudWatch Logs** – Lambda execution logs + audit summary
- **AWS CodePipeline + AWS CodeBuild** – CI/CD pipeline triggered from GitHub
- **GitHub Actions** – pre-merge syntax/dependency validation

## 6. ETL Rules
| Stage | Rule |
|---|---|
| Extract | Read the raw JSON array uploaded to `s3://<bucket>/raw/*.json` |
| Transform | Reject records with empty `city` or non-numeric/negative `aqi`. Standardize `city` to Title Case and `aqi` to integer. Add derived field `aqi_category` (Good / Moderate / Unhealthy_for_Sensitive_Groups / Unhealthy / Very_Unhealthy / Hazardous) |
| Load | `put_item` into DynamoDB with partition key `record_id` = `<city>_<reading_time>` |
| Audit | Log `total_input_records`, `inserted_records`, `rejected_records`, `timestamp` to CloudWatch |

## 7. DynamoDB Table Design
- **Table name:** `clean_records`
- **Partition key:** `record_id` (String) — composite of city + reading timestamp, guarantees
  uniqueness per city per reading and avoids overwriting historical data with each run.
- **Capacity mode:** On-demand (no need to pre-provision throughput for a small/variable workload)
- **Other attributes:** `city`, `aqi`, `dominant_pollutant`, `aqi_category`, `reading_time`, `ingested_at`

## 8. Testing Steps
1. Run `python fetch_and_upload.py` locally — it calls the live WAQI API for each city in
   `CITIES`, builds a raw JSON file, and uploads it to `s3://<bucket>/raw/`.
2. Confirm the S3 PUT event triggers the Lambda function (check CloudWatch Logs).
3. Confirm the `AUDIT_SUMMARY` log line shows the expected total/inserted/rejected counts
   (a city lookup that fails or returns a non-`"ok"` status from WAQI is skipped by the
   fetch script itself; any record that does reach S3 with an invalid/missing AQI or city is
   rejected by Lambda's validation step — so the audit numbers reflect real, live-API conditions).
4. Open the DynamoDB table and confirm clean items appear with correct `aqi_category` values.
5. Push a code change to GitHub and confirm the GitHub Actions workflow passes.
6. Confirm AWS CodePipeline runs Source → Build successfully after the same push.

## 9. GitHub Actions Summary
`.github/workflows/ci.yml` runs on every push/PR: checks out the repo, sets up Python 3.11,
installs dependencies, and runs `python -m py_compile` against `lambda_function.py` and
`fetch_and_upload.py` to catch syntax errors before merge.

## 10. AWS CodePipeline Summary
The pipeline has two stages:
1. **Source** – pulls the latest commit from the GitHub repository (via GitHub App connection).
2. **Build** – AWS CodeBuild runs `buildspec.yml`, which installs dependencies and compiles
   `lambda_function.py`, producing a build artifact containing the Lambda code.

## 11. Reflection Questions

**Why did you choose DynamoDB for this project?**
DynamoDB is a fully managed, serverless NoSQL database that fits naturally with a serverless
Lambda pipeline — no servers to provision, scales automatically, and on-demand capacity mode
means I only pay for the small number of writes this project generates.

**What is your partition key and why?**
`record_id`, built from `city + reading_time`. This spreads writes across many distinct keys
(good for DynamoDB performance) and keeps a full history of readings per city instead of
overwriting the previous value every time the ETL runs.

**What transformation rules did Lambda apply?**
Rejects records with a missing city or a negative/non-numeric AQI; standardizes city name
casing and AQI to integer type; derives a new `aqi_category` field from the AQI value.

**What did GitHub Actions validate?**
That the Python files install their dependencies cleanly and compile without syntax errors,
on every push/PR — a fast first line of defense before the heavier CodePipeline/CodeBuild stage.

**What did AWS CodePipeline do?**
Automatically pulled the latest code from GitHub (Source stage) and ran the same dependency
install + compile check via CodeBuild (Build stage), producing a deployable artifact.

**Which files should never be committed to GitHub and why?**
`.env` files and any AWS access/secret keys (credential leakage risk), `*.zip` build artifacts
(bloat, regenerable), `__pycache__/` (bytecode, regenerable), and raw `*.csv`/large raw datasets
(can be large, often not meant for public sharing, and are regenerable from the source API).

## 12. Repository Structure
```
etl-s3-lambda-dynamodb/
├── README.md
├── lambda_function.py
├── fetch_and_upload.py
├── requirements.txt
├── buildspec.yml
├── screenshots/
└── .github/workflows/ci.yml
```
