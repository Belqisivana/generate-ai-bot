import asyncio
import httpx
import config

from openai import AsyncOpenAI

# ============================================
# TIMEOUT
# ============================================

TIMEOUT = httpx.Timeout(
    timeout=120.0,
    connect=20.0
)

# ============================================
# OPENROUTER CLIENT
# ============================================

client = AsyncOpenAI(
    api_key=config.OPENROUTER_API_KEY,
    base_url=config.BASE_URL,
    timeout=TIMEOUT
)

# ============================================
# GENERATE TEXT
# ============================================

async def generate_text(prompt: str) -> str:

    models = [
        "deepseek/deepseek-chat-v3-0324:free",
        "google/gemma-3-12b-it:free",
        "mistralai/mistral-7b-instruct:free"
    ]

    for model in models:

        try:

            print("\n========== OPENROUTER TEXT ==========")
            print("MODEL:", model)
            print("PROMPT:", prompt)

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=config.TEXT_MODEL,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=1000
                ),
                timeout=120
            )

            result = response.choices[0].message.content

            if result:
                print("SUCCESS:", model)
                return result

        except Exception as e:

            print(f"\nFAILED MODEL: {model}")
            print(type(e).__name__)
            print(e)

            continue

    return "Maaf, AI sedang sibuk. Silakan coba lagi beberapa saat."

# ============================================
# GENERATE IMAGE
# ============================================

async def generate_image(prompt: str):

    print("🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption).")
    return None

# ============================================
# GENERATE VIDEO
# ============================================

async def generate_video(prompt: str):

    print("🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption).")
    return None

# ============================================
# IMAGE + CAPTION
# ============================================

async def generate_image_with_caption(prompt: str):

    try:

        image = await generate_image(prompt)

        if not image:
            return None

        caption = await generate_text(
            f"Buat caption singkat maksimal 2 kalimat untuk gambar berikut: {prompt}"
        )

        return {
            "image": image,
            "caption": caption
        }

    except Exception as e:

        print("🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption).", e)

        return None

# ============================================
# VIDEO + CAPTION
# ============================================

async def generate_video_with_caption(prompt: str):

    try:

        video = await generate_video(prompt)

        if not video:
            return None

        caption = await generate_text(
            f"Buat caption singkat maksimal 2 kalimat untuk video berikut: {prompt}"
        )

        return {
            "video": video,
            "caption": caption
        }

    except Exception as e:

        print("🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption).", e)

        return None