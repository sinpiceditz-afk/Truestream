import os
import asyncio
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- VARIABLES (Render Environment se lega) ---
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Render URL automatic uthayega
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8080")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://apki-website.netlify.app")

PORT = int(os.environ.get("PORT", 8080))

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BOT SETUP ---
app = Client("RenderBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- WEB SERVER ---
routes = web.RouteTableDef()

def get_cors_headers(content_type="video/mp4", filename="video.mp4"):
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Range',
        'Content-Type': content_type,
        'Content-Disposition': f'inline; filename="{filename}"',
        'Accept-Ranges': 'bytes'
    }

@routes.get("/")
async def status_check(request):
    return web.Response(text="✅ Render Server is Running Fast!")

@routes.options("/stream/{chat_id}/{message_id}")
async def options_handler(request):
    return web.Response(headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, OPTIONS', 'Access-Control-Allow-Headers': '*'})

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        message = await app.get_messages(chat_id, message_id)
        media = message.video or message.document or message.audio
        
        if not media: return web.Response(status=404, text="File Not Found")

        file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # Stream directly to response
        file_stream = await app.download_media(message, in_memory=True)
        return web.Response(body=file_stream.getbuffer(), headers=get_cors_headers(mime_type, file_name))

    except Exception as e:
        return web.Response(status=500, text=f"Error: {e}")

# --- BOT COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("Render Bot Active! Send Video.")

@app.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    try:
        chat_id = message.chat.id
        msg_id = message.id
        media = message.video or message.document or message.audio
        fname = getattr(media, "file_name", "Video")

        # Dynamic Links
        stream_link = f"{RENDER_EXTERNAL_URL}/stream/{chat_id}/{msg_id}"
        safe_filename = urllib.parse.quote(fname)
        web_app_link = f"{WEB_APP_URL}/?src={stream_link}&name={safe_filename}"

        await message.reply_text(
            f"✅ **File on Fast Server!**\n📂 `{fname}`\n\n👇 **Watch Online:**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Play Video", url=web_app_link)]])
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