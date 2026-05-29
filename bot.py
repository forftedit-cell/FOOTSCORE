import os
import asyncio
import logging
from datetime import datetime, timedelta
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
API_BASE = "https://v3.football.api-sports.io"

HEADERS = {
    "x-apisports-key": FOOTBALL_API_KEY
}

# Top ligalar ID lari
TOP_LEAGUES = {
    39: "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
    140: "🇪🇸 La Liga",
    135: "🇮🇹 Serie A",
    78: "🇩🇪 Bundesliga",
    61: "🇫🇷 Ligue 1",
    2: "⭐ Champions League",
    3: "🏆 Europa League",
    848: "🏆 Conference League",
}

SEASON = 2024

# ============================================================
# API funksiyalari
# ============================================================

async def api_get(endpoint: str, params: dict) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE}/{endpoint}",
            headers=HEADERS,
            params=params
        ) as resp:
            return await resp.json()

async def get_fixtures(date_str: str) -> list:
    data = await api_get("fixtures", {"date": date_str, "season": SEASON})
    return data.get("response", [])

async def get_live_fixtures() -> list:
    data = await api_get("fixtures", {"live": "all"})
    return data.get("response", [])

async def search_team(name: str) -> list:
    data = await api_get("teams", {"search": name})
    return data.get("response", [])[:5]

async def get_team_fixture_today(team_id: int) -> list:
    today = datetime.now().strftime("%Y-%m-%d")
    data = await api_get("fixtures", {"team": team_id, "date": today, "season": SEASON})
    return data.get("response", [])

# ============================================================
# Formatlash funksiyalari
# ============================================================

def format_fixture(f: dict) -> str:
    home = f["teams"]["home"]["name"]
    away = f["teams"]["away"]["name"]
    home_score = f["goals"]["home"]
    away_score = f["goals"]["away"]
    status = f["fixture"]["status"]["short"]
    elapsed = f["fixture"]["status"]["elapsed"]
    league = f["league"]["name"]

    if status in ("FT", "AET", "PEN"):
        time_str = "✅ Tugadi"
        score = f"{home_score} : {away_score}"
    elif status in ("1H", "2H", "HT", "ET", "BT", "P"):
        time_str = f"🔴 {elapsed}'"
        score = f"{home_score} : {away_score}"
    elif status == "NS":
        kick_off = f["fixture"]["date"]
        dt = datetime.fromisoformat(kick_off.replace("Z", "+00:00"))
        time_str = f"🕐 {dt.strftime('%H:%M')}"
        score = "vs"
    else:
        time_str = status
        score = "vs"

    home_bold = f"*{home}*" if (home_score or 0) > (away_score or 0) else home
    away_bold = f"*{away}*" if (away_score or 0) > (home_score or 0) else away

    return f"{time_str}  {home_bold} {score} {away_bold}\n〔{league}〕"

def group_by_league(fixtures: list) -> dict:
    grouped = {}
    for f in fixtures:
        league_id = f["league"]["id"]
        league_name = f["league"]["name"]
        key = (league_id, league_name)
        grouped.setdefault(key, []).append(f)
    return grouped

def build_fixtures_message(fixtures: list, title: str) -> str:
    if not fixtures:
        return f"*{title}*\n\nO'yinlar topilmadi."

    # Avval top ligalarni ko'rsat, keyin qolganlarini
    grouped = group_by_league(fixtures)
    lines = [f"*{title}*\n"]

    # Top ligalar birinchi
    for league_id, league_label in TOP_LEAGUES.items():
        for (lid, lname), matches in grouped.items():
            if lid == league_id:
                lines.append(f"\n{league_label}")
                lines.append("─" * 28)
                for m in matches:
                    lines.append(format_fixture(m))
                break

    # Qolgan ligalar
    top_ids = set(TOP_LEAGUES.keys())
    for (lid, lname), matches in grouped.items():
        if lid not in top_ids:
            lines.append(f"\n🏆 {lname}")
            lines.append("─" * 28)
            for m in matches:
                lines.append(format_fixture(m))

    return "\n".join(lines)

