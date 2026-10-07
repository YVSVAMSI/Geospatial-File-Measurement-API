import sys
sys.path.append('.')
from main import process_file_task, files_db
import json

file_id = "test_natural_earth"
file_path = "ne_110m_admin_0_countries.zip"

import urllib.request
import os

if not os.path.exists(file_path):
    print("Downloading shapefile...")
    urllib.request.urlretrieve("http://www.naturalearthdata.com/http//www.naturalearthdata.com/download/110m/cultural/ne_110m_admin_0_countries.zip", file_path)

print("Starting processing")
files_db[file_id] = {}
process_file_task(file_id, file_path, file_path, ".zip")

if files_db[file_id].get('status') == 'FAILED':
    print("FAILED:", files_db[file_id].get('error'))
else:
    print("SUCCESS")
    features = files_db[file_id]['features']
    print(f"Number of features: {len(features)}")
    
    # Try serializing to json to test if FastAPI would crash
    try:
        json_data = json.dumps(features)
        print("JSON Serialization SUCCESS")
    except Exception as e:
        print("JSON Serialization FAILED:", e)
