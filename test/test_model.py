import asyncio
import config
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=config.OPENROUTER_API_KEY,
    base_url=config.BASE_URL
)

async def main():

    response = await client.chat.completions.create(
        model="minimax/minimax-m3",
        messages=[
            {
                "role": "user",
                "content": "Halo, jawab singkat."
            }
        ],
        max_tokens=50
    )

    print(response)

asyncio.run(main())