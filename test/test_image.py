from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

response = client.chat.completions.create(
    model="google/gemini-3.1-flash-image-preview",
    messages=[
        {
            "role": "user",
            "content": "A cute astronaut cat on the moon"
        }
    ],
    max_tokens=500
)

print(response)