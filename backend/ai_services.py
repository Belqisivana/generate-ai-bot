import asyncio
import httpx
import uuid
import os
import base64

import backend.config as config

from openai import AsyncOpenAI
from backend.file_service import download_file


TIMEOUT = httpx.Timeout(
    timeout=120.0,
    connect=20.0
)

client_text = AsyncOpenAI(
    api_key=config.LOCAL_API_KEY,
    base_url=config.BASE_URL,
    timeout=TIMEOUT
)

client_image = AsyncOpenAI(
    api_key=config.LOCAL_API_KEY,
    base_url=config.BASE_URL,
    timeout=TIMEOUT
)

# ==========================================
# MAPPING RASIO + RESOLUSI → SIZE
# ==========================================

# Base pixel per resolusi (sisi terpanjang)
RESOLUSI_BASE = {
    "480p":  480,
    "720p":  720,
    "1080p": 1080,
    "2K":    1440,
}

# Rasio → (width_ratio, height_ratio)
RASIO_MAP = {
    "1:1":  (1, 1),
    "9:16": (9, 16),
    "16:9": (16, 9),
    "3:4":  (3, 4),
    "4:3":  (4, 3),
    "4:5":  (4, 5),
    "5:4":  (5, 4),
    "3:2":  (3, 2),
    "2:3":  (2, 3),
    "21:9": (21, 9),
}

def get_size(rasio: str = "1:1", resolusi: str = "720p") -> str:
    """
    Konversi rasio + resolusi jadi string size, misal "1280x720".
    Sisi terpanjang = base resolusi, sisi lain dihitung dari rasio.
    """
    base = RESOLUSI_BASE.get(resolusi, 720)
    w_ratio, h_ratio = RASIO_MAP.get(rasio, (1, 1))

    if w_ratio >= h_ratio:
        # landscape atau square → width jadi base
        width  = base
        height = round(base * h_ratio / w_ratio)
    else:
        # portrait → height jadi base
        height = base
        width  = round(base * w_ratio / h_ratio)

    # Bulatkan ke kelipatan 8 (dibutuhkan banyak model AI)
    width  = (width  // 8) * 8
    height = (height // 8) * 8

    return f"{width}x{height}"


# ==========================================
# DOWNLOAD FILE
# ==========================================

async def download_file(url: str, extension: str):

    os.makedirs("generated", exist_ok=True)
    filename = f"generated/{uuid.uuid4()}.{extension}"

    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.get(url)
        response.raise_for_status()
        with open(filename, "wb") as f:
            f.write(response.content)

    return filename


# ==========================================
# TEXT
# ==========================================

async def generate_text(prompt: str) -> str:

    try:
        print("\n========== TEXT ==========")
        print("BASE_URL :", config.BASE_URL)
        print("MODEL    :", config.TEXT_MODEL)
        print("PROMPT   :", prompt)

        response = await asyncio.wait_for(
            client_text.chat.completions.create(
                model=config.TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            ),
            timeout=120
        )

        print("\n========== RAW RESPONSE ==========")
        print(response)
        print("==================================")

        if not response.choices:
            return "Maaf, AI tidak memberikan respon."

        result = response.choices[0].message.content

        if not result:
            return "Maaf, AI tidak memberikan respon."

        print("\n========== SUCCESS ==========")
        print(result)
        print("=============================")

        return result

    except Exception as e:
        print("\n========== TEXT ERROR ==========")
        print("TYPE :", type(e).__name__)
        print("ERROR:", str(e))
        print("================================")
        return "Maaf, AI sedang sibuk. Silakan coba lagi beberapa saat."


# ==========================================
# IMAGE
# ==========================================

async def generate_image(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):

    try:
        size = get_size(rasio, resolusi)

        print("\n========== IMAGE ==========")
        print("MODEL    :", config.IMAGE_MODEL)
        print("PROMPT   :", prompt)
        print("RASIO    :", rasio)
        print("RESOLUSI :", resolusi)
        print("SIZE     :", size)

        response = await client_image.images.generate(
            model=config.IMAGE_MODEL,
            prompt=prompt,
            size=size
        )

        print(response)

        if not response.data:
            return None

        image = response.data[0]

        if hasattr(image, "url") and image.url:
            return await download_file(image.url, "png")

        if hasattr(image, "b64_json") and image.b64_json:
            os.makedirs("generated", exist_ok=True)
            filename = f"generated/{uuid.uuid4()}.png"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(image.b64_json))
            return filename

        return None

    except Exception as e:
        print("\nIMAGE ERROR")
        print(type(e).__name__)
        print(e)
        return None


# ==========================================
# VIDEO
# ==========================================

async def generate_video(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):

    try:
        size = get_size(rasio, resolusi)

        print("\n========== VIDEO ==========")
        print("MODEL    :", config.VIDEO_MODEL)
        print("PROMPT   :", prompt)
        print("RASIO    :", rasio)
        print("RESOLUSI :", resolusi)
        print("SIZE     :", size)

        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(
                f"{config.BASE_URL}/videos/generations",
                headers={
                    "Authorization": f"Bearer {config.LOCAL_API_KEY}"
                },
                json={
                    "model": config.VIDEO_MODEL,
                    "prompt": prompt,
                    "size": size
                }
            )

        print(response.status_code)
        print(response.text)

        response.raise_for_status()

        data = response.json()

        if not data.get("data"):
            return None

        video_url = data["data"][0].get("url")

        if not video_url:
            return None

        return await download_file(video_url, "mp4")

    except Exception as e:
        print("\nVIDEO ERROR")
        print(type(e).__name__)
        print(e)
        return None


# ==========================================
# IMAGE + CAPTION
# ==========================================

async def generate_image_with_caption(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):

    try:
        image = await generate_image(prompt, rasio=rasio, resolusi=resolusi)

        if not image:
            return None

        caption = await generate_text(
            f"Buat caption profesional, menarik, dan engaging maksimal 3 kalimat untuk konten berikut: {prompt}"
        )

        return {
            "image": image,
            "caption": caption
        }

    except Exception as e:
        print("\nIMAGE CAPTION ERROR")
        print(type(e).__name__)
        print(e)
        return None


# ==========================================
# VIDEO + CAPTION
# ==========================================

async def generate_video_with_caption(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):

    try:
        video = await generate_video(prompt, rasio=rasio, resolusi=resolusi)

        if not video:
            return None

        caption = await generate_text(
            f"Buat caption profesional, menarik, dan engaging maksimal 3 kalimat untuk konten berikut: {prompt}"
        )

        return {
            "video": video,
            "caption": caption
        }

    except Exception as e:
        print("\nVIDEO CAPTION ERROR")
        print(type(e).__name__)
        print(e)
        return None