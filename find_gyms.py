import csv
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-3.1-flash-lite")
CLIENT = genai.Client(api_key=API_KEY) if API_KEY else None
GYM_RESULT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "office_name": {"type": "string"},
            "office_address": {"type": "string"},
            "gym_name": {"type": "string"},
            "gym_address": {"type": "string"},
            "distance_metres": {"type": "integer"},
            "walk_time_mins": {"type": "integer"},
        },
        "required": [
            "office_name",
            "office_address",
            "gym_name",
            "gym_address",
            "distance_metres",
            "walk_time_mins",
        ],
    },
}


def build_gym_prompt(brand, office_name, office_postcode, coords):
    return (
        f"Use Google Maps grounding to find up to 3 {brand} locations within a 10-minute walk of "
        f"Workspace office '{office_name}' near postcode {office_postcode} at coordinates {coords}. "
        f"Only return real locations you can ground from Google Maps results. Do not invent, estimate, or "
        f"merge locations. If fewer than 3 grounded gyms are found, return fewer items. If none are found, "
        f"return an empty JSON array. Return ONLY JSON using this schema: "
        f"[{{\"office_name\": \"{office_name}\", \"office_address\": \"{office_postcode}\", "
        f"\"gym_name\": \"string\", \"gym_address\": \"string\", \"distance_metres\": integer, "
        f"\"walk_time_mins\": integer}}]"
    )

def call_gemini(prompt, retries=3):
    if not CLIENT:
        print("Missing GEMINI_API_KEY in environment.")
        return None

    for attempt in range(retries):
        try:
            response = CLIENT.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_maps=types.GoogleMaps())],
                    response_mime_type="application/json",
                    response_schema=GYM_RESULT_SCHEMA,
                    thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
                ),
            )
            if not response.text:
                return []
            return json.loads(response.text)
        except Exception as e:
            print(f"Exception during API call: {e}")
            if attempt < retries - 1:
                print(f"Retrying... (Attempt {attempt + 1})")
                time.sleep(10 * (attempt + 1))

    return None

def process_gyms():
    input_file = "workspace_office_locations.csv"
    puregym_output = "puregym_locations.csv"
    gymgroup_output = "gymgroup_locations.csv"
    
    # Use 'utf-8-sig' to handle Byte Order Mark (BOM) if present
    with open(input_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        offices = list(reader)
    
    # Define CSV fields
    fieldnames = ["office_name", "office_address", "gym_name", "gym_address", "distance_metres", "walk_time_mins"]

    # Open both files and write headers if they don't exist
    with open(puregym_output, 'w', newline='', encoding='utf-8') as pf, \
         open(gymgroup_output, 'w', newline='', encoding='utf-8') as gf:
        
        p_writer = csv.DictWriter(pf, fieldnames=fieldnames)
        g_writer = csv.DictWriter(gf, fieldnames=fieldnames)
        
        p_writer.writeheader()
        g_writer.writeheader()
    
        for i, office in enumerate(offices):
            name = office['Name']
            address = office.get('Address') or office['Postcode']
            postcode = office['Postcode']
            coords = f"{office['Latitude']}, {office['Longitude']}"
            
            print(f"Processing ({i+1}/{len(offices)}): {name}")
            
            # Query and write for PureGym
            puregym_prompt = build_gym_prompt("PureGym", name, f"{address} ({postcode})", coords)
            puregym_results = call_gemini(puregym_prompt)
            if puregym_results and isinstance(puregym_results, list):
                for res in puregym_results:
                    p_writer.writerow(res)
                pf.flush()
            time.sleep(3)
            
            # Query and write for The Gym Group
            gymgroup_prompt = build_gym_prompt("The Gym Group", name, f"{address} ({postcode})", coords)
            gymgroup_results = call_gemini(gymgroup_prompt)
            if gymgroup_results and isinstance(gymgroup_results, list):
                for res in gymgroup_results:
                    g_writer.writerow(res)
                gf.flush()
            time.sleep(3)

if __name__ == "__main__":
    process_gyms()
