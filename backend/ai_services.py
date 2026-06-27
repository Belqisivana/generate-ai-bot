import asyncio
import httpx
import uuid
import os
import base64

import backend.config as config

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError, AuthenticationError, RateLimitError


TIMEOUT = httpx.Timeout(
    timeout=120.0,
    connect=20.0
)


_base = config.BASE_URL.rstrip("/")

# URL untuk OpenAI SDK (text)
if not _base.endswith("/v1"):
    OPENAI_BASE_URL = f"{_base}/v1"
else:
    OPENAI_BASE_URL = _base

RAW_BASE_URL = _base[:-3] if _base.endswith("/v1") else _base

print(f"[CONFIG] BASE_URL      : {config.BASE_URL}")
print(f"[CONFIG] OPENAI_BASE   : {OPENAI_BASE_URL}")
print(f"[CONFIG] RAW_BASE      : {RAW_BASE_URL}")


# ==========================================
# BUDGET GUARD
# ==========================================

class BudgetExceededError(Exception):
    """Raised saat API key melebihi budget harian — hentikan semua retry."""
    pass


def _raise_if_budget_exceeded(response: httpx.Response):
    """Cek apakah 429 disebabkan budget habis. Kalau iya, raise BudgetExceededError."""
    if response.status_code != 429:
        return
    try:
        body = response.json()
        msg = body.get("error", {}).get("message", "")
    except Exception:
        msg = response.text

    if "budget" in msg.lower() or "exceededbudget" in msg.lower():
        print(f"[BUDGET] Budget harian habis: {msg}")
        raise BudgetExceededError(
            "⚠️ Budget API harian telah habis. Silakan hubungi admin untuk menaikkan limit."
        )

# Client untuk text (OpenAI SDK)
client_text = AsyncOpenAI(
    api_key=config.LOCAL_API_KEY,
    base_url=OPENAI_BASE_URL,
    timeout=TIMEOUT
)

# ==========================================
# MAPPING RASIO + RESOLUSI → SIZE
# ==========================================

RESOLUSI_BASE = {
    "480p": 480,
    "720p": 720,
}

