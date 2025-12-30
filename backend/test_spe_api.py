
import requests
import json

TOKEN = "51566c9fde37672ca10b8ffb7670fd8783cbbac9"
URL = "http://127.0.0.1:8000/api/v3/spot/envelopes/"

payload = {
    "shipment_context": {
        "origin_country": "AU",
        "destination_country": "PG",
        "origin_code": "",
        "destination_code": "POM",
        "commodity": "GCR",
        "total_weight_kg": 100.0,
        "pieces": 5
    },
    "charges": [],
    "trigger_code": "TEST_TRIGGER",
    "trigger_text": "Test trigger reason",
    "conditions": {
        "rate_validity_hours": 72
    }
}

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}

response = requests.post(URL, json=payload, headers=headers)

print(f"Status Code: {response.status_code}")
try:
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except:
    print("Response Text:")
    print(response.text)
