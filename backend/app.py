from fastapi import FastAPI, Request
import asyncio
import time
import backend.ai_services as ai_services
from backend.ai_services import BudgetExceededError

from backend.whatsapp_service import send_text
from backend.google_drive_service import upload_file_to_drive

app = FastAPI()

BOT_START_TIME = int(time.time())

# Anti duplicate message
processed_messages = set()

# State management
user_states = {}

# Per-user lock to prevent race conditions
user_locks = {}

# Auto-timeout: timer task per user (cancel session jika idle 2 menit)
user_timeout_tasks = {}
SESSION_TIMEOUT = 120  # detik

# =====================================
# KONSTANTA RASIO & RESOLUSI
# =====================================

RASIO_OPTIONS = {
    "1": {"label": "1:1",  "desc": "Square — Feed"},
    "2": {"label": "9:16", "desc": "Portrait — Story/Reels"},
    "3": {"label": "16:9", "desc": "Landscape — YouTube/Banner"},
    "4": {"label": "3:4",  "desc": "Portrait — Feed"},
    "5": {"label": "4:3",  "desc": "Landscape — Presentasi"},
    "6": {"label": "4:5",  "desc": "Portrait — Feed Instagram"},
    "7": {"label": "5:4",  "desc": "Landscape — Feed"},
    "8": {"label": "3:2",  "desc": "Landscape — Foto"},
    "9": {"label": "2:3",  "desc": "Portrait — Foto"},
}

RESOLUSI_OPTIONS = {
    "1": {"label": "480p", "desc": "Cepat, ukuran kecil"},
    "2": {"label": "720p", "desc": "Standar, kualitas baik"},
}

# =====================================
# PESAN - PESAN BOT
# =====================================

MSG_WELCOME = """👋 Selamat Datang di AI Content Generator
Saya dapat membantu mengubah ide atau deskripsi Anda menjadi:

1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption

✏️ Cara Penggunaan
Kirimkan ide atau deskripsi konten yang ingin dibuat.
Contoh:
• Kucing astronaut berjalan di bulan
• Promosi kopi kekinian
• Pantai tropis saat matahari terbenam

Setelah menerima deskripsi Anda, saya akan menanyakan jenis konten yang ingin dibuat.
Silakan kirim ide atau deskripsi konten Anda."""

MSG_MENU = """✅ Prompt diterima

Prompt:
{prompt}

Pilih jenis konten yang ingin dibuat:

1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption
0. Batal

Balas dengan ANGKA saja."""

MSG_RASIO = """📐 Pilih rasio gambar:

1. 1:1   — Square (Feed)
2. 9:16  — Portrait (Story/Reels)
3. 16:9  — Landscape (YouTube/Banner)
4. 3:4   — Portrait (Feed)
5. 4:3   — Landscape (Presentasi)
6. 4:5   — Portrait (Feed Instagram)
7. 5:4   — Landscape (Feed)
8. 3:2   — Landscape (Foto)
9. 2:3   — Portrait (Foto)

Balas dengan ANGKA saja."""

MSG_RESOLUSI = """Rasio dipilih: {rasio} ({desc_rasio})

📏 Pilih resolusi output:

1. 480p  — Cepat, ukuran kecil
2. 720p  — Standar, kualitas baik

Balas dengan ANGKA saja."""

MSG_KONFIRMASI_GENERATE = """🔍 Konfirmasi Generate

Prompt   : {prompt}
Rasio    : {rasio} ({desc_rasio})
Resolusi : {resolusi}

Ketik YA untuk lanjut atau BATAL untuk membatalkan."""

MSG_INVALID_MENU = """❌ Pilihan tidak valid.

Balas dengan ANGKA sesuai menu:

1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption
0. Batal"""

MSG_INVALID_RASIO = """❌ Pilihan rasio tidak valid.

Balas dengan angka 1-9 sesuai pilihan di atas."""

MSG_INVALID_RESOLUSI = """❌ Pilihan resolusi tidak valid.

Balas dengan angka 1-2 sesuai pilihan di atas."""

MSG_CANCELLED = """🚫 Proses dibatalkan.

Silakan kirim ide atau deskripsi konten baru untuk memulai lagi."""

MSG_SESSION_TIMEOUT = """⏰ Sesi Anda telah berakhir karena tidak ada aktivitas selama 2 menit.

Silakan kirim ide atau deskripsi konten baru untuk memulai kembali."""

