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
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://apki-website.netlify.app")

# ⚠️ IMPORTANT: Yaha apna Render ka link dalein (Bina last slash ke)
# Example: "https://my-app.onrender.com"
MY_RENDER_URL = "https://truestream-1.onrender.com" 

PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
app = Client("StreamBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=10)

# --- WEB SERVER ---
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.Response(text="✅ Server Online")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        try:
            message = await app.get_messages(chat_id, message_id)
            media = message.video or message.document or message.audio
            if not media: raise Exception
        except:
            return web.Response(status=404, text="File Not Found")

        file_size = media.file_size
        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # Range Header Logic
        range_header = request.headers.get("Range", 0)
        from_bytes, until_bytes = 0, file_size - 1
        if range_header:
            try:
                from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
                from_bytes = int(from_bytes)
                until_bytes = int(until_bytes) if until_bytes else file_size - 1
            except: pass
        
        length = until_bytes - from_bytes + 1
        
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(length),
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*", # CORS Fix
        }

        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        # 🚀 Faster Streaming Logic (64KB Chunks for fast start)
        chunk_size = 64 * 1024 
        
        try:
            async for chunk in app.download_media(
                message, offset=from_bytes, limit=length, in_memory=True, chunk_size=chunk_size
            ):
                await response.write(chunk)
        except:
            pass
            
        return response

    except Exception as e:
        logger.error(f"Stream Error: {e}")
        return web.Response(status=500)

# --- COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 Video bhejo!")

@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(client, message):
    try:
        media = message.video or message.document
        fname = getattr(media, "file_name", "Video.mp4") or "Video.mp4"
        
        # 🔗 Link Generation (Ab ye Localhost nahi hoga)
        stream_link = f"{MY_RENDER_URL}/stream/{message.chat.id}/{message.id}"
        
        safe_name = urllib.parse.quote(fname)
        web_link = f"{WEB_APP_URL}/?src={stream_link}&name={safe_name}"

        await message.reply_text(
            f"✅ **Link Ready!**\n📂 `{fname}`\n\n👇 **Watch Now:**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Play Video", url=web_link)]])
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