# ============================================================
# Asosiy menyu
# ============================================================

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Bugungi o'yinlar", callback_data="today"),
            InlineKeyboardButton("🔴 Jonli", callback_data="live"),
        ],
        [
            InlineKeyboardButton("⏮ Kechagi", callback_data="yesterday"),
            InlineKeyboardButton("⏭ Ertangi", callback_data="tomorrow"),
        ],
        [
            InlineKeyboardButton("📆 Haftalik jadval", callback_data="week"),
        ],
        [
            InlineKeyboardButton("⭐ Mening klubim", callback_data="my_club"),
            InlineKeyboardButton("🔔 Bildirishnomalar", callback_data="notifications"),
        ],
    ])

# ============================================================
# Handlers
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚽ *FutScore Botga xush kelibsiz!*\n\n"
        "Bu bot orqali:\n"
        "• Barcha ligalar natijalarini ko'ring\n"
        "• Jonli o'yinlarni kuzating\n"
        "• Sevimli klubingizni tanlang\n"
        "• Gol urish bildirishnomalarini oling\n\n"
        "Quyidagi menyudan tanlang 👇"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Asosiy menyu*",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "today":
        await show_fixtures_for_date(query, datetime.now().strftime("%Y-%m-%d"), "📅 Bugungi o'yinlar")

    elif data == "yesterday":
        d = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        await show_fixtures_for_date(query, d, "⏮ Kechagi o'yinlar")

    elif data == "tomorrow":
        d = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        await show_fixtures_for_date(query, d, "⏭ Ertangi o'yinlar")

    elif data == "live":
        await query.edit_message_text("⏳ Jonli o'yinlar yuklanmoqda...", parse_mode="Markdown")
        fixtures = await get_live_fixtures()
        msg = build_fixtures_message(fixtures, "🔴 Jonli o'yinlar")
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu"), InlineKeyboardButton("🔄 Yangilash", callback_data="live")]])
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_kb)

    elif data == "week":
        await show_week(query)

    elif data == "my_club":
        await query.edit_message_text(
            "⭐ *Sevimli klubingizni kiriting*\n\nMasalan: `Arsenal`, `Barcelona`, `CSKA`\n\nFaqat klub nomini yozing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]])
        )
        context.user_data["awaiting_club"] = True

    elif data == "notifications":
        user_id = query.from_user.id
        club = context.bot_data.get("subscriptions", {}).get(str(user_id))
        if club:
            text = f"🔔 *Bildirishnomalar*\n\nSiz hozir *{club['name']}* klubiga obuna bo'lgansiz.\n\nGol urganida sizga xabar keladi! ✅"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Obunani bekor qilish", callback_data="unsubscribe")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]
            ])
        else:
            text = "🔔 *Bildirishnomalar*\n\nSiz hech qanday klubga obuna bo'lmagansiz.\n\nAvval ⭐ Mening klubim bo'limidan klub tanlang."
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Klub tanlash", callback_data="my_club")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]
            ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    elif data == "unsubscribe":
        user_id = str(query.from_user.id)
        if "subscriptions" in context.bot_data:
            context.bot_data["subscriptions"].pop(user_id, None)
        await query.edit_message_text(
            "✅ Obuna bekor qilindi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]])
        )

    elif data == "back_menu":
        await query.edit_message_text(
            "📋 *Asosiy menyu*",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )

    elif data.startswith("select_club:"):
        team_id = int(data.split(":")[1])
        team_name = data.split(":")[2]
        user_id = str(query.from_user.id)
        if "subscriptions" not in context.bot_data:
            context.bot_data["subscriptions"] = {}
        context.bot_data["subscriptions"][user_id] = {
            "id": team_id,
            "name": team_name,
            "last_goals": {}
        }
        await query.edit_message_text(
            f"✅ *{team_name}* klubiga muvaffaqiyatli obuna bo'ldingiz!\n\n"
            f"🔔 Endi ular gol urganida sizga bildirishnoma keladi.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="back_menu")]])
        )

    elif data.startswith("day:"):
        date_str = data.split(":")[1]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        label = dt.strftime("%d.%m.%Y")
        await show_fixtures_for_date(query, date_str, f"📅 {label} o'yinlari")