MSG_CAPTION_REVISION = """{caption}

---
💡 Jika ingin mengembangkan atau merevisi caption ini, langsung kirim instruksinya.

Contoh:
• buat lebih profesional
• lebih santai
• tambahkan CTA
• tambahkan hashtag

Ketik SELESAI jika sudah selesai."""

MSG_CAPTION_REVISED = """{caption}

---
💡 Mau revisi lagi? Langsung kirim instruksinya.
Ketik SELESAI jika sudah selesai."""

MSG_CAPTION_DONE = """✅ Caption sudah selesai.

Silakan kirim ide baru untuk membuat konten berikutnya."""

MSG_FEATURE_WIP = """⚠️ Fitur {fitur} masih dalam pengembangan.

Sementara Anda bisa menggunakan menu 5 (Caption).
Kirim ide baru untuk mencoba lagi."""

MSG_ERROR_GENERAL = """⚠️ Terjadi kendala teknis.

Silakan coba kirim ulang pesan Anda. Jika masih error, tunggu beberapa saat."""

MSG_ERROR_BUDGET = """⚠️ Budget API harian telah habis.

Pembuatan konten tidak dapat dilakukan sementara ini. Silakan hubungi admin atau coba lagi besok."""

MSG_ERROR_CONTENT_FILTER = """⚠️ Deskripsi kamu tidak dapat diproses karena terdeteksi oleh content filter.

Coba gunakan deskripsi yang berbeda dan hindari kata-kata yang sensitif."""

MSG_ERROR_UPLOAD = """⚠️ Konten berhasil dibuat, namun gagal upload ke Drive.

Silakan coba lagi atau hubungi admin jika masalah berlanjut."""

# =====================================
# HELPER
# =====================================

def get_msg_id(payload: dict) -> str:
    msg_id = (
        payload.get("id")
        or payload.get("messageId")
        or payload.get("_data", {}).get("id", {}).get("_serialized")
    )
    if not msg_id:
        sender = payload.get("from", "")
        body = payload.get("body") or payload.get("text") or ""
        timestamp = payload.get("timestamp", "")
        msg_id = f"{sender}_{timestamp}_{body[:30]}"
    return msg_id


# =====================================
# TIMEOUT HELPERS
# =====================================

def cancel_timeout(sender_number: str):
    """Batalkan timer timeout yang sedang berjalan untuk user ini."""
    task = user_timeout_tasks.pop(sender_number, None)
    if task and not task.done():
        task.cancel()


async def _timeout_worker(sender_number: str):
    """Coroutine yang menunggu SESSION_TIMEOUT detik, lalu reset sesi user."""
    try:
        await asyncio.sleep(SESSION_TIMEOUT)
    except asyncio.CancelledError:
        return  # Timer dibatalkan karena user aktif kembali

    # Cek apakah user masih dalam sesi aktif (bukan step generating)
    state = user_states.get(sender_number)
    if state and state.get("step") != "generating":
        print(f"[TIMEOUT] Reset sesi user {sender_number} karena idle {SESSION_TIMEOUT}s")
        user_states.pop(sender_number, None)
        user_timeout_tasks.pop(sender_number, None)
        await send_text(sender_number, MSG_SESSION_TIMEOUT)


def reset_timeout(sender_number: str):
    """Cancel timer lama dan mulai timer baru untuk user ini."""
    cancel_timeout(sender_number)
    task = asyncio.create_task(_timeout_worker(sender_number))
    user_timeout_tasks[sender_number] = task


async def handle_ai_error(sender_number: str, e: Exception) -> dict:
    """Kirim pesan error yang tepat ke user berdasarkan jenis error."""
    if isinstance(e, BudgetExceededError):
        print(f"[BUDGET ERROR] {e}")
        await send_text(sender_number, MSG_ERROR_BUDGET)
        cancel_timeout(sender_number)
    elif "di-block" in str(e).lower() or "content filter" in str(e).lower() or "blocked" in str(e).lower():
        print(f"[CONTENT FILTER] {e}")
        await send_text(sender_number, MSG_ERROR_CONTENT_FILTER)
    else:
        print("AI ERROR:", e)
        await send_text(sender_number, MSG_ERROR_GENERAL)
    user_states[sender_number] = {"step": "waiting_prompt"}
    reset_timeout(sender_number)
    return {"status": "ai_error"}


