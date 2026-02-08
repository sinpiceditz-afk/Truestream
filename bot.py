import os
import asyncio
import logging
import math
import time
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- CONFIGURATION (Render ke Environment Variables se lega) ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Render URL (Automatic Detect karega)
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8080")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://apki-website.netlify.app")

PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
# Workers bada diye taki multiple log ek sath dekh sakein
app = Client("SpeedBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=10, max_concurrent_transmissions=10)

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="🚀 High Speed Direct Streamer Running!")

# --- THE MAGIC STREAMING LOGIC ---
@routes.get("/stream/{chat_id}/{message_id}")
async def media_streamer(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        # 1. Telegram se File ki jankari lena
        message = await app.get_messages(chat_id, message_id)
        media = message.video or message.document or message.audio
        
        if not media: return web.Response(status=404, text="File Not Found")

        file_size = media.file_size
        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # 2. RANGE HEADER HANDLE KARNA (Fast Play ke liye sabse zaruri)
        # Browser batata hai "Muze video ka kon sa hissa chahiye"
        range_header = request.headers.get("Range", 0)
        
        from_bytes, until_bytes = 0, file_size - 1
        if range_header:
            try:
                from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
                from_bytes = int(from_bytes)
                until_bytes = int(until_bytes) if until_bytes else file_size - 1
            except:
                pass

        # 3. Content Length calculate karna
        content_length = until_bytes - from_bytes + 1
        
        # 4. Headers Set karna
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(content_length),
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        }

        # 5. Response Shuru (Status 206 Partial Content)
        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        # 6. STREAMING (Bina Download kiye pipe karna)
        # Hum 1MB ke tukdo (chunks) mein bhejenge
        chunk_size = 1024 * 1024 # 1 MB chunks
        
        async for chunk in app.download_media(
            message,
            offset=from_bytes,
            limit=content_length,
            in_memory=True,
            chunk_size=chunk_size
        ):
            try:
                await response.write(chunk)
            except:
                break # Agar user ne video band kar diya to ruk jao

        return response

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500, text="Internal Server Error")

# --- BOT COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 **Fast Stream Bot!**\nSend video to get instant play link.")

@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    try:
        # File Info
        media = message.video or message.document
        fname = getattr(media, "file_name", "Video") or "Video"
        
        # Link Generation
        stream_link = f"{RENDER_EXTERNAL_URL}/stream/{message.chat.id}/{message.id}"
        
        # Web App Link (Ads ke liye)
        safe_name = urllib.parse.quote(fname)
        web_app_link = f"{WEB_APP_URL}/?src={stream_link}&name={safe_name}"

        await message.reply_text(
            f"✅ **Fast Link Ready!**\n\n"
            f"📂 `{fname}`\n"
            f"🚀 **No Buffer Link:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch Online", url=web_app_link)]
            ])
        )
    except Exception as e:
        logger.error(e)

# --- RUNNER ---
async def start_services():
    app_runner = web.AppRunner(web.Application())
    app_runner.app.add_routes(routes)
    await app_runner.setup()
    site = web.TCPSite(app_runner, "0.0.0.0", PORT)
    await site.start()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
