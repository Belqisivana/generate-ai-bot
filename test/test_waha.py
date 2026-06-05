# test_waha.py

import requests

r = requests.get(
    "http://127.0.0.1:3001/api/sessions",
    headers={
        "X-Api-Key": "1234567890"
    }
)

print(r.status_code)
print(r.text)