async def handle_message(sender_number: str, incoming_msg: str):
    """Core message handler — runs inside per-user lock."""

    # =====================================
    # COMMAND GLOBAL
    # =====================================

    if incoming_msg.lower() in ["reset", "mulai", "restart", "/start"]:
        cancel_timeout(sender_number)
        user_states.pop(sender_number, None)
        await send_text(sender_number, MSG_WELCOME)
        return {"status": "reset"}

    if incoming_msg.lower() in ["help", "bantuan", "/help"]:
        reset_timeout(sender_number)
        await send_text(sender_number, MSG_WELCOME)
        return {"status": "help"}

    # =====================================
    # USER BARU
    # =====================================

    if sender_number not in user_states:
        user_states[sender_number] = {"step": "waiting_prompt"}
        reset_timeout(sender_number)
        await send_text(sender_number, MSG_WELCOME)
        return {"status": "welcome_sent"}

    # Perpanjang timer setiap kali user mengirim pesan
    reset_timeout(sender_number)

    user_state = user_states[sender_number]
    print(f"STEP: {user_state['step']}")

    # =====================================
    # STEP: WAITING PROMPT
    # =====================================

    if user_state["step"] == "waiting_prompt":
        user_state["prompt"] = incoming_msg
        user_state["step"] = "waiting_menu"
        await send_text(sender_number, MSG_MENU.format(prompt=incoming_msg))
        return {"status": "menu_sent"}

    # =====================================
    # STEP: WAITING MENU
    # =====================================

    if user_state["step"] == "waiting_menu":

        if incoming_msg not in ["0", "1", "2", "3", "4", "5"]:
            await send_text(sender_number, MSG_INVALID_MENU)
            return {"status": "invalid_menu"}

        if incoming_msg == "0":
            cancel_timeout(sender_number)
            user_states.pop(sender_number, None)
            await send_text(sender_number, MSG_CANCELLED)
            return {"status": "cancelled"}

        user_state["menu"] = incoming_msg

        if incoming_msg == "5":
            user_state["step"] = "generating"
            await send_text(sender_number, "✏️ Membuat caption...")
            prompt = user_state.get("prompt", "")

            try:
                caption = await ai_services.generate_text(
                    f"Create a professional, attractive, and engaging social media caption in Indonesian language for: {prompt}"
                )
            except Exception as e:
                return await handle_ai_error(sender_number, e)

            user_states[sender_number] = {
                "step": "waiting_caption_revision",
                "original_prompt": prompt,
                "last_caption": caption
            }
            await send_text(sender_number, MSG_CAPTION_REVISION.format(caption=caption))
            return {"status": "caption_done"}

        user_state["step"] = "waiting_rasio"
        await send_text(sender_number, MSG_RASIO)
        return {"status": "rasio_asked"}

    # =====================================
    # STEP: WAITING RASIO
    # =====================================

    if user_state["step"] == "waiting_rasio":

        if incoming_msg not in RASIO_OPTIONS:
            await send_text(sender_number, MSG_INVALID_RASIO)
            return {"status": "invalid_rasio"}

        rasio_data = RASIO_OPTIONS[incoming_msg]
        user_state["rasio"] = rasio_data["label"]
        user_state["rasio_desc"] = rasio_data["desc"]
        user_state["step"] = "waiting_resolusi"

        await send_text(
            sender_number,
            MSG_RESOLUSI.format(rasio=rasio_data["label"], desc_rasio=rasio_data["desc"])
        )
        return {"status": "resolusi_asked"}

    # =====================================
    # STEP: WAITING RESOLUSI
    # =====================================

    if user_state["step"] == "waiting_resolusi":

        if incoming_msg not in RESOLUSI_OPTIONS:
            await send_text(sender_number, MSG_INVALID_RESOLUSI)
            return {"status": "invalid_resolusi"}

        resolusi_data = RESOLUSI_OPTIONS[incoming_msg]
        user_state["resolusi"] = resolusi_data["label"]
        user_state["step"] = "waiting_konfirmasi"

        await send_text(
            sender_number,
            MSG_KONFIRMASI_GENERATE.format(
                prompt=user_state["prompt"],
                rasio=user_state["rasio"],
                desc_rasio=user_state["rasio_desc"],
                resolusi=resolusi_data["label"]
            )
        )
        return {"status": "konfirmasi_asked"}

    # =====================================
    # STEP: WAITING KONFIRMASI
    # =====================================

    if user_state["step"] == "waiting_konfirmasi":

        if incoming_msg.lower() in ["batal", "tidak", "no"]:
            cancel_timeout(sender_number)
            user_states.pop(sender_number, None)
            await send_text(sender_number, MSG_CANCELLED)
            return {"status": "cancelled"}

        if incoming_msg.lower() not in ["ya", "yes", "iya"]:
            await send_text(sender_number, "Ketik YA untuk lanjut atau BATAL untuk membatalkan.")
            return {"status": "invalid_konfirmasi"}

        prompt   = user_state.get("prompt", "")
        menu     = user_state.get("menu", "")
        rasio    = user_state.get("rasio", "1:1")
        resolusi = user_state.get("resolusi", "720p")

        # Tandai sedang generate supaya tidak bisa diinterupsi
        user_state["step"] = "generating"
        cancel_timeout(sender_number)  # Jangan timeout saat proses generate

        # ================= GAMBAR =================
        if menu == "1":
            await send_text(sender_number, f"🎨 Membuat gambar... ({rasio} / {resolusi})")
            try:
                image_result = await ai_services.generate_image(prompt, rasio=rasio, resolusi=resolusi)
            except Exception as e:
                return await handle_ai_error(sender_number, e)

            if not image_result:
                await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Gambar"))
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "feature_wip"}

            try:
                drive_link = await asyncio.to_thread(upload_file_to_drive, image_result, "image/png")
            except Exception as e:
                print("DRIVE ERROR:", e)
                await send_text(sender_number, MSG_ERROR_UPLOAD)
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "drive_error"}

            user_states[sender_number] = {"step": "waiting_prompt"}
            reset_timeout(sender_number)
            await send_text(
                sender_number,
                f"✅ Gambar berhasil dibuat!\nRasio: {rasio} | Resolusi: {resolusi}\n\n{drive_link}\n\nSilakan kirim ide baru untuk membuat konten berikutnya."
            )
            return {"status": "image_done"}

        # ================= VIDEO =================
        if menu == "2":
            await send_text(sender_number, f"🎬 Membuat video... ({rasio} / {resolusi})\nProses ini membutuhkan waktu lebih lama.")
            try:
                video_result = await ai_services.generate_video(prompt, rasio=rasio, resolusi=resolusi)
            except Exception as e:
                return await handle_ai_error(sender_number, e)

            if not video_result:
                await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Video"))
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "feature_wip"}

            try:
                drive_link = await asyncio.to_thread(upload_file_to_drive, video_result, "video/mp4")
            except Exception as e:
                print("DRIVE ERROR:", e)
                await send_text(sender_number, MSG_ERROR_UPLOAD)
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "drive_error"}

            user_states[sender_number] = {"step": "waiting_prompt"}
            reset_timeout(sender_number)
            await send_text(
                sender_number,
                f"✅ Video berhasil dibuat!\nRasio: {rasio} | Resolusi: {resolusi}\n\n{drive_link}\n\nSilakan kirim ide baru untuk membuat konten berikutnya."
            )
            return {"status": "video_done"}

        # ================= GAMBAR + CAPTION =================
        if menu == "3":
            await send_text(sender_number, f"🎨✏️ Membuat gambar dan caption... ({rasio} / {resolusi})")
            try:
                result = await ai_services.generate_image_with_caption(prompt, rasio=rasio, resolusi=resolusi)
            except Exception as e:
                return await handle_ai_error(sender_number, e)

            if not result:
                await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Gambar + Caption"))
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "feature_wip"}

            try:
                drive_link = await asyncio.to_thread(upload_file_to_drive, result["image"], "image/png")
            except Exception as e:
                print("DRIVE ERROR:", e)
                await send_text(sender_number, MSG_ERROR_UPLOAD)
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "drive_error"}

            user_states[sender_number] = {
                "step": "waiting_caption_revision",
                "original_prompt": prompt,
                "last_caption": result["caption"]
            }
            reset_timeout(sender_number)
            await send_text(sender_number, f"✅ Gambar selesai! ({rasio} / {resolusi})\n{drive_link}")
            await send_text(sender_number, MSG_CAPTION_REVISION.format(caption=result["caption"]))
            return {"status": "image_caption_done"}

        # ================= VIDEO + CAPTION =================
        if menu == "4":
            await send_text(sender_number, f"🎬✏️ Membuat video dan caption... ({rasio} / {resolusi})")
            try:
                result = await ai_services.generate_video_with_caption(prompt, rasio=rasio, resolusi=resolusi)
            except Exception as e:
                return await handle_ai_error(sender_number, e)

            if not result:
                await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Video + Caption"))
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "feature_wip"}

            try:
                drive_link = await asyncio.to_thread(upload_file_to_drive, result["video"], "video/mp4")
            except Exception as e:
                print("DRIVE ERROR:", e)
                await send_text(sender_number, MSG_ERROR_UPLOAD)
                user_states[sender_number] = {"step": "waiting_prompt"}
                return {"status": "drive_error"}

            user_states[sender_number] = {
                "step": "waiting_caption_revision",
                "original_prompt": prompt,
                "last_caption": result["caption"]
            }
            reset_timeout(sender_number)
            await send_text(sender_number, f"✅ Video selesai! ({rasio} / {resolusi})\n{drive_link}")
            await send_text(sender_number, MSG_CAPTION_REVISION.format(caption=result["caption"]))
            return {"status": "video_caption_done"}

    # =====================================
    # STEP: WAITING CAPTION REVISION
    # =====================================

    if user_state["step"] == "waiting_caption_revision":

        if incoming_msg.upper() == "SELESAI":
            cancel_timeout(sender_number)
            user_states[sender_number] = {"step": "waiting_prompt"}
            await send_text(sender_number, MSG_CAPTION_DONE)
            return {"status": "revision_finished"}

        await send_text(sender_number, "✏️ Merevisi caption...")

        try:
            new_caption = await ai_services.generate_text(
                f"""You are a professional copywriter. Write all output in Indonesian language.

Original topic: {user_state['original_prompt']}

Current caption:
{user_state['last_caption']}

Revision instruction: {incoming_msg}

Task: Revise the caption according to the instruction. Keep the original context, stay on topic. Output in Indonesian."""
            )
        except Exception as e:
            return await handle_ai_error(sender_number, e)

        user_state["last_caption"] = new_caption
        await send_text(sender_number, MSG_CAPTION_REVISED.format(caption=new_caption))
        return {"status": "caption_revised"}

    # =====================================
    # FALLBACK
    # =====================================

    user_states[sender_number] = {"step": "waiting_prompt"}
    await send_text(
        sender_number,
        "⚠️ Terjadi kesalahan. Silakan mulai dari awal.\n\nKirim ide atau deskripsi konten Anda."
    )
    return {"status": "fallback_reset"}


