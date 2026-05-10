import csv
import os
import time
import requests
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENCAGE_API_KEY")

def call_opencage_rest(query):
    # Construct the REST URL as per documentation
    # https://api.opencagedata.com/geocode/v1/json?q=QUERY&key=YOUR-API-KEY
    encoded_query = quote(query)
    url = f"https://api.opencagedata.com/geocode/v1/json?q={encoded_query}&key={API_KEY}&limit=1&no_annotations=1"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['results']:
                geometry = data['results'][0]['geometry']
                return geometry['lat'], geometry['lng']
            else:
                print(f"    Warning: No results found for {query}")
        elif response.status_code == 429:
            print("    Rate limited (429). Waiting longer...")
            time.sleep(5)
        else:
            print(f"    Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"    Exception during REST call: {e}")
    
    return None, None

def geocode_csv(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"File {input_file} not found. Skipping.")
        return

    print(f"Geocoding {input_file} -> {output_file} using REST API...")
    
    # Overwrite the output file by opening it in 'w' mode
    with open(input_file, mode='r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames + ['gym_latitude', 'gym_longitude']
        
        with open(output_file, mode='w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in reader:
                address = row['gym_address']
                print(f"  Geocoding: {address}")
                
                # Use the REST function instead of SDK
                lat, lng = call_opencage_rest(f"{address}, UK")
                
                row['gym_latitude'] = lat if lat is not None else ""
                row['gym_longitude'] = lng if lng is not None else ""
                
                writer.writerow(row)
                outfile.flush()
                # Respect rate limits (Free trial is 1 request per second)
                time.sleep(1.1)

def main():
    if not API_KEY or API_KEY == "your_opencage_key_here":
        print("Please set your OPENCAGE_API_KEY in the .env file.")
        return

    geocode_csv('puregym_locations.csv', 'puregym_locations_geocoded.csv')
    geocode_csv('gymgroup_locations.csv', 'gymgroup_locations_geocoded.csv')

if __name__ == "__main__":
    main()
