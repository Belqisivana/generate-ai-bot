# list_models.py

import httpx
import config

headers = {
    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}"
}

r = httpx.get(
    "https://openrouter.ai/api/v1/models",
    headers=headers
)

print(r.status_code)
print(r.text[:5000])