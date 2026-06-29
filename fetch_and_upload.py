

import json
import time
import requests
import boto3

# ---- CONFIG ---------------------------------------------------------
WAQI_TOKEN = "9e61f6da4928e57947fbe8e2652b25e93fe36d9c"  # your token
CITIES = ["delhi", "mumbai", "bhopal", "rewa", "jabalpur"]
S3_BUCKET = "REPLACE_WITH_YOUR_BUCKET_NAME"
S3_RAW_KEY_PREFIX = "raw/"
# ----------------------------------------------------------------------


def fetch_city_aqi(city: str) -> dict:
    """Calls the WAQI feed API for a single city and returns raw JSON."""
    url = f"https://api.waqi.info/feed/{city}/?token={WAQI_TOKEN}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main():
    records = []
    for city in CITIES:
        try:
            payload = fetch_city_aqi(city)
            if payload.get("status") == "ok":
                d = payload["data"]
                records.append({
                    "city": d.get("city", {}).get("name", city),
                    "aqi": d.get("aqi"),
                    "dominant_pollutant": d.get("dominentpol"),
                    "time": d.get("time", {}).get("iso"),
                    "station_idx": d.get("idx"),
                })
            else:
                print(f"WAQI returned non-ok status for {city}: {payload}")
        except Exception as e:
            print(f"Failed to fetch {city}: {e}")
        time.sleep(1)  # be polite to the free API tier

    filename = f"aqi_raw_{int(time.time())}.json"
    with open(filename, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Saved {len(records)} records locally to {filename}")

    # Upload to S3 raw/ prefix
    s3 = boto3.client("s3")
    s3_key = S3_RAW_KEY_PREFIX + filename
    s3.upload_file(filename, S3_BUCKET, s3_key)
    print(f"Uploaded to s3://{S3_BUCKET}/{s3_key}")


if __name__ == "__main__":
    main()
