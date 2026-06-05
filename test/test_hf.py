import httpx

r = httpx.get("https://api-inference.huggingface.co")
print(r.status_code)
print(r.text)