async def show_fixtures_for_date(query, date_str: str, title: str):
    await query.edit_message_text(f"⏳ {title} yuklanmoqda...", parse_mode="Markdown")
    fixtures = await get_fixtures(date_str)
    msg = build_fixtures_message(fixtures, title)
    # Telegram 4096 belgi chegarasi
    if len(msg) > 4000:
        msg = msg[:4000] + "\n\n_...va boshqa o'yinlar_"
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu"), InlineKeyboardButton("🔄 Yangilash", callback_data=f"day:{date_str}")]])
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_kb)

async def show_week(query):
    await query.edit_message_text("⏳ Haftalik jadval yuklanmoqda...", parse_mode="Markdown")
    today = datetime.now()
    buttons = []
    for i in range(-2, 6):
        d = today + timedelta(days=i)
        label = d.strftime("%a %d.%m")
        if i == 0:
            label = "📅 " + label + " (bugun)"
        elif i == -1:
            label = "⏮ " + label
        elif i == 1:
            label = "⏭ " + label
        buttons.append(InlineKeyboardButton(label, callback_data=f"day:{d.strftime('%Y-%m-%d')}"))

    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])

    await query.edit_message_text(
        "📆 *Haftalik jadval*\nKun tanlang:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows)
    )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_club"):
        await update.message.reply_text(
            "Menyu uchun /start yoki /menu buyrug'ini ishlating.",
            reply_markup=main_menu_keyboard()
        )
        return

    context.user_data["awaiting_club"] = False
    query_text = update.message.text.strip()
    msg = await update.message.reply_text(f"🔍 *{query_text}* qidirilmoqda...", parse_mode="Markdown")

    teams = await search_team(query_text)
    if not teams:
        await msg.edit_text("❌ Klub topilmadi. Boshqa nom bilan urinib ko'ring.")
        return

    buttons = []
    for t in teams:
        name = t["team"]["name"]
        tid = t["team"]["id"]
        country = t["team"].get("country", "")
        buttons.append([InlineKeyboardButton(f"{name} ({country})", callback_data=f"select_club:{tid}:{name}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])

    await msg.edit_text(
        "🔍 *Topilgan klublar:*\nO'zingiznikini tanlang:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ============================================================
# Gol bildirishnoma (background task)
# ============================================================

async def check_goals(context: ContextTypes.DEFAULT_TYPE):
    subscriptions = context.bot_data.get("subscriptions", {})
    if not subscriptions:
        return

    live = await get_live_fixtures()

    for user_id, sub in subscriptions.items():
        team_id = sub["id"]
        team_name = sub["name"]
        last_goals = sub.get("last_goals", {})

        for fixture in live:
            home = fixture["teams"]["home"]
            away = fixture["teams"]["away"]

            if home["id"] != team_id and away["id"] != team_id:
                continue

            fixture_id = str(fixture["fixture"]["id"])
            home_goals = fixture["goals"]["home"] or 0
            away_goals = fixture["goals"]["away"] or 0
            elapsed = fixture["fixture"]["status"]["elapsed"] or 0

            prev_home = last_goals.get(fixture_id, {}).get("home", 0)
            prev_away = last_goals.get(fixture_id, {}).get("away", 0)

            home_name = home["name"]
            away_name = away["name"]

            # Yangi gol bormi?
            if home["id"] == team_id and home_goals > prev_home:
                for _ in range(home_goals - prev_home):
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚽ *GOL! {team_name}*\n\n"
                            f"🏟 {home_name} *{home_goals}* : {away_goals} {away_name}\n"
                            f"⏱ {elapsed}' daqiqa"
                        ),
                        parse_mode="Markdown"
                    )

            elif away["id"] == team_id and away_goals > prev_away:
                for _ in range(away_goals - prev_away):
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚽ *GOL! {team_name}*\n\n"
                            f"🏟 {home_name} {home_goals} : *{away_goals}* {away_name}\n"
                            f"⏱ {elapsed}' daqiqa"
                        ),
                        parse_mode="Markdown"
                    )

            sub["last_goals"][fixture_id] = {"home": home_goals, "away": away_goals}

# ============================================================
# Main
# ============================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Har 60 soniyada gol tekshirish
    app.job_queue.run_repeating(check_goals, interval=60, first=10)

    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