# =====================================
# ROUTES
# =====================================

@app.get("/")
async def home():
    return {"status": "online", "bot": "AI Content Generator"}


@app.post("/webhook")
async def whatsapp_webhook(request: Request):

    print("WEBHOOK HIT")

    try:
        data = await request.json()

        print("\n=========== WEBHOOK MASUK ===========")
        print(data)
        print("=====================================\n")

        payload = data.get("payload", {})

        # --- Anti duplikat ---
        msg_id = get_msg_id(payload)
        print("MSG ID:", msg_id)

        if not msg_id:
            return {"status": "ignored", "reason": "no_msg_id"}

        if msg_id in processed_messages:
            print("DUPLICATE DETECTED:", msg_id)
            return {"status": "duplicate"}

        processed_messages.add(msg_id)
        if len(processed_messages) > 1000:
            processed_messages.clear()

        # --- Filter event ---
        event = data.get("event")
        if event != "message":
            return {"status": "ignored", "reason": "not_message_event"}

        # --- Filter tipe pesan ---
        message_type = (payload.get("_data", {}) or {}).get("type")
        if message_type not in ["chat", "text"]:
            return {"status": "ignored", "reason": "unsupported_type"}

        # --- Filter pesan dari bot sendiri ---
        from_me = payload.get("fromMe", False)
        if from_me:
            return {"status": "ignored", "reason": "from_me"}

        # --- Filter pesan lama ---
        message_timestamp = payload.get("timestamp")
        if message_timestamp and int(message_timestamp) < BOT_START_TIME:
            print("SKIP OLD MESSAGE")
            return {"status": "ignored", "reason": "old_message"}

        # --- Filter grup ---
        sender_number = payload.get("from")
        if not sender_number:
            return {"status": "ignored", "reason": "no_sender"}
        if "@g.us" in sender_number:
            return {"status": "ignored", "reason": "group_message"}

        # --- Ambil isi pesan ---
        incoming_msg = (payload.get("body") or payload.get("text") or "").strip()
        if not incoming_msg:
            return {"status": "ignored", "reason": "empty_message"}

        print(f"DARI: {sender_number}")
        print(f"TEXT: {incoming_msg}")

        # --- Per-user lock: cegah race condition duplicate webhook ---
        if sender_number not in user_locks:
            user_locks[sender_number] = asyncio.Lock()

        if user_locks[sender_number].locked():
            print(f"SKIP: user {sender_number} sedang diproses")
            return {"status": "ignored", "reason": "user_locked"}

        async with user_locks[sender_number]:
            return await handle_message(sender_number, incoming_msg)

    except Exception as e:
        print(f"\nWEBHOOK ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e)
        }