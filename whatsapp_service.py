import httpx
import config


def format_number(wa_id: str):
    if not wa_id:
        return None

    wa_id = str(wa_id).strip()

    # GROUP → jangan diubah
    if "@g.us" in wa_id:
        return wa_id

    # PRIVATE CHAT → WAHA internal ID (jangan dimodif angka)
    if "@c.us" in wa_id:
        return wa_id

    if "@lid" in wa_id:
        # WAHA kadang butuh tetap raw lid format
        return wa_id

    # fallback: kalau sudah numeric doang
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
        print("STATUS:", res.status_code)
        print("BODY:", res.text)
        print("\n=== SEND TEXT ===")
        print("STATUS:", res.status_code)
        print("RESPONSE:", res.text)
        print("TO:", to)
        print("TEXT:", text)
        print("DEBUG CHAT ID FINAL:", to)

        # 🔥 FIX 2: jangan pakai raise_for_status (biar tidak crash silent flow)
        if res.status_code != 200:
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

        print("\n=== SEND IMAGE ===")
        print("STATUS:", res.status_code)
        print("RESPONSE:", res.text)

        if res.status_code != 200:
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

        print("\n=== SEND VIDEO ===")
        print("STATUS:", res.status_code)
        print("RESPONSE:", res.text)

        if res.status_code != 200:
            print("[WAHA ERROR SEND VIDEO]", res.text)
            return None

        try:
            return res.json()
        except:
            return {"raw": res.text}

    except Exception as e:
        print("[SEND VIDEO ERROR]", e)
        return None