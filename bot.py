import os
import asyncio
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Website Link
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://apki-website.netlify.app")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8080")

PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
# Workers badhaye hain taki multiple users dekh sakein
app = Client("StreamBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50, max_concurrent_transmissions=20)

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="🟢 Server is Online & Ready to Stream!")

# --- STREAMING LOGIC (The Fix) ---
@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        # 1. File Info Get Karna
        try:
            message = await app.get_messages(chat_id, message_id)
            media = message.video or message.document or message.audio
            if not media: raise Exception("No Media")
        except:
            return web.Response(status=404, text="File Not Found or Link Expired")

        file_size = media.file_size
        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # 2. RANGE HEADER (Browser ko tukdo mein video dena)
        range_header = request.headers.get("Range", 0)
        from_bytes, until_bytes = 0, file_size - 1
        
        if range_header:
            try:
                from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
                from_bytes = int(from_bytes)
                until_bytes = int(until_bytes) if until_bytes else file_size - 1
            except:
                pass

        content_length = until_bytes - from_bytes + 1
        
        # 3. HEADERS (Black Screen Fix)
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(content_length),
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",  # CORS FIX
            "Access-Control-Allow-Headers": "*"
        }

        # 4. START RESPONSE
        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        # 5. STREAMING LOOP (RAM Bachane ke liye)
        # Hum 1MB ka tukda download karenge aur turant bhej denge
        chunk_size = 1024 * 1024 # 1 MB
        
        try:
            async for chunk in app.download_media(
                message,
                offset=from_bytes,
                limit=content_length,
                in_memory=True, # Ye sirf 1 chunk memory me rakhega (Safe)
                chunk_size=chunk_size
            ):
                await response.write(chunk)
        except Exception as e:
            pass # Agar user ne video band kar diya to error ignore karo

        return response

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500, text="Server Error")

# --- BOT COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 **Ready!** Video bhejo.")

@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    try:
        media = message.video or message.document
        fname = getattr(media, "file_name", "Video.mp4") or "Video.mp4"
        
        # Stream Link
        stream_link = f"{RENDER_EXTERNAL_URL}/stream/{message.chat.id}/{message.id}"
        
        # Website Link (URL Encode ke saath)
        safe_name = urllib.parse.quote(fname)
        web_link = f"{WEB_APP_URL}/?src={stream_link}&name={safe_name}"

        await message.reply_text(
            f"✅ **Link Generated!**\n📂 `{fname}`\n👇 Watch Now:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch Online", url=web_link)]
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
