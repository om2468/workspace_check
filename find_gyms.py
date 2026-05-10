import csv
import json
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_ID = "gemini-flash-lite-latest"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"

def call_gemini(prompt, retries=3):
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }
    
    for attempt in range(retries):
        try:
            response = requests.post(URL, headers=headers, json=data)
            if response.status_code == 200:
                result = response.json()
                # Extract text from response
                text_content = result['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text_content)
            elif response.status_code == 429:
                print(f"Rate limited. Waiting and retrying... (Attempt {attempt + 1})")
                time.sleep(10 * (attempt + 1))
            else:
                print(f"Error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Exception during API call: {e}")
        
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
            address = office['Postcode']
            coords = f"{office['Latitude']}, {office['Longitude']}"
            
            print(f"Processing ({i+1}/{len(offices)}): {name}")
            
            # Query and write for PureGym
            puregym_prompt = (
                f"Find up to the 3 closest PureGym locations to '{name}' at {address} ({coords}) "
                f"that are within a 10-minute walk. Return ONLY a JSON list of objects: "
                f"[{{\"office_name\": \"{name}\", \"office_address\": \"{address}\", \"gym_name\": \"string\", "
                f"\"gym_address\": \"string\", \"distance_metres\": integer, \"walk_time_mins\": integer}}]"
            )
            puregym_results = call_gemini(puregym_prompt)
            if puregym_results and isinstance(puregym_results, list):
                for res in puregym_results:
                    p_writer.writerow(res)
                pf.flush()
            time.sleep(3)
            
            # Query and write for The Gym Group
            gymgroup_prompt = (
                f"Find up to the 3 closest 'The Gym Group' locations to '{name}' at {address} ({coords}) "
                f"that are within a 10-minute walk. Return ONLY a JSON list of objects: "
                f"[{{\"office_name\": \"{name}\", \"office_address\": \"{address}\", \"gym_name\": \"string\", "
                f"\"gym_address\": \"string\", \"distance_metres\": integer, \"walk_time_mins\": integer}}]"
            )
            gymgroup_results = call_gemini(gymgroup_prompt)
            if gymgroup_results and isinstance(gymgroup_results, list):
                for res in gymgroup_results:
                    g_writer.writerow(res)
                gf.flush()
            time.sleep(3)

if __name__ == "__main__":
    process_gyms()
