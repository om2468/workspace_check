import csv
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


OFFICES_PATH = Path("workspace_office_locations.csv")
REPORT_PATH = Path("workspace_office_validation_report.csv")
API_URL = "https://api.opencagedata.com/geocode/v1/json"


def normalize_postcode(value: str) -> str:
    return "".join((value or "").upper().split())


def reverse_geocode(api_key: str, latitude: str, longitude: str):
    response = requests.get(
        API_URL,
        params={
            "q": f"{latitude},{longitude}",
            "key": api_key,
            "limit": 1,
            "no_annotations": 1,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("results"):
        return {}
    result = payload["results"][0]
    components = result.get("components", {})
    return {
        "formatted": result.get("formatted", ""),
        "postcode": components.get("postcode", ""),
        "road": components.get("road", ""),
        "house_number": components.get("house_number", ""),
        "confidence": result.get("confidence", ""),
    }


def main():
    load_dotenv(".env")
    api_key = os.getenv("OPENCAGE_API_KEY")
    if not api_key or api_key == "your_opencage_key_here":
        raise SystemExit("Missing OPENCAGE_API_KEY in .env")

    with OFFICES_PATH.open(mode="r", encoding="utf-8-sig") as file_handle:
        office_rows = list(csv.DictReader(file_handle))

    output_rows = []
    mismatches = 0

    for office in office_rows:
        reverse = reverse_geocode(api_key, office["Latitude"], office["Longitude"])
        expected_postcode = office["Postcode"]
        reverse_postcode = reverse.get("postcode", "")
        postcode_match = normalize_postcode(expected_postcode) == normalize_postcode(reverse_postcode)
        if not postcode_match:
            mismatches += 1

        output_rows.append(
            {
                "office_name": office["Name"],
                "latitude": office["Latitude"],
                "longitude": office["Longitude"],
                "expected_postcode": expected_postcode,
                "reverse_postcode": reverse_postcode,
                "postcode_match": "yes" if postcode_match else "no",
                "reverse_formatted": reverse.get("formatted", ""),
                "reverse_road": reverse.get("road", ""),
                "reverse_house_number": reverse.get("house_number", ""),
                "confidence": reverse.get("confidence", ""),
            }
        )
        print(f"Checked {office['Name']}: {'OK' if postcode_match else 'MISMATCH'}")
        time.sleep(1.1)

    fieldnames = list(output_rows[0].keys()) if output_rows else []
    with REPORT_PATH.open(mode="w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Checked {len(output_rows)} offices")
    print(f"Postcode mismatches: {mismatches}")
    print(f"Office validation report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()