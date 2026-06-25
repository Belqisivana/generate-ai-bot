from fastapi import FastAPI, Request
import asyncio
import time
import backend.ai_services as ai_services

from backend.whatsapp_service import send_text
from backend.google_drive_service import upload_file_to_drive

app = FastAPI()

BOT_START_TIME = int(time.time())

# Anti duplicate message
processed_messages = set()

# State management
user_states = {}

# =====================================
# KONSTANTA RASIO & RESOLUSI
# =====================================

RASIO_OPTIONS = {
    "1": {"label": "1:1", "desc": "Square — Feed"},
    "2": {"label": "9:16", "desc": "Portrait — Story/Reels"},
    "3": {"label": "16:9", "desc": "Landscape — YouTube/Banner"},
    "4": {"label": "3:4", "desc": "Portrait — Feed"},
    "5": {"label": "4:3", "desc": "Landscape — Presentasi"},
    "6": {"label": "4:5", "desc": "Portrait — Feed Instagram"},
    "7": {"label": "5:4", "desc": "Landscape — Feed"},
    "8": {"label": "3:2", "desc": "Landscape — Foto"},
    "9": {"label": "2:3", "desc": "Portrait — Foto"},
}

RESOLUSI_OPTIONS = {
    "1": {"label": "480p",  "desc": "Cepat, ukuran kecil"},
    "2": {"label": "720p",  "desc": "Standar, kualitas baik"},
    "3": {"label": "1080p", "desc": "HD, kualitas tinggi"},
    "4": {"label": "2K",    "desc": "Ultra HD, terbaik"},
}

# =====================================
# PESAN - PESAN BOT
# =====================================

MSG_WELCOME = """Halo! Selamat datang di *AI Content Generator*

Saya bisa bantu kamu bikin konten dari ide sederhana jadi karya keren!

Yang bisa saya buat:
1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption

Yuk mulai! Ceritain ide atau deskripsi konten yang kamu mau.

_Contoh: "Kucing astronaut berjalan di bulan" atau "Promosi kopi kekinian"_

Ketik *reset* kapan saja untuk mulai ulang."""

MSG_MENU = """Oke! Ide kamu udah saya terima

*"{prompt}"*

Pilih jenis konten yang mau dibuat:

1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption

0. Batal

Balas dengan *angka* ya"""

MSG_RASIO = """Pilih *rasio gambar* yang kamu mau:

1. 1:1   — Square (Feed)
2. 9:16  — Portrait (Story/Reels)
3. 16:9  — Landscape (YouTube/Banner)
4. 3:4   — Portrait (Feed)
5. 4:3   — Landscape (Presentasi)
6. 4:5   — Portrait (Feed Instagram)
7. 5:4   — Landscape (Feed)
8. 3:2   — Landscape (Foto)
9. 2:3   — Portrait (Foto)

Balas dengan *angka*"""

MSG_RESOLUSI = """Rasio dipilih: *{rasio}* ({desc_rasio})

Sekarang pilih *resolusi output*:

1. 480p  — Cepat, ukuran kecil
2. 720p  — Standar, kualitas baik
3. 1080p — HD, kualitas tinggi
4. 2K    — Ultra HD, terbaik

Balas dengan *angka*"""

MSG_KONFIRMASI_GENERATE = """Siap generate dengan pengaturan:

Prompt   : _{prompt}_
Rasio    : *{rasio}* ({desc_rasio})
Resolusi : *{resolusi}*

Ketik *ya* untuk lanjut atau *batal* untuk membatalkan"""

MSG_INVALID_MENU = """Ups, pilihannya belum tepat nih.

Balas dengan *angka* sesuai menu:

1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption

0. Batal"""

MSG_INVALID_RASIO = """Pilihan rasio tidak valid.

Balas dengan angka 1-9 sesuai pilihan di atas ya"""

MSG_INVALID_RESOLUSI = """Pilihan resolusi tidak valid.

Balas dengan angka 1-4 sesuai pilihan di atas ya"""

MSG_CANCELLED = """Oke, proses dibatalkan.

Kalau mau mulai lagi, tinggal kirim ide atau deskripsi konten baru ya!"""

MSG_CAPTION_REVISION = """{caption}

---
*Mau dikembangin lagi?*
Langsung kirim instruksinya aja, contoh:
- "buat lebih profesional"
- "tambahkan CTA"
- "tone lebih santai"
- "tambahkan hashtag"

Ketik *SELESAI* kalau sudah oke"""

MSG_CAPTION_REVISED = """{caption}

---
Mau revisi lagi? Langsung kirim instruksinya.
Ketik *SELESAI* kalau sudah oke"""

MSG_CAPTION_DONE = """Siap! Caption sudah selesai.

Kalau mau bikin konten baru, langsung kirim ide berikutnya ya"""

