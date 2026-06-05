import asyncio
from ai_services import generate_text

async def main():
    result = await generate_text("Halo siapa kamu?")
    print(result)

asyncio.run(main())