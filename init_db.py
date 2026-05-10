import duckdb
import os

def setup_database():
    db_path = "gym_locator.db"
    
    # Connect to DuckDB
    con = duckdb.connect(db_path)
    
    print("Initializing DuckDB tables...")
    
    # 1. Create Offices Table
    con.execute("""
        CREATE OR REPLACE TABLE offices AS 
        SELECT 
            Name as office_name,
            Latitude as lat,
            Longitude as lon,
            Postcode as postcode
        FROM read_csv_auto('workspace_office_locations.csv');
    """)
    
    # 2. Import Geocoded Gyms (if files exist)
    for gym_type, file in [('puregym', 'puregym_locations_geocoded.csv'), 
                           ('gymgroup', 'gymgroup_locations_geocoded.csv')]:
        if os.path.exists(file):
            table_name = f"{gym_type}_gyms"
            con.execute(f"DROP TABLE IF EXISTS {table_name}")
            con.execute(f"""
                CREATE TABLE {table_name} AS 
                SELECT 
                    office_name as Office,
                    gym_name as Name,
                    gym_address as Address,
                    walk_time_mins as Duration,
                    distance_metres as Distance,
                    gym_latitude as lat,
                    gym_longitude as lon
                FROM read_csv_auto('{file}');
            """)
            print(f"Imported {file} into {table_name}")
        else:
            print(f"Skipping {file} as it doesn't exist yet. Run find_gyms.py and geocode_gyms.py first.")

    con.close()
    print("Database setup complete.")

if __name__ == "__main__":
    setup_database()
