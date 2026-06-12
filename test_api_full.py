# test_api_full.py
import requests
import json

url = 'http://localhost:8000/api/predict/'

data = {
    "engine_id": "TEST_API_001",
    "cycle": 1,
    "altitude": 10000, "mach": 0.6, "regime": 100,
    "s2": 518.67, "s3": 642.0, "s4": 1589.0,
    "s7": 554.0, "s8": 2388.0, "s9": 9046.0,
    "s11": 47.0, "s12": 521.0, "s13": 2388.0,
    "s14": 8138.0, "s15": 8.4, "s17": 392.0,
    "s20": 39.0, "s21": 23.0
}

try:
    response = requests.post(url, json=data, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Erreur {response.status_code}: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ Impossible de se connecter au serveur. Lancez : python manage.py runserver")
except Exception as e:
    print(f"❌ Erreur: {e}")