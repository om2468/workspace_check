import argparse
import csv
import json
import math
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from workspace_office_filters import is_workspace_office_name


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-3.1-flash-lite")
CLIENT = genai.Client(api_key=API_KEY) if API_KEY else None
INPUT_PATH = Path("workspace_office_locations.csv")
OUTPUT_PATH = Path("workspace_office_reviews.csv")
OUTPUT_FIELDS = [
    "Name",
    "GroundedName",
    "Address",
    "Postcode",
    "Latitude",
    "Longitude",
    "AreaOfLondon",
    "GoogleMapsRating",
    "GoogleMapsReviewCount",
    "PlaceStatus",
    "ReviewSummary",
    "KeyComments",
    "PositiveThemes",
    "NegativeThemes",
    "PositiveCommentExamples",
    "NegativeCommentExamples",
    "ReviewNotes",
]


def parse_json_text(response_text):
    if not response_text:
        return None

    cleaned_text = response_text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned_text, re.DOTALL)
    if fenced_match:
        cleaned_text = fenced_match.group(1).strip()

    for pattern in (r"(\{.*\})", r"(\[.*\])"):
        match = re.search(pattern, cleaned_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

    return json.loads(cleaned_text)


def normalize_string_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def to_float(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return round(number, 2)


def to_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def infer_area_of_london(postcode, latitude, longitude):
    postcode = (postcode or "").strip().upper()
    district = postcode.split()[0]
    prefix_match = re.match(r"[A-Z]+", district)
    prefix = prefix_match.group(0) if prefix_match else ""

    central_prefixes = {"EC", "WC", "W1", "SW1", "SE1", "N1"}
    west_prefixes = {"W", "W2", "W3", "W4", "W5", "W6", "W8", "W9", "W10", "W11", "W12", "W14"}
    east_prefixes = {"E", "E1", "E2", "E3", "E8", "E14", "E15", "SE8"}
    south_prefixes = {"SE", "SE1", "SE5", "SE8", "SE11", "SE15", "SE21", "SW", "SW4", "SW8", "SW9", "SW18"}
    north_prefixes = {"N", "N1", "N4", "N5", "N7", "N16", "NW", "NW1", "NW5", "NW6", "NW8", "NW10"}

    if district in central_prefixes or prefix in {"EC", "WC"}:
        return "Central"
    if district in east_prefixes or prefix == "E":
        return "East"
    if district in west_prefixes or prefix == "W":
        return "West"
    if district in south_prefixes or prefix == "SE" or prefix == "SW":
        return "South"
    if district in north_prefixes or prefix == "N" or prefix == "NW":
        return "North"

    lat = to_float(latitude)
    lon = to_float(longitude)
    if lat is None or lon is None:
        return "Other"
    if lat >= 51.515 and -0.18 <= lon <= -0.02:
        return "Central"
    if lon > -0.02:
        return "East"
    if lon < -0.18:
        return "West"
    if lat < 51.49:
        return "South"
    if lat > 51.53:
        return "North"
    return "Central"


def build_review_prompt(office):
    office_name = office["Name"]
    grounded_name = office.get("GroundedName") or office_name
    address = office.get("Address") or office.get("Postcode", "")
    postcode = office.get("Postcode", "")
    latitude = office.get("Latitude", "")
    longitude = office.get("Longitude", "")
    return (
        f"Use Google Maps grounding to inspect the Workspace office '{office_name}' in London. "
        f"Prefer the grounded place '{grounded_name}' at {address}, {postcode} near coordinates {latitude}, {longitude}. "
        f"Return grounded Google Maps review information for the office itself, not the surrounding area. "
        f"If reviews are sparse, summarize only what is clearly supported by Google Maps review content and metadata. "
        f"Do not invent quotes, counts, themes, or sentiment. Keep comments paraphrased, concise, and factual. "
        f"Return JSON with exactly these fields: "
        f"{{"
        f"\"Name\": \"{office_name}\", "
        f"\"GroundedName\": \"{grounded_name}\", "
        f"\"Address\": \"{address}\", "
        f"\"Postcode\": \"{postcode}\", "
        f"\"Latitude\": {latitude}, "
        f"\"Longitude\": {longitude}, "
        f"\"GoogleMapsRating\": number or null, "
        f"\"GoogleMapsReviewCount\": integer or null, "
        f"\"PlaceStatus\": \"Open|Temporarily closed|Permanently closed|Unknown\", "
        f"\"ReviewSummary\": \"2-3 sentence summary\", "
        f"\"KeyComments\": [\"string\"], "
        f"\"PositiveThemes\": [\"string\"], "
        f"\"NegativeThemes\": [\"string\"], "
        f"\"PositiveCommentExamples\": [\"string\"], "
        f"\"NegativeCommentExamples\": [\"string\"], "
        f"\"ReviewNotes\": \"short note about confidence, lack of reviews, or ambiguity\""
        f"}}"
    )


def fetch_review_record(prompt, retries=3):
    if not CLIENT:
        raise RuntimeError("Missing GEMINI_API_KEY in environment")

    for attempt in range(retries):
        try:
            response = CLIENT.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_maps=types.GoogleMaps())],
                    thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
                ),
            )
            if not response.text:
                return None
            return parse_json_text(response.text)
        except Exception as exc:
            print(f"Exception during API call: {exc}")
            if attempt < retries - 1:
                time.sleep(10 * (attempt + 1))

    return None


