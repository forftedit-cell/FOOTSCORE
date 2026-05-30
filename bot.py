import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN")

# Spotify init
try:
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))
except:
    sp = None

# ============================================================
# YouTube yuklab olish
# ============================================================

async def download_youtube(query: str, audio_only: bool = True) -> dict:
    ydl_opts = {
        'format': 'worstvideo+worstaudio/worst/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'default_search': 'ytsearch1',
        'outtmpl': '/tmp/%(title)s.%(ext)s',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            if audio_only:
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'url': info.get('webpage_url', ''),
                'filename': filename,
                'success': True
            }
    except Exception as e:
        logger.error(f"YouTube error: {e}")
        return {'success': False, 'error': str(e)}

async def search_youtube(query: str, limit: int = 5) -> list:
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'default_search': f'ytsearch{limit}',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            results = []
            for entry in info.get('entries', []):
                results.append({
                    'title': entry.get('title', 'Unknown'),
                    'duration': entry.get('duration', 0),
                    'url': entry.get('url', ''),
                    'id': entry.get('id', ''),
                })
            return results
    except Exception as e:
        logger.error(f"YouTube search error: {e}")
        return []

# ============================================================
# Spotify qidirish
# ============================================================

def search_spotify(query: str, limit: int = 5) -> list:
    if not sp:
        return []
    try:
        results = sp.search(q=query, limit=limit, type='track')
        tracks = []
        for item in results['tracks']['items']:
            tracks.append({
                'title': item['name'],
                'artist': ', '.join([a['name'] for a in item['artists']]),
                'album': item['album']['name'],
                'duration': item['duration_ms'] // 1000,
                'preview_url': item.get('preview_url'),
                'spotify_url': item['external_urls']['spotify'],
                'image': item['album']['images'][0]['url'] if item['album']['images'] else None,
            })
        return tracks
    except Exception as e:
        logger.error(f"Spotify error: {e}")
        return []

def search_spotify_artist(artist: str) -> dict:
    if not sp:
        return {}
    try:
        results = sp.search(q=f"artist:{artist}", type='artist', limit=1)
        items = results['artists']['items']
        if not items:
            return {}
        a = items[0]
        top_tracks = sp.artist_top_tracks(a['id'])['tracks'][:5]
        return {
            'name': a['name'],
            'genres': ', '.join(a['genres'][:3]) if a['genres'] else 'Noma\'lum',
            'followers': a['followers']['total'],
            'image': a['images'][0]['url'] if a['images'] else None,
            'url': a['external_urls']['spotify'],
            'top_tracks': [{'title': t['name'], 'album': t['album']['name']} for t in top_tracks],
        }
    except Exception as e:
        logger.error(f"Spotify artist error: {e}")
        return {}

# ============================================================
# Lyrics (Genius)
# ============================================================

def get_lyrics(song: str, artist: str = '') -> str:
    if not GENIUS_TOKEN:
        return None
    try:
        query = f"{song} {artist}".strip()
        headers = {'Authorization': f'Bearer {GENIUS_TOKEN}'}
        resp = requests.get(
            'https://api.genius.com/search',
            headers=headers,
            params={'q': query}
        )
        hits = resp.json()['response']['hits']
        if not hits:
            return None
        url = hits[0]['result']['url']
        return url
    except Exception as e:
        logger.error(f"Genius error: {e}")
        return None

# ============================================================
# Format funksiyalari
# ============================================================

def fmt_duration(seconds: int) -> str:
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

# ============================================================
# Menyu
# ============================================================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Qo'shiq yuklab olish", callback_data="download"),
            InlineKeyboardButton("🔍 Qidirish", callback_data="search"),
        ],
        [
            InlineKeyboardButton("🎤 Artist ma'lumoti", callback_data="artist"),
            InlineKeyboardButton("📝 Lyrics (so'zlar)", callback_data="lyrics"),
        ],
        [
            InlineKeyboardButton("▶️ YouTube", callback_data="yt_search"),
            InlineKeyboardButton("🟢 Spotify", callback_data="sp_search"),
        ],
    ])

