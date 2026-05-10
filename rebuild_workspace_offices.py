import csv
import json
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
OUTPUT_PATH = Path("workspace_office_locations_regenerated.csv")
OFFICE_SCHEMA = {
    "type": "object",
    "properties": {
        "Name": {"type": "string"},
        "Address": {"type": "string"},
        "Latitude": {"type": "number"},
        "Longitude": {"type": "number"},
        "Postcode": {"type": "string"},
        "GroundedName": {"type": "string"},
        "GroundingNotes": {"type": "string"},
    },
    "required": [
        "Name",
        "Address",
        "Latitude",
        "Longitude",
        "Postcode",
        "GroundedName",
        "GroundingNotes",
    ],
}


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


def build_office_prompt(office_name, postcode, latitude, longitude):
    return (
        f"Use Google Maps grounding to identify the actual Workspace Group office named '{office_name}' in London. "
        f"The seed dataset currently says postcode {postcode} and coordinates {latitude}, {longitude}. "
        f"Match the Workspace office itself, not just a nearby road, postcode centroid, or unrelated building. "
        f"If you cannot find a clearly grounded Workspace office, return the best grounded building that corresponds "
        f"to that office name and explain the ambiguity in GroundingNotes. "
        f"Return the canonical street address, postcode, latitude, and longitude from the grounded Google Maps result. "
        f"Set GroundedName to the exact place or building name you grounded against in Google Maps. "
        f"Set GroundingNotes to a short explanation of why this match was chosen, including any mismatch from the seed postcode or coordinates. "
        f"Only return a result if it is grounded in Google Maps. Do not infer from the seed CSV alone. "
        f"Return JSON with exactly these fields: "
        f"{{\"Name\": \"{office_name}\", \"Address\": \"string\", \"Latitude\": number, \"Longitude\": number, \"Postcode\": \"string\", \"GroundedName\": \"string\", \"GroundingNotes\": \"string\"}}"
    )


def fetch_office_record(prompt, retries=3):
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


def load_seed_offices():
    with INPUT_PATH.open(mode="r", encoding="utf-8-sig") as file_handle:
        return list(csv.DictReader(file_handle))


def main():
    offices = load_seed_offices()
    fieldnames = [
        "Name",
        "Address",
        "Latitude",
        "Longitude",
        "Postcode",
        "GroundedName",
        "GroundingNotes",
        "SeedLatitude",
        "SeedLongitude",
        "SeedPostcode",
    ]

    with OUTPUT_PATH.open(mode="w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()

        for index, office in enumerate(offices, start=1):
            if not is_workspace_office_name(office["Name"]):
                continue
            print(f"Processing ({index}/{len(offices)}): {office['Name']}")
            record = fetch_office_record(
                build_office_prompt(
                    office_name=office["Name"],
                    postcode=office["Postcode"],
                    latitude=office["Latitude"],
                    longitude=office["Longitude"],
                )
            )
            if record:
                record["SeedLatitude"] = office["Latitude"]
                record["SeedLongitude"] = office["Longitude"]
                record["SeedPostcode"] = office["Postcode"]
                writer.writerow(record)
            file_handle.flush()
            time.sleep(3)

    print(f"Wrote regenerated office CSV to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()