def load_offices(input_path):
    with input_path.open(mode="r", encoding="utf-8-sig") as file_handle:
        offices = list(csv.DictReader(file_handle))
    return [office for office in offices if is_workspace_office_name(office.get("Name"))]


def clean_record(office, record):
    cleaned = {
        "Name": office["Name"],
        "GroundedName": office.get("GroundedName") or office["Name"],
        "Address": office.get("Address", ""),
        "Postcode": office.get("Postcode", ""),
        "Latitude": office.get("Latitude", ""),
        "Longitude": office.get("Longitude", ""),
        "AreaOfLondon": infer_area_of_london(
            office.get("Postcode", ""), office.get("Latitude", ""), office.get("Longitude", "")
        ),
        "GoogleMapsRating": None,
        "GoogleMapsReviewCount": None,
        "PlaceStatus": "Unknown",
        "ReviewSummary": "",
        "KeyComments": "[]",
        "PositiveThemes": "[]",
        "NegativeThemes": "[]",
        "PositiveCommentExamples": "[]",
        "NegativeCommentExamples": "[]",
        "ReviewNotes": "No grounded review result returned",
    }
    if not record:
        return cleaned

    cleaned.update(
        {
            "GroundedName": record.get("GroundedName") or cleaned["GroundedName"],
            "Address": record.get("Address") or cleaned["Address"],
            "Postcode": record.get("Postcode") or cleaned["Postcode"],
            "Latitude": record.get("Latitude") or cleaned["Latitude"],
            "Longitude": record.get("Longitude") or cleaned["Longitude"],
            "GoogleMapsRating": to_float(record.get("GoogleMapsRating")),
            "GoogleMapsReviewCount": to_int(record.get("GoogleMapsReviewCount")),
            "PlaceStatus": record.get("PlaceStatus") or "Unknown",
            "ReviewSummary": str(record.get("ReviewSummary") or "").strip(),
            "KeyComments": json.dumps(normalize_string_list(record.get("KeyComments")), ensure_ascii=True),
            "PositiveThemes": json.dumps(normalize_string_list(record.get("PositiveThemes")), ensure_ascii=True),
            "NegativeThemes": json.dumps(normalize_string_list(record.get("NegativeThemes")), ensure_ascii=True),
            "PositiveCommentExamples": json.dumps(
                normalize_string_list(record.get("PositiveCommentExamples")), ensure_ascii=True
            ),
            "NegativeCommentExamples": json.dumps(
                normalize_string_list(record.get("NegativeCommentExamples")), ensure_ascii=True
            ),
            "ReviewNotes": str(record.get("ReviewNotes") or "").strip(),
        }
    )
    cleaned["AreaOfLondon"] = infer_area_of_london(
        cleaned.get("Postcode", ""), cleaned.get("Latitude", ""), cleaned.get("Longitude", "")
    )
    return cleaned


def write_reviews(offices, output_path, delay_seconds):
    with output_path.open(mode="w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for index, office in enumerate(offices, start=1):
            print(f"Processing ({index}/{len(offices)}): {office['Name']}")
            record = fetch_review_record(build_review_prompt(office))
            writer.writerow(clean_record(office, record))
            file_handle.flush()
            time.sleep(delay_seconds)


def build_parser():
    parser = argparse.ArgumentParser(description="Enrich Workspace offices with Google Maps review summaries.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH, help="Office CSV to read")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Review CSV to write")
    parser.add_argument("--office", help="Only process a single office name")
    parser.add_argument("--limit", type=int, help="Only process the first N offices after filtering")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between API requests in seconds")
    return parser


def main():
    args = build_parser().parse_args()
    offices = load_offices(args.input)

    if args.office:
        offices = [office for office in offices if office["Name"] == args.office]

    if args.limit is not None:
        offices = offices[: args.limit]

    if not offices:
        raise SystemExit("No offices matched the requested filters")

    write_reviews(offices, args.output, args.delay)
    print(f"Wrote review dataset to {args.output}")


if __name__ == "__main__":
    main()