import os
import asyncio
import logging
import mimetypes
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "123456"))
API_HASH = os.getenv("API_HASH", "your_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token")
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://your-app.onrender.com")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://your-netlify-site.netlify.app")

PORT = int(os.getenv("PORT", "8080"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client("StreamBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
routes = web.RouteTableDef()

@routes.get("/")
async def index(request):
    return web.Response(text="Bot is Running... ✅")

@routes.get("/stream/{chat_id}/{message_id}")
async def stream_handler(request):
    try:
        chat_id = int(request.match_info['chat_id'])
        message_id = int(request.match_info['message_id'])
        
        # Telegram se message fetch karein
        message = await app.get_messages(chat_id, message_id)
        if not message or not (message.video or message.document or message.audio):
            return web.Response(status=404, text="File Not Found")

        media = message.video or message.document or message.audio
        file_size = media.file_size
        mime_type = media.mime_type or mimetypes.guess_type(media.file_name)[0] or "video/mp4"
        
        # Range Header handle karna (Seeking ke liye zaruri hai)
        range_header = request.headers.get("Range")
        start = 0
        end = file_size - 1

        if range_header:
            # Format: bytes=start-end
            ranges = range_header.replace("bytes=", "").split("-")
            start = int(ranges[0])
            if ranges[1]:
                end = int(ranges[1])

        payload_size = end - start + 1

        # Response headers create karein
        headers = {
            "Content-Type": mime_type,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(payload_size),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Content-Disposition": f'inline; filename="{media.file_name}"',
        }

        # Pyrogram stream_media generator ka use karke chunk-by-chunk data bhejna
        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        await response.prepare(request)

        async for chunk in app.stream_media(message, offset=start, limit=payload_size):
            await response.write(chunk)

        return response

    except Exception as e:
        logger.error(f"Streaming Error: {e}")
        return web.Response(status=500, text="Internal Server Error")

# --- BOT COMMANDS ---
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 Hello! Send me a video to get the streaming link.")

@app.on_message(filters.private & (filters.video | filters.document | filters.audio))
async def media_handler(client, message):
    media = message.video or message.document or message.audio
    # URL safe file name
    import urllib.parse
    safe_name = urllib.parse.quote(getattr(media, "file_name", "video.mp4"))
    
    # Links
    stream_link = f"{PUBLIC_URL}/stream/{message.chat.id}/{message.id}"
    play_link = f"{WEB_APP_URL}/?src={stream_link}&name={safe_name}"

    text = (
        f"✅ **Fast Stream Link Ready!**\n\n"
        f"📂 **File:** `{media.file_name}`\n"
        f"🔗 **Direct Link:** `{stream_link}`"
    )
    
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Watch Online", url=play_link)]])
    await message.reply_text(text, reply_markup=btn)

async def start_services():
    server = web.Application()
    server.add_routes(routes)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await app.start()
    print("✅ Bot & Stream Server Started!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(start_services())