MSG_FEATURE_WIP = """Fitur *{fitur}* masih dalam pengembangan.

Sementara kamu bisa pakai menu *5 (Caption)* dulu ya!
Kirim ide baru untuk mencoba lagi"""

MSG_ERROR_GENERAL = """Waduh, ada kendala teknis nih.

Coba kirim ulang pesanmu ya. Kalau masih error, tunggu beberapa saat lagi."""

MSG_ERROR_UPLOAD = """Konten berhasil dibuat, tapi gagal upload ke Drive.

Coba lagi ya, atau hubungi admin kalau terus bermasalah."""

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

        # =====================================
        # COMMAND GLOBAL
        # =====================================

        if incoming_msg.lower() in ["reset", "mulai", "restart", "/start"]:
            user_states.pop(sender_number, None)
            await send_text(sender_number, MSG_WELCOME)
            return {"status": "reset"}

        if incoming_msg.lower() in ["help", "bantuan", "/help"]:
            await send_text(sender_number, MSG_WELCOME)
            return {"status": "help"}

        # =====================================
        # USER BARU
        # =====================================

        if sender_number not in user_states:
            user_states[sender_number] = {"step": "waiting_prompt"}
            await send_text(sender_number, MSG_WELCOME)
            return {"status": "welcome_sent"}

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
                user_states.pop(sender_number, None)
                await send_text(sender_number, MSG_CANCELLED)
                return {"status": "cancelled"}

            user_state["menu"] = incoming_msg

            # Caption tidak butuh rasio/resolusi
            if incoming_msg == "5":
                user_state["step"] = "waiting_caption_generate"
                await send_text(sender_number, "Sebentar ya, lagi nulis caption...")
                prompt = user_state.get("prompt", "")

                try:
                    caption = await ai_services.generate_text(
                        f"Buat caption profesional, menarik, dan engaging untuk konten berikut: {prompt}"
                    )
                except Exception as e:
                    print("AI ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_GENERAL)
                    user_state["step"] = "waiting_prompt"
                    return {"status": "ai_error"}

                user_states[sender_number] = {
                    "step": "waiting_caption_revision",
                    "original_prompt": prompt,
                    "last_caption": caption
                }
                await send_text(sender_number, MSG_CAPTION_REVISION.format(caption=caption))
                return {"status": "caption_done"}

            # Gambar/Video → tanya rasio dulu
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
                MSG_RESOLUSI.format(
                    rasio=rasio_data["label"],
                    desc_rasio=rasio_data["desc"]
                )
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

            if incoming_msg.lower() == "batal":
                user_states.pop(sender_number, None)
                await send_text(sender_number, MSG_CANCELLED)
                return {"status": "cancelled"}

            if incoming_msg.lower() != "ya":
                await send_text(sender_number, "Ketik *ya* untuk lanjut atau *batal* untuk membatalkan")
                return {"status": "invalid_konfirmasi"}

            prompt    = user_state.get("prompt", "")
            menu      = user_state.get("menu", "")
            rasio     = user_state.get("rasio", "1:1")
            resolusi  = user_state.get("resolusi", "720p")

            # ================= GAMBAR =================
            if menu == "1":
                await send_text(sender_number, f"Sebentar ya, lagi bikin gambarnya... ({rasio} / {resolusi})")

                try:
                    image_result = await ai_services.generate_image(prompt, rasio=rasio, resolusi=resolusi)
                except Exception as e:
                    print("AI ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_GENERAL)
                    user_state["step"] = "waiting_prompt"
                    return {"status": "ai_error"}

                if not image_result:
                    await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Gambar"))
                    user_states[sender_number] = {"step": "waiting_prompt"}
                    return {"status": "feature_wip"}

                try:
                    drive_link = await asyncio.to_thread(upload_file_to_drive, image_result, "image/png")
                except Exception as e:
                    print("DRIVE ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_UPLOAD)
                    return {"status": "drive_error"}

                user_states[sender_number] = {"step": "waiting_prompt"}
                await send_text(
                    sender_number,
                    f"Gambar berhasil dibuat!\nRasio: {rasio} | Resolusi: {resolusi}\n\n{drive_link}\n\nMau bikin konten lain? Kirim ide berikutnya ya"
                )
                return {"status": "image_done"}

            # ================= VIDEO =================
            if menu == "2":
                await send_text(sender_number, f"Sebentar ya, lagi bikin videonya... ({rasio} / {resolusi})\nIni butuh waktu lebih lama ya")

                try:
                    video_result = await ai_services.generate_video(prompt, rasio=rasio, resolusi=resolusi)
                except Exception as e:
                    print("AI ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_GENERAL)
                    user_state["step"] = "waiting_prompt"
                    return {"status": "ai_error"}

                if not video_result:
                    await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Video"))
                    user_states[sender_number] = {"step": "waiting_prompt"}
                    return {"status": "feature_wip"}

                try:
                    drive_link = await asyncio.to_thread(upload_file_to_drive, video_result, "video/mp4")
                except Exception as e:
                    print("DRIVE ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_UPLOAD)
                    return {"status": "drive_error"}

                user_states[sender_number] = {"step": "waiting_prompt"}
                await send_text(
                    sender_number,
                    f"Video berhasil dibuat!\nRasio: {rasio} | Resolusi: {resolusi}\n\n{drive_link}\n\nMau bikin konten lain? Kirim ide berikutnya ya"
                )
                return {"status": "video_done"}

            # ================= GAMBAR + CAPTION =================
            if menu == "3":
                await send_text(sender_number, f"Sebentar ya, lagi bikin gambar dan caption... ({rasio} / {resolusi})")

                try:
                    result = await ai_services.generate_image_with_caption(prompt, rasio=rasio, resolusi=resolusi)
                except Exception as e:
                    print("AI ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_GENERAL)
                    user_state["step"] = "waiting_prompt"
                    return {"status": "ai_error"}

                if not result:
                    await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Gambar + Caption"))
                    user_states[sender_number] = {"step": "waiting_prompt"}
                    return {"status": "feature_wip"}

                try:
                    drive_link = await asyncio.to_thread(upload_file_to_drive, result["image"], "image/png")
                except Exception as e:
                    print("DRIVE ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_UPLOAD)
                    return {"status": "drive_error"}

                user_states[sender_number] = {
                    "step": "waiting_caption_revision",
                    "original_prompt": prompt,
                    "last_caption": result["caption"]
                }
                await send_text(sender_number, f"Gambar selesai! ({rasio} / {resolusi})\n{drive_link}")
                await send_text(sender_number, MSG_CAPTION_REVISION.format(caption=result["caption"]))
                return {"status": "image_caption_done"}

            # ================= VIDEO + CAPTION =================
            if menu == "4":
                await send_text(sender_number, f"Sebentar ya, lagi bikin video dan caption... ({rasio} / {resolusi})")

                try:
                    result = await ai_services.generate_video_with_caption(prompt, rasio=rasio, resolusi=resolusi)
                except Exception as e:
                    print("AI ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_GENERAL)
                    user_state["step"] = "waiting_prompt"
                    return {"status": "ai_error"}

                if not result:
                    await send_text(sender_number, MSG_FEATURE_WIP.format(fitur="Video + Caption"))
                    user_states[sender_number] = {"step": "waiting_prompt"}
                    return {"status": "feature_wip"}

                try:
                    drive_link = await asyncio.to_thread(upload_file_to_drive, result["video"], "video/mp4")
                except Exception as e:
                    print("DRIVE ERROR:", e)
                    await send_text(sender_number, MSG_ERROR_UPLOAD)
                    return {"status": "drive_error"}

                user_states[sender_number] = {
                    "step": "waiting_caption_revision",
                    "original_prompt": prompt,
                    "last_caption": result["caption"]
                }
                await send_text(sender_number, f"Video selesai! ({rasio} / {resolusi})\n{drive_link}")
                await send_text(sender_number, MSG_CAPTION_REVISION.format(caption=result["caption"]))
                return {"status": "video_caption_done"}

        # =====================================
        # STEP: WAITING CAPTION REVISION
        # =====================================

        if user_state["step"] == "waiting_caption_revision":

            if incoming_msg.upper() == "SELESAI":
                user_states[sender_number] = {"step": "waiting_prompt"}
                await send_text(sender_number, MSG_CAPTION_DONE)
                return {"status": "revision_finished"}

            await send_text(sender_number, "Oke, lagi direvisi...")

            try:
                new_caption = await ai_services.generate_text(
                    f"""Kamu adalah copywriter profesional.

Prompt awal: {user_state['original_prompt']}

Caption saat ini:
{user_state['last_caption']}

Instruksi revisi dari user: {incoming_msg}

Tugas: Revisi caption sesuai instruksi. Pertahankan konteks asli, jangan keluar dari topik."""
                )
            except Exception as e:
                print("AI ERROR:", e)
                await send_text(sender_number, MSG_ERROR_GENERAL)
                return {"status": "ai_error"}

            user_state["last_caption"] = new_caption
            await send_text(sender_number, MSG_CAPTION_REVISED.format(caption=new_caption))
            return {"status": "caption_revised"}

        # =====================================
        # FALLBACK
        # =====================================

        user_states[sender_number] = {"step": "waiting_prompt"}
        await send_text(
            sender_number,
            "Ups, sepertinya ada yang error. Yuk mulai dari awal!\n\nKirim ide atau deskripsi konten kamu."
        )
        return {"status": "fallback_reset"}

    except Exception as e:
        print(f"\nWEBHOOK ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e)
        }