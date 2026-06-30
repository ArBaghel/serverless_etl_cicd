import csv
import io
import json
import os
import boto3
import uuid
from datetime import datetime, timezone
 
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
 
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "clean_aqi_records")
table = dynamodb.Table(TABLE_NAME)
 
 
def classify_aqi(aqi: int) -> str:
    #Derived field: standard EPA-style AQI category.
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy_for_Sensitive_Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very_Unhealthy"
    else:
        return "Hazardous"
 
 
def is_valid(record: dict) -> bool:
    aqi = record.get("aqi")
    city = record.get("city")
    if city is None or str(city).strip() == "":
        return False
    try:
        aqi_val = int(aqi)
        if aqi_val < 0:
            return False
    except (ValueError, TypeError):
        return False
    return True
 
 
 
def transform(record: dict) -> dict:
    #Standardize at least two fields + add one derived field.
    city_clean = str(record["city"]).strip().title()          # standardized field 1
    aqi_clean = int(record["aqi"])                             # standardized field 2 (type-safe int)
    pollutant = str(record.get("dominant_pollutant", "unknown")).lower()
    timestamp = record.get("time") or datetime.now(timezone.utc).isoformat()
 
    record_id = f"{city_clean.lower().replace(' ', '_')}_{timestamp}_{uuid.uuid4().hex[:8]}"
 
    return {
        "record_id": record_id,                # partition key
        "city": city_clean,
        "aqi": aqi_clean,
        "dominant_pollutant": pollutant,
        "aqi_category": classify_aqi(aqi_clean),   # derived field
        "reading_time": timestamp,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
 
 
def parse_csv(raw_bytes: bytes) -> list:
    """Minimal CSV -> list[dict] parser, same field names as the JSON records."""
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]
 
 
def lambda_handler(event, context):
    total = 0
    inserted = 0
    rejected = 0
 
    for s3_event in event.get("Records", []):
        bucket = s3_event["s3"]["bucket"]["name"]
        key = s3_event["s3"]["object"]["key"]
 
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw_bytes = obj["Body"].read()
 
        if key.lower().endswith(".csv"):
            raw_data = parse_csv(raw_bytes)
        else:
            raw_data = json.loads(raw_bytes)
 
        # raw_data is expected to be a list of dicts (see fetch_and_upload.py)
        if isinstance(raw_data, dict):
            raw_data = [raw_data]
 
        for raw_record in raw_data:
            total += 1
            if not is_valid(raw_record):
                rejected += 1
                continue
            try:
                clean_record = transform(raw_record)
                table.put_item(Item=clean_record)
                inserted += 1
            except Exception as e:
                print(f"Failed to insert record: {raw_record} -> {e}")
                rejected += 1
 
    audit_summary = {
        "total_input_records": total,
        "inserted_records": inserted,
        "rejected_records": rejected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
 
    # AUDIT log -> visible in CloudWatch Logs
    print(f"AUDIT_SUMMARY: {json.dumps(audit_summary)}")
 
    return {
        "statusCode": 200,
        "body": json.dumps(audit_summary),
    }