# ============================================================
# Handlers
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *Universal Music Bot*\n\n"
        "Men sizga qo'shiq yuklab beraman!\n\n"
        "• YouTube, Spotify, SoundCloud dan\n"
        "• Artist ma'lumotlari\n"
        "• Qo'shiq so'zlari (Lyrics)\n\n"
        "Shunchaki qo'shiq nomini yozing yoki menyu tanlang 👇",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    back = [[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]

    if data == "back_menu":
        await query.edit_message_text("🎵 Asosiy menyu:", reply_markup=main_menu())

    elif data == "download":
        await query.edit_message_text(
            "🎵 *Qo'shiq yuklab olish*\n\nQo'shiq nomini yozing:\nMasalan: `Adele Hello` yoki `Michael Jackson Thriller`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back)
        )
        context.user_data["mode"] = "download"

    elif data == "search":
        await query.edit_message_text(
            "🔍 *Qidirish*\n\nQo'shiq yoki artist nomini yozing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back)
        )
        context.user_data["mode"] = "search"

    elif data == "artist":
        await query.edit_message_text(
            "🎤 *Artist ma'lumoti*\n\nArtist nomini yozing:\nMasalan: `The Weeknd`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back)
        )
        context.user_data["mode"] = "artist"

    elif data == "lyrics":
        await query.edit_message_text(
            "📝 *Lyrics*\n\nQo'shiq nomini yozing:\nMasalan: `Bohemian Rhapsody Queen`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back)
        )
        context.user_data["mode"] = "lyrics"

    elif data == "yt_search":
        await query.edit_message_text(
            "▶️ *YouTube qidirish*\n\nQo'shiq nomini yozing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back)
        )
        context.user_data["mode"] = "yt_search"

    elif data == "sp_search":
        await query.edit_message_text(
            "🟢 *Spotify qidirish*\n\nQo'shiq nomini yozing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back)
        )
        context.user_data["mode"] = "sp_search"

    elif data.startswith("dl_yt:"):
        video_id = data.split(":", 1)[1]
        await query.edit_message_text("⏳ Yuklanmoqda... Bu 1-2 daqiqa olishi mumkin")
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _download_yt_sync(video_id)
        )
        if result['success']:
            try:
                with open(result['filename'], 'rb') as f:
                    await query.message.reply_audio(
                        audio=f,
                        title=result['title'],
                        caption=f"🎵 {result['title']}\n⏱ {fmt_duration(result['duration'])}",
                    )
                os.remove(result['filename'])
            except Exception as e:
                await query.message.reply_text(f"❌ Yuklashda xato: {e}")
        else:
            await query.message.reply_text(f"❌ Xato: {result.get('error', 'Noma\'lum')}")
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(back))

