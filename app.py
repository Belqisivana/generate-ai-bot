from fastapi import FastAPI, Request
import asyncio
import time 
import ai_services

from whatsapp_service import send_text
from google_drive_service import upload_file_to_drive

app = FastAPI()

BOT_START_TIME = int(time.time())

# anti duplicate message
processed_messages = set()

user_states = {}

@app.get("/")
async def home():
    return {"status": "online"}

WELCOME_MESSAGE = """
👋 Selamat Datang di AI Content Generator
Saya dapat membantu mengubah ide atau deskripsi Anda menjadi:
1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption

📝 Cara Penggunaan
Kirimkan ide atau deskripsi konten yang ingin dibuat.
Contoh:
• Kucing astronaut berjalan di bulan
• Promosi kopi kekinian
• Pantai tropis saat matahari terbenam

Setelah menerima deskripsi Anda, saya akan menanyakan jenis konten yang ingin dibuat.
Silakan kirim ide atau deskripsi konten Anda.
"""

@app.post("/webhook")
async def whatsapp_webhook(request: Request):

    print("🔥 WEBHOOK HIT")

    try:
        data = await request.json()

        print("\n=========== WEBHOOK MASUK ===========")
        print(data)
        print("=====================================\n")

        payload = data.get("payload", {})

        msg_id = (
            payload.get("id")
            or payload.get("messageId")
            or payload.get("_data", {}).get("id", {}).get("_serialized")
        )

        if not msg_id:
            return {"status": "ignored"}

        if msg_id in processed_messages:
            return {"status": "duplicate"}

        processed_messages.add(msg_id)

        # cleanup memory
        if len(processed_messages) > 1000:
            processed_messages.clear()

        event = data.get("event")

        message_type = (payload.get("_data", {}) or {}).get("type")

        if message_type not in ["chat", "text"]:
            return {"status": "ignored"}

        from_me = payload.get("fromMe", False)

        print("EVENT:", event)
        print("MESSAGE TYPE:", message_type)
        print("FROM ME:", from_me)

        if event != "message":
            return {"status": "ignored"}

        if from_me:
            return {"status": "ignored"}

        message_timestamp = payload.get("timestamp")

        if message_timestamp:

            if int(message_timestamp) < BOT_START_TIME:

                print("SKIP OLD MESSAGE")
                print("MESSAGE TIME:", message_timestamp)
                print("BOT START:", BOT_START_TIME)

                return {"status": "old_message"}

        sender_number = payload.get("from")
        if not sender_number:
            return {"status": "ignored"}

        if "@g.us" in sender_number:
            return {"status": "ignored"}

        incoming_msg = payload.get("body") or payload.get("text") or ""
        incoming_msg = incoming_msg.strip()

        if not incoming_msg:
            return {"status": "ignored"}

        print("DARI:", sender_number)
        print("TEXT:", incoming_msg)

        print("USER STATES:", user_states)
        print("SENDER:", sender_number)
        # =====================================
        # USER BARU
        # =====================================

        if sender_number not in user_states:

            user_states[sender_number] = {
                "step": "waiting_prompt",
            }

            await send_text(
                sender_number,
                WELCOME_MESSAGE
            )
            return {"status": "welcome_sent"}
        
        user_state = user_states[sender_number]
        
        # =====================================
        # REVISI / PENGEMBANGAN CAPTION
        # =====================================

        if user_state["step"] == "waiting_caption_revision":

            if incoming_msg.upper() == "SELESAI":

                user_states[sender_number] = {
                    "step": "waiting_prompt"
                }

                await send_text(
                    sender_number,
                    "✅ Baik. Silakan kirim prompt baru."
                )

                return {"status": "revision_finished"}

            await send_text(
                sender_number,
                "✍️ Mengembangkan caption..."
            )

            new_caption = await ai_services.generate_text(
                f"""
        Prompt awal:
        {user_state['original_prompt']}

        Caption saat ini:
        {user_state['last_caption']}

        Instruksi user:
        {incoming_msg}

        Tugas:
        Perbaiki dan kembangkan caption sesuai instruksi user.
        Jangan membuat caption baru yang keluar konteks.
        """
            )

            user_state["last_caption"] = new_caption

            await send_text(
                sender_number,
                f"""{new_caption}

        💡 Jika masih ingin revisi atau mengembangkan caption,
        langsung kirim instruksinya lagi.

        Ketik SELESAI jika sudah selesai.
        """
            )

            return {"status": "caption_revised"}
        
        # =====================================
        # MENUNGGU PROMPT
        # =====================================

        if user_state["step"] == "waiting_prompt":

            user_state["prompt"] = incoming_msg
            user_state["step"] = "waiting_menu"

            await send_text(
                sender_number,
                f"""✅ Prompt diterima

        Prompt:
        {incoming_msg}

        Pilih jenis konten yang ingin dibuat:

        1. Gambar
        2. Video
        3. Gambar + Caption
        4. Video + Caption
        5. Caption
        0. Batal

        Balas dengan ANGKA saja."""
                    )

            return {"status": "waiting_menu"}

        # =====================================
        # MENUNGGU PILIHAN MENU
        # =====================================

        if user_state["step"] == "waiting_menu":

            if incoming_msg not in ["0", "1", "2", "3", "4", "5"]:

                await send_text(
                    sender_number,
                    """⚠️ Pilihan tidak valid.

Silakan balas dengan angka:

1. Gambar
2. Video
3. Gambar + Caption
4. Video + Caption
5. Caption
0. Batal"""
                )

                return {"status": "invalid_menu"}

            prompt = user_state["prompt"]

            # ================= BATAL =================

            if incoming_msg == "0":

                del user_states[sender_number]

                await send_text(
                    sender_number,
                    "❌ Proses dibatalkan.\n\nSilakan kirim kata sapaan pembuka baru (contoh: 'tes', 'halo', 'p! balap', dan sebagainya)."
                )

                return {"status": "cancelled"}

            # ================= CAPTION =================

            if incoming_msg == "5":

                await send_text(
                    sender_number,
                    "✍️ Membuat caption..."
                )

                caption = await ai_services.generate_text(
                    f"Buat caption profesional untuk: {prompt}"
                )

                user_states[sender_number] = {
                    "step": "waiting_caption_revision",
                    "original_prompt": prompt,
                    "last_caption": caption
                }

                await send_text(
                    sender_number,
                    f"""{caption}

                💡 Jika ingin mengembangkan atau merevisi caption ini,
                langsung kirim instruksinya.

                Contoh:
                • buat lebih profesional
                • lebih santai
                • tambahkan CTA
                • tambahkan hashtag

                Ketik SELESAI jika sudah selesai.
                """
                )

                return {"status": "caption_done"}

            # ================= GAMBAR =================

            if incoming_msg == "1":

                await send_text(
                    sender_number,
                    "🎨 Sedang membuat gambar..."
                )

                image_result = await ai_services.generate_image(prompt)

                if not image_result:

                    await send_text(
                        sender_number,
                        "🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption).."
                    )

                    return {"status": "failed"}

                drive_link = await asyncio.to_thread(
                    upload_file_to_drive,
                    image_result,
                    "image/png"
                )

                user_states[sender_number] = {
                    "step": "waiting_prompt"
                }

                await send_text(
                    sender_number,
                    f"✅ Gambar berhasil dibuat\n\n{drive_link}"
                )

                return {"status": "image_done"}

            # ================= VIDEO =================

            if incoming_msg == "2":

                await send_text(
                    sender_number,
                    "🎬 Sedang membuat video..."
                )

                video_result = await ai_services.generate_video(prompt)

                if not video_result:

                    await send_text(
                        sender_number,
                        "🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption)."
                    )

                    return {"status": "failed"}

                drive_link = await asyncio.to_thread(
                    upload_file_to_drive,
                    video_result,
                    "video/mp4"
                )

                user_states[sender_number] = {
                    "step": "waiting_prompt"
                }

                await send_text(
                    sender_number,
                    f"✅ Video berhasil dibuat\n\n{drive_link}"
                )

                return {"status": "video_done"}

            # ================= GAMBAR + CAPTION =================

            if incoming_msg == "3":

                await send_text(
                    sender_number,
                    "🎨 Membuat gambar dan caption..."
                )

                result = await ai_services.generate_image_with_caption(
                    prompt
                )

                if not result:

                    await send_text(
                        sender_number,
                        "🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption)."
                    )

                    return {"status": "failed"}

                drive_link = await asyncio.to_thread(
                    upload_file_to_drive,
                    result["image"],
                    "image/png"
                )

                user_states[sender_number] = {
                    "step": "waiting_caption_revision",
                    "original_prompt": prompt,
                    "last_caption": result["caption"]
                }

                await send_text(
                    sender_number,
                    f"📷 {drive_link}\n\n✍️ {result['caption']}"
                )

                return {"status": "image_caption_done"}

            # ================= VIDEO + CAPTION =================

            if incoming_msg == "4":

                await send_text(
                    sender_number,
                    "🎬 Membuat video dan caption..."
                )

                result = await ai_services.generate_video_with_caption(
                    prompt
                )

                if not result:

                    await send_text(
                        sender_number,
                        "🚧 Fitur ini sedang dalam pengembangan.\n\nSilakan gunakan menu 5 (Caption)."
                    )

                    return {"status": "failed"}

                drive_link = await asyncio.to_thread(
                    upload_file_to_drive,
                    result["video"],
                    "video/mp4"
                )

                user_states[sender_number] = {
                    "step": "waiting_caption_revision",
                    "original_prompt": prompt,
                    "last_caption": result["caption"]
                }

                await send_text(
                    sender_number,
                    f"🎥 {drive_link}\n\n✍️ {result['caption']}"
                )

                return {"status": "video_caption_done"}

        # ================= TEST =================
        if incoming_msg.lower() == "test":
            await send_text(sender_number, "Halo juga 👋")
            return {"status": "ok"}
        
    except Exception as e:
        print("\nWEBHOOK ERROR:", e)
        return {
            "status": "error",
            "message": str(e)
        }
    