# Resolusi maksimal yang diizinkan
RESOLUSI_MAX = "720p"
RESOLUSI_ALLOWED = {"480p", "720p"}

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
    # Clamp resolusi ke maksimal 720p
    if resolusi not in RESOLUSI_ALLOWED:
        resolusi = RESOLUSI_MAX
    base = RESOLUSI_BASE.get(resolusi, 720)
    w_ratio, h_ratio = RASIO_MAP.get(rasio, (1, 1))

    if w_ratio >= h_ratio:
        width  = base
        height = round(base * h_ratio / w_ratio)
    else:
        height = base
        width  = round(base * w_ratio / h_ratio)

    width  = (width  // 8) * 8
    height = (height // 8) * 8

    return f"{width}x{height}"


# ==========================================
# DOWNLOAD FILE
# ==========================================

async def download_file(url: str, extension: str):
    try:
        os.makedirs("generated", exist_ok=True)
    except OSError as e:
        print(f"[DOWNLOAD] Gagal buat folder 'generated': {e}")
        raise Exception(f"Gagal buat folder penyimpanan: {e}")

    filename = f"generated/{uuid.uuid4()}.{extension}"

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(url)
            response.raise_for_status()
            with open(filename, "wb") as f:
                f.write(response.content)
        print(f"[DOWNLOAD] Berhasil simpan ke: {filename}")
        return filename

    except httpx.TimeoutException as e:
        print(f"[DOWNLOAD] Timeout: {e}")
        raise Exception("Download file timeout — server terlalu lambat merespons")

    except httpx.ConnectError as e:
        print(f"[DOWNLOAD] Tidak bisa koneksi ke {url}: {e}")
        raise Exception("Tidak bisa koneksi ke server untuk download file")

    except httpx.HTTPStatusError as e:
        print(f"[DOWNLOAD] HTTP error {e.response.status_code}: {e}")
        raise Exception(f"Download file gagal — server return HTTP {e.response.status_code}")

    except OSError as e:
        print(f"[DOWNLOAD] Gagal tulis file ke disk: {e}")
        raise Exception(f"Gagal simpan file ke disk: {e}")


# ==========================================
# TEXT
# ==========================================

async def generate_text(prompt: str) -> str:
    print("\n========== TEXT ==========")
    print("OPENAI_BASE_URL :", OPENAI_BASE_URL)
    print("MODEL           :", config.TEXT_MODEL)
    print("PROMPT          :", prompt[:100], "..." if len(prompt) > 100 else "")

    try:
        response = await asyncio.wait_for(
            client_text.chat.completions.create(
                model=config.TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            ),
            timeout=120
        )

    except asyncio.TimeoutError:
        print("[TEXT] asyncio timeout 120 detik")
        raise Exception("AI text timeout — tidak ada respons dalam 120 detik")

    except AuthenticationError as e:
        print(f"[TEXT] Authentication error: {e}")
        raise Exception("API key tidak valid atau tidak punya akses ke model text")

    except RateLimitError as e:
        print(f"[TEXT] Rate limit: {e}")
        raise Exception("Terlalu banyak request ke AI, coba lagi beberapa saat")

    except APITimeoutError as e:
        print(f"[TEXT] API timeout: {e}")
        raise Exception("AI text timeout — server tidak merespons")

    except APIConnectionError as e:
        print(f"[TEXT] Tidak bisa koneksi ke server AI: {e}")
        raise Exception("Tidak bisa koneksi ke server AI — cek koneksi internet")

    except APIStatusError as e:
        status = e.status_code
        body   = e.response.text[:300] if hasattr(e, 'response') else str(e)
        print(f"[TEXT] API status error {status}: {body}")

        if status == 400:
            raise Exception("Request text tidak valid — coba prompt yang berbeda")
        elif status == 403:
            raise Exception("Request text di-block oleh content filter server")
        elif status == 404:
            raise Exception(f"Model text '{config.TEXT_MODEL}' tidak ditemukan di server")
        elif status == 429:
            raise Exception("Rate limit server AI — coba lagi beberapa saat")
        elif status >= 500:
            raise Exception(f"Server AI sedang bermasalah (HTTP {status}) — coba lagi")
        else:
            raise Exception(f"AI text error HTTP {status}: {body}")

    except Exception as e:
        # Tangkap semua error lain yang tidak terduga
        # Pastikan tidak swallow error yang sudah di-raise di atas
        if "AI text" in str(e) or "Request text" in str(e) or "Model text" in str(e) or "Rate limit" in str(e) or "API key" in str(e):
            raise
        print(f"[TEXT] Error tidak terduga: {type(e).__name__}: {e}")
        raise Exception(f"Error tidak terduga saat generate text: {type(e).__name__}: {e}")

    if not response.choices or not response.choices[0].message.content:
        print("[TEXT] Respons kosong dari AI")
        raise Exception("AI mengembalikan respons kosong")

    result = response.choices[0].message.content.strip()
    if not result:
        raise Exception("AI mengembalikan teks kosong")

    print("\n========== SUCCESS ==========")
    print(result[:200])
    print("=============================")

    return result


# ==========================================
# IMAGE (pakai httpx langsung, bukan OpenAI SDK)
# Karena endpoint image LiteLLM butuh /v1/images/generations
# ==========================================

async def generate_image(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):
    size = get_size(rasio, resolusi)

    print("\n========== IMAGE ==========")
    print("MODEL    :", config.IMAGE_MODEL)
    print("PROMPT   :", prompt[:100])
    print("SIZE     :", size)

    endpoint = f"{RAW_BASE_URL}/v1/images/generations"
    print("ENDPOINT :", endpoint)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {config.LOCAL_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": config.IMAGE_MODEL,
                    "prompt": prompt,
                    "size": size
                }
            )

    except httpx.TimeoutException as e:
        print(f"[IMAGE] Timeout: {e}")
        raise Exception("Generate gambar timeout — server tidak merespons dalam 120 detik")

    except httpx.ConnectError as e:
        print(f"[IMAGE] Tidak bisa koneksi: {e}")
        raise Exception("Tidak bisa koneksi ke server AI untuk generate gambar")

    except Exception as e:
        print(f"[IMAGE] Error tidak terduga saat request: {type(e).__name__}: {e}")
        raise Exception(f"Error tidak terduga saat generate gambar: {type(e).__name__}")

    print(f"[IMAGE] Status: {response.status_code}")
    print(f"[IMAGE] Body: {response.text[:300]}")

    status = response.status_code
    if status == 400:
        raise Exception(f"Ukuran gambar '{size}' tidak didukung model ini, atau prompt tidak valid")
    elif status == 401:
        raise Exception("API key tidak valid untuk generate gambar")
    elif status == 403:
        raise Exception("Request gambar di-block oleh content filter server")
    elif status == 404:
        raise Exception(f"Model image '{config.IMAGE_MODEL}' tidak ditemukan di server")
    elif status == 429:
        _raise_if_budget_exceeded(response)
        raise Exception("Rate limit server AI — coba lagi beberapa saat")
    elif status >= 500:
        raise Exception(f"Server AI bermasalah (HTTP {status}) saat generate gambar")
    elif status not in (200, 201):
        raise Exception(f"Server image return HTTP {status}")

    try:
        data = response.json()
    except Exception as e:
        print(f"[IMAGE] Respons bukan JSON valid: {e}")
        raise Exception("Respons server image tidak bisa dibaca — format tidak valid")

    if not data.get("data"):
        print("[IMAGE] data['data'] kosong")
        raise Exception("AI tidak menghasilkan gambar — respons kosong")

    image = data["data"][0]

    # Coba ambil dari URL
    image_url = image.get("url")
    if image_url:
        try:
            return await download_file(image_url, "png")
        except Exception as e:
            print(f"[IMAGE] Gagal download dari URL: {e}")
            raise Exception(f"Gambar dibuat tapi gagal didownload: {e}")

    # Coba ambil dari base64
    b64 = image.get("b64_json")
    if b64:
        try:
            os.makedirs("generated", exist_ok=True)
            filename = f"generated/{uuid.uuid4()}.png"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(b64))
            print(f"[IMAGE] Berhasil decode b64 ke: {filename}")
            return filename
        except base64.binascii.Error as e:
            print(f"[IMAGE] Data base64 corrupt: {e}")
            raise Exception("Data gambar dari AI corrupt — coba generate ulang")
        except OSError as e:
            print(f"[IMAGE] Gagal simpan gambar: {e}")
            raise Exception(f"Gagal simpan gambar ke disk: {e}")

    print("[IMAGE] Tidak ada url maupun b64_json dalam respons")
    raise Exception("Format respons gambar dari AI tidak dikenal")


# ==========================================
# VIDEO
# ==========================================

async def _post_video(client: httpx.AsyncClient, prompt: str, size: str) -> httpx.Response:
    """Helper: kirim satu request POST video ke LiteLLM."""
    return await client.post(
        f"{RAW_BASE_URL}/v1/videos",
        headers={
            "Authorization": f"Bearer {config.LOCAL_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": config.VIDEO_MODEL,
            "prompt": prompt,
            "size": size
        }
    )


def _extract_video_url(data: dict) -> str | None:
    """Coba ambil URL video dari berbagai format respons."""
    # Format standar: {"data": [{"url": "..."}]}
    items = data.get("data") or []
    if items:
        return items[0].get("url") or items[0].get("video_url")

    # Format alternatif langsung di root
    return data.get("url") or data.get("video_url")


async def generate_video(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):
    size = get_size(rasio, resolusi)

    print("\n========== VIDEO ==========")
    print("MODEL    :", config.VIDEO_MODEL)
    print("PROMPT   :", prompt[:100])
    print("SIZE     :", size)
    print("ENDPOINT :", f"{RAW_BASE_URL}/v1/videos")

    # ── TAHAP 1: Request awal dengan timeout panjang ──
    # LiteLLM kadang blocking sampai video selesai (bisa 3-8 menit)
    # Timeout 720 detik = 12 menit
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(720.0, connect=20.0)) as client:
            print("[VIDEO] Mengirim request... (bisa memakan waktu beberapa menit)")
            response = await _post_video(client, prompt, size)

    except httpx.TimeoutException:
        print("[VIDEO] Request pertama timeout 720 detik")
        raise Exception("Generate video timeout — proses terlalu lama (>12 menit)")

    except httpx.ConnectError as e:
        print(f"[VIDEO] Tidak bisa koneksi: {e}")
        raise Exception("Tidak bisa koneksi ke server AI untuk generate video")

    except Exception as e:
        print(f"[VIDEO] Error tidak terduga: {type(e).__name__}: {e}")
        raise Exception(f"Error tidak terduga saat generate video: {type(e).__name__}")

    print(f"[VIDEO] Status: {response.status_code}")
    print(f"[VIDEO] Body: {response.text[:600]}")

    # ── Validasi status HTTP ──
    status = response.status_code
    if status == 400:
        raise Exception(f"Parameter video tidak valid — ukuran '{size}' mungkin tidak didukung")
    elif status in (401, 403):
        raise Exception("API key tidak valid atau request video di-block oleh server")
    elif status == 404:
        raise Exception(f"Endpoint video atau model '{config.VIDEO_MODEL}' tidak ditemukan")
    elif status == 429:
        _raise_if_budget_exceeded(response)
        raise Exception("Rate limit server AI — coba generate video lagi nanti")
    elif status >= 500:
        raise Exception(f"Server AI bermasalah (HTTP {status}) saat generate video")
    elif status not in (200, 201):
        raise Exception(f"Server video return HTTP {status}")

    try:
        data = response.json()
    except Exception:
        raise Exception("Respons server video tidak bisa dibaca — format tidak valid")

    # ── TAHAP 2: Cek URL langsung di respons pertama ──
    video_url = _extract_video_url(data)
    if video_url:
        print(f"[VIDEO] URL langsung ditemukan: {video_url[:80]}")
        try:
            return await download_file(video_url, "mp4")
        except Exception as e:
            raise Exception(f"Video dibuat tapi gagal didownload: {e}")

    # ── TAHAP 3: Respons async job — LiteLLM return {id, status} tanpa URL ──
    # Karena polling via GET /v1/videos/{id} tidak bisa (key restriction),
    # strategi: kirim ulang request POST yang sama, LiteLLM akan
    # deduplicate / queue dan akhirnya return URL saat video selesai.
    job_id  = data.get("id", "")
    job_status = (data.get("status") or "").lower()

    print(f"[VIDEO] Async job detected — id: {job_id[:40]}... status: '{job_status}'")
    print("[VIDEO] Mulai retry loop (kirim ulang POST tiap 30 detik)...")

    max_retries   = 5     # Maksimal 5x retry (hemat biaya)
    retry_interval = 60   # Jeda 60 detik per retry (total max ~5 menit)

    for attempt in range(1, max_retries + 1):
        print(f"[VIDEO] Retry {attempt}/{max_retries} — tunggu {retry_interval} detik...")
        await asyncio.sleep(retry_interval)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0)) as rc:
                retry_resp = await _post_video(rc, prompt, size)
        except httpx.TimeoutException:
            print(f"[VIDEO] Retry {attempt} timeout, lanjut...")
            continue
        except Exception as e:
            print(f"[VIDEO] Retry {attempt} error: {e}")
            continue

        print(f"[VIDEO] Retry {attempt} status: {retry_resp.status_code}")
        print(f"[VIDEO] Retry {attempt} body: {retry_resp.text[:400]}")

        if retry_resp.status_code not in (200, 201):
            # Cek budget dulu — kalau budget habis, stop total, jangan retry lagi
            if retry_resp.status_code == 429:
                _raise_if_budget_exceeded(retry_resp)
            print(f"[VIDEO] Retry {attempt} HTTP {retry_resp.status_code}, skip")
            continue

        try:
            retry_data = retry_resp.json()
        except Exception:
            print(f"[VIDEO] Retry {attempt} respons bukan JSON, skip")
            continue

        video_url = _extract_video_url(retry_data)
        if video_url:
            print(f"[VIDEO] URL ditemukan di retry {attempt}: {video_url[:80]}")
            try:
                return await download_file(video_url, "mp4")
            except Exception as e:
                raise Exception(f"Video dibuat tapi gagal didownload: {e}")

        # Cek apakah ada error eksplisit
        retry_status = (retry_data.get("status") or "").lower()
        if retry_status in ("failed", "error", "cancelled"):
            err_msg = retry_data.get("error") or retry_data.get("message") or "tidak diketahui"
            raise Exception(f"Server AI gagal generate video: {err_msg}")

        print(f"[VIDEO] Retry {attempt} — video belum selesai (status: '{retry_status}'), lanjut polling...")

    raise Exception(f"Video timeout setelah {max_retries} retry — server tidak kunjung selesai")


# ==========================================
# IMAGE + CAPTION
# ==========================================

async def generate_image_with_caption(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):
    image = await generate_image(prompt, rasio=rasio, resolusi=resolusi)

    if not image:
        return None

    caption = await generate_text(
        f"Create a professional, engaging social media caption (max 3 sentences) in Indonesian language for: {prompt}"
    )

    return {
        "image": image,
        "caption": caption
    }


# ==========================================
# VIDEO + CAPTION
# ==========================================

async def generate_video_with_caption(prompt: str, rasio: str = "1:1", resolusi: str = "720p"):
    video = await generate_video(prompt, rasio=rasio, resolusi=resolusi)

    if not video:
        return None

    caption = await generate_text(
        f"Create a professional, engaging social media caption (max 3 sentences) in Indonesian language for: {prompt}"
    )

    return {
        "video": video,
        "caption": caption
    }