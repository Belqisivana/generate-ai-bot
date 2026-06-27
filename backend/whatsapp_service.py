import httpx
import backend.config as config


def format_number(wa_id: str):
    if not wa_id:
        return None

    wa_id = str(wa_id).strip()

    if "@g.us" in wa_id:
        return wa_id
    if "@c.us" in wa_id:
        return wa_id
    if "@lid" in wa_id:
        return wa_id
    if wa_id.isdigit():
        return wa_id + "@c.us"

    return wa_id


async def send_text(to, text):
    if not text:
        print("[WAHA] Empty text blocked")
        return None

    to = format_number(to)

    payload = {
        "session": config.WAHA_SESSION,
        "chatId": to,
        "text": text
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                f"{config.WAHA_URL}/api/sendText",
                headers={"X-Api-Key": config.WAHA_API_KEY},
                json=payload
            )

        print(f"\n=== SEND TEXT ===")
        print(f"STATUS: {res.status_code}")
        print(f"TO: {to}")
        print(f"TEXT: {text[:50]}...")

        # WAHA bisa return 200 atau 201, keduanya sukses
        if res.status_code not in [200, 201]:
            print("[WAHA ERROR SEND TEXT]", res.text)
            return None

        try:
            return res.json()
        except:
            return {"raw": res.text}

    except Exception as e:
        print("[SEND TEXT ERROR]", e)
        return None


async def send_image(to, image_url, caption=""):
    to = format_number(to)

    payload = {
        "session": config.WAHA_SESSION,
        "chatId": to,
        "file": {
            "url": image_url,
            "mimetype": "image/png"
        },
        "caption": caption
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                f"{config.WAHA_URL}/api/sendFile",
                headers={"X-Api-Key": config.WAHA_API_KEY},
                json=payload
            )

        if res.status_code not in [200, 201]:
            print("[WAHA ERROR SEND IMAGE]", res.text)
            return None

        try:
            return res.json()
        except:
            return {"raw": res.text}

    except Exception as e:
        print("[SEND IMAGE ERROR]", e)
        return None


async def send_video(to, video_url, caption=""):
    to = format_number(to)

    payload = {
        "session": config.WAHA_SESSION,
        "chatId": to,
        "file": {
            "url": video_url,
            "mimetype": "video/mp4"
        },
        "caption": caption
    }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            res = await client.post(
                f"{config.WAHA_URL}/api/sendFile",
                headers={"X-Api-Key": config.WAHA_API_KEY},
                json=payload
            )

        if res.status_code not in [200, 201]:
            print("[WAHA ERROR SEND VIDEO]", res.text)
            return None

        try:
            return res.json()
        except:
            return {"raw": res.text}

    except Exception as e:
        print("[SEND VIDEO ERROR]", e)
        return None