def _download_yt_sync(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': '/tmp/%(id)s.%(ext)s',
        'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
        'socket_timeout': 30,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return {'success': True, 'filename': filename, 'title': info.get('title'), 'duration': info.get('duration', 0)}
    except Exception as e:
        logger.error(f"Download error: {e}")
        return {'success': False, 'error': str(e)}

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.get("mode", "download")

    if mode == "download":
        msg = await update.message.reply_text(f"🔍 YouTube da qidirilmoqda: *{text}*...", parse_mode="Markdown")
        results = await search_youtube(text, limit=5)
        if not results:
            await msg.edit_text("❌ Topilmadi.")
            return
        buttons = []
        for r in results:
            dur = fmt_duration(r.get('duration', 0))
            label = f"🎵 {r['title'][:40]} [{dur}]"
            buttons.append([InlineKeyboardButton(label, callback_data=f"dl_yt:{r['id']}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
        await msg.edit_text(
            f"🔍 *'{text}'* natijalari:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif mode == "yt_search":
        context.user_data["mode"] = "download"
        msg = await update.message.reply_text(f"🔍 YouTube da qidirilmoqda...", parse_mode="Markdown")
        results = await search_youtube(text, limit=5)
        if not results:
            await msg.edit_text("❌ Topilmadi.")
            return
        buttons = []
        for r in results:
            dur = fmt_duration(r.get('duration', 0))
            buttons.append([InlineKeyboardButton(f"🎵 {r['title'][:40]} [{dur}]", callback_data=f"dl_yt:{r['id']}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
        await msg.edit_text(f"▶️ *YouTube natijalari:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif mode == "sp_search":
        context.user_data["mode"] = None
        msg = await update.message.reply_text("🟢 Spotify da qidirilmoqda...")
        tracks = search_spotify(text)
        if not tracks:
            await msg.edit_text("❌ Spotify da topilmadi.")
            return
        lines = [f"🟢 *Spotify natijalari: '{text}'*\n"]
        for i, t in enumerate(tracks, 1):
            lines.append(f"{i}. *{t['title']}* — {t['artist']}")
            lines.append(f"   💿 {t['album']} | ⏱ {fmt_duration(t['duration'])}")
            if t.get('spotify_url'):
                lines.append(f"   🔗 [Spotify da ochish]({t['spotify_url']})")
            lines.append("")
        await msg.edit_text("\n".join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]))

    elif mode == "artist":
        context.user_data["mode"] = None
        msg = await update.message.reply_text(f"🎤 *{text}* haqida ma'lumot qidirilmoqda...")
        artist = search_spotify_artist(text)
        if not artist:
            # YouTube dan qidirish
            results = await search_youtube(f"{text} official", limit=3)
            if results:
                buttons = [[InlineKeyboardButton(f"🎵 {r['title'][:40]}", callback_data=f"dl_yt:{r['id']}")] for r in results]
                buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
                await msg.edit_text(f"🎤 *{text}* — YouTube natijalari:", parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await msg.edit_text("❌ Artist topilmadi.")
            return
        lines = [
            f"🎤 *{artist['name']}*\n",
            f"🎭 Janr: {artist['genres']}",
            f"👥 Obunachilar: {artist['followers']:,}",
            f"🔗 [Spotify da ko'rish]({artist['url']})\n",
            f"🔥 *Top qo'shiqlar:*"
        ]
        for i, t in enumerate(artist['top_tracks'], 1):
            lines.append(f"  {i}. {t['title']} — {t['album']}")
        await msg.edit_text("\n".join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]))

    elif mode == "lyrics":
        context.user_data["mode"] = None
        msg = await update.message.reply_text(f"📝 *{text}* so'zlari qidirilmoqda...")
        url = get_lyrics(text)
        if url:
            await msg.edit_text(
                f"📝 *{text}* so'zlari:\n\n[Genius da ko'rish]({url})",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]))
        else:
            # YouTube qidirib ko'ramiz
            results = await search_youtube(f"{text} lyrics", limit=3)
            if results:
                buttons = [[InlineKeyboardButton(f"▶️ {r['title'][:40]}", callback_data=f"dl_yt:{r['id']}")] for r in results]
                buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
                await msg.edit_text(f"📝 Lyrics topilmadi. YouTube dan:\n", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await msg.edit_text("❌ So'zlar topilmadi.")

    elif mode == "search":
        context.user_data["mode"] = None
        msg = await update.message.reply_text(f"🔍 Qidirilmoqda: *{text}*...")
        yt_results = await search_youtube(text, limit=3)
        sp_results = search_spotify(text, limit=3)
        lines = [f"🔍 *'{text}'* natijalari:\n"]
        buttons = []
        if yt_results:
            lines.append("▶️ *YouTube:*")
            for r in yt_results:
                buttons.append([InlineKeyboardButton(f"▶️ {r['title'][:40]}", callback_data=f"dl_yt:{r['id']}")])
        if sp_results:
            lines.append("\n🟢 *Spotify:*")
            for t in sp_results:
                lines.append(f"• *{t['title']}* — {t['artist']}")
                if t.get('spotify_url'):
                    lines.append(f"  [Ochish]({t['spotify_url']})")
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
        await msg.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    else:
        # Default: YouTube dan qidirish
        msg = await update.message.reply_text(f"🔍 *{text}* qidirilmoqda...", parse_mode="Markdown")
        results = await search_youtube(text, limit=5)
        if not results:
            await msg.edit_text("❌ Topilmadi.")
            return
        buttons = []
        for r in results:
            dur = fmt_duration(r.get('duration', 0))
            buttons.append([InlineKeyboardButton(f"🎵 {r['title'][:40]} [{dur}]", callback_data=f"dl_yt:{r['id']}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
        await msg.edit_text(f"🎵 *Natijalar:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi!")
        return
    logger.info("Music bot ishga tushmoqda...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("Music bot tayyor!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
