import os
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
ADMIN_ID = 6364081843

HEADERS = {"x-apisports-key": FOOTBALL_API_KEY}

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
WC_LEAGUE_ID = 1   # API-Football: FIFA World Cup
WC_SEASON = 2026

# ============================================================
# API
# ============================================================

async def api_get(endpoint: str, params: dict) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE}/{endpoint}", headers=HEADERS, params=params
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

async def get_team_last_fixtures(team_id: int) -> list:
    data = await api_get("fixtures", {"team": team_id, "last": 5, "season": SEASON})
    return data.get("response", [])

async def get_team_next_fixtures(team_id: int) -> list:
    data = await api_get("fixtures", {"team": team_id, "next": 10})
    return data.get("response", [])

async def get_wc_groups() -> dict:
    data = await api_get("standings", {"league": WC_LEAGUE_ID, "season": WC_SEASON})
    return data.get("response", [])

async def get_wc_fixtures(stage: str = None) -> list:
    params = {"league": WC_LEAGUE_ID, "season": WC_SEASON}
    if stage:
        params["round"] = stage
    data = await api_get("fixtures", params)
    return data.get("response", [])

async def search_fixtures_by_teams(team1_id: int, team2_id: int) -> list:
    data = await api_get("fixtures/headtohead", {"h2h": f"{team1_id}-{team2_id}", "last": 10})
    return data.get("response", [])

async def get_fixture_events(fixture_id: int) -> list:
    data = await api_get("fixtures/events", {"fixture": fixture_id})
    return data.get("response", [])

async def get_fixture_stats(fixture_id: int) -> list:
    data = await api_get("fixtures/statistics", {"fixture": fixture_id})
    return data.get("response", [])

# ============================================================
# Formatlash
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
        lid = f["league"]["id"]
        lname = f["league"]["name"]
        grouped.setdefault((lid, lname), []).append(f)
    return grouped

def build_fixtures_message(fixtures: list, title: str) -> str:
    if not fixtures:
        return f"*{title}*\n\nO'yinlar topilmadi."
    grouped = group_by_league(fixtures)
    lines = [f"*{title}*\n"]
    for league_id, league_label in TOP_LEAGUES.items():
        for (lid, lname), matches in grouped.items():
            if lid == league_id:
                lines.append(f"\n{league_label}")
                lines.append("─" * 28)
                for m in matches:
                    lines.append(format_fixture(m))
                break
    top_ids = set(TOP_LEAGUES.keys())
    for (lid, lname), matches in grouped.items():
        if lid not in top_ids:
            lines.append(f"\n🏆 {lname}")
            lines.append("─" * 28)
            for m in matches:
                lines.append(format_fixture(m))
    return "\n".join(lines)

def format_team_fixture_row(f: dict, team_id: int) -> str:
    home = f["teams"]["home"]
    away = f["teams"]["away"]
    hg = f["goals"]["home"] or 0
    ag = f["goals"]["away"] or 0
    status = f["fixture"]["status"]["short"]
    date = f["fixture"]["date"][:10]
    league = f["league"]["name"]

    if status in ("FT", "AET", "PEN"):
        # Natija: G/D/Y
        if home["id"] == team_id:
            if hg > ag:
                result = "🟢 G"
            elif hg == ag:
                result = "🟡 D"
            else:
                result = "🔴 Y"
            score_str = f"{hg}:{ag}"
            opp = away["name"]
            location = "Uy"
        else:
            if ag > hg:
                result = "🟢 G"
            elif ag == hg:
                result = "🟡 D"
            else:
                result = "🔴 Y"
            score_str = f"{hg}:{ag}"
            opp = home["name"]
            location = "Tashqari"
        return f"{result} {date} | {opp} {score_str} ({location})\n〔{league}〕"
    elif status == "NS":
        dt = datetime.fromisoformat(f["fixture"]["date"].replace("Z", "+00:00"))
        opp = away["name"] if home["id"] == team_id else home["name"]
        location = "Uy" if home["id"] == team_id else "Tashqari"
        return f"🕐 {dt.strftime('%d.%m %H:%M')} | {opp} ({location})\n〔{league}〕"
    else:
        opp = away["name"] if home["id"] == team_id else home["name"]
        return f"📅 {date} | {opp}\n〔{league}〕"

async def format_match_detail(fixture: dict) -> str:
    fid = fixture["fixture"]["id"]
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    home_score = fixture["goals"]["home"] or 0
    away_score = fixture["goals"]["away"] or 0
    league = fixture["league"]["name"]
    date_str = fixture["fixture"]["date"]
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

    lines = [
        f"📋 *{home} vs {away}*",
        f"🏆 {league}",
        f"📅 {dt.strftime('%d.%m.%Y %H:%M')}",
        f"⚽ Hisob: *{home_score} : {away_score}*",
        ""
    ]

    events = await get_fixture_events(fid)
    if events:
        lines.append("📝 *Voqealar:*")
        for e in events:
            etype = e.get("type", "")
            detail = e.get("detail", "")
            minute = e.get("time", {}).get("elapsed", "?")
            player = e.get("player", {}).get("name", "")
            team = e.get("team", {}).get("name", "")
            if etype == "Goal":
                if detail == "Own Goal":
                    lines.append(f"  ⚽ {minute}' *OG* — {player} ({team})")
                elif detail == "Penalty":
                    lines.append(f"  ⚽ {minute}' *Pen* — {player} ({team})")
                else:
                    lines.append(f"  ⚽ {minute}' — {player} ({team})")
            elif etype == "Card":
                if detail == "Yellow Card":
                    lines.append(f"  🟨 {minute}' — {player} ({team})")
                elif detail in ("Red Card", "Second Yellow card"):
                    lines.append(f"  🟥 {minute}' — {player} ({team})")

    stats = await get_fixture_stats(fid)
    if stats and len(stats) >= 2:
        lines.append("")
        lines.append("📊 *Statistika:*")
        home_stats = {s["type"]: s["value"] for s in stats[0].get("statistics", [])}
        away_stats = {s["type"]: s["value"] for s in stats[1].get("statistics", [])}
        show = [
            ("Ball Possession", "🔵 Top"),
            ("Total Shots", "🎯 Urinish"),
            ("Shots on Goal", "🥅 Darvozaga"),
            ("Corner Kicks", "🚩 Burchak"),
            ("Fouls", "🤼 Faul"),
            ("Yellow Cards", "🟨 Sariq"),
            ("Red Cards", "🟥 Qizil"),
        ]
        for key, label in show:
            hv = home_stats.get(key, 0) or 0
            av = away_stats.get(key, 0) or 0
            lines.append(f"  {label}: {hv} — {av}")

    return "\n".join(lines)

# ============================================================
# Menyu
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
        [InlineKeyboardButton("📆 Haftalik jadval", callback_data="week")],
        [
            InlineKeyboardButton("🔍 O'yin qidirish", callback_data="search_match"),
            InlineKeyboardButton("📋 Jamoa o'yinlari", callback_data="team_fixtures"),
        ],
        [
            InlineKeyboardButton("🌍 World Cup 2026", callback_data="wc2026"),
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
        "• Barcha ligalar natijalarini ko'ring\n"
        "• Jonli o'yinlarni kuzating\n"
        "• Istalgan o'yinni qidiring — gol, karta, statistika\n"
        "• Jamoa o'yinlari ro'yxati — oxirgi 5 + keyingi 10\n"
        "• Sevimli klubingizga obuna bo'ling\n\n"
        "👇 Menyudan tanlang"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 *Asosiy menyu*", parse_mode="Markdown", reply_markup=main_menu_keyboard())

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
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu"),
            InlineKeyboardButton("🔄 Yangilash", callback_data="live")
        ]])
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)

    elif data == "week":
        await show_week(query)

    elif data == "search_match":
        await query.edit_message_text(
            "🔍 *O'yin qidirish*\n\nIkki jamoa nomini yozing:\nMasalan: `Arsenal Chelsea`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]])
        )
        context.user_data["awaiting_match_search"] = True

    elif data == "team_fixtures":
        await query.edit_message_text(
            "📋 *Jamoa o'yinlari*\n\nJamoa nomini yozing:\nMasalan: `Arsenal`, `Barcelona`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]])
        )
        context.user_data["awaiting_team_fixtures"] = True

    elif data == "wc2026":
        await query.edit_message_text("⏳ World Cup 2026 yuklanmoqda...", parse_mode="Markdown")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Guruh bosqichi", callback_data="wc_stage:Group Stage")],
            [InlineKeyboardButton("⚔️ Round of 32", callback_data="wc_stage:Round of 32")],
            [InlineKeyboardButton("🏆 Round of 16", callback_data="wc_stage:Round of 16")],
            [InlineKeyboardButton("💥 Chorak final", callback_data="wc_stage:Quarter-finals")],
            [InlineKeyboardButton("🔥 Yarim final", callback_data="wc_stage:Semi-finals")],
            [InlineKeyboardButton("🥇 Final", callback_data="wc_stage:Final")],
            [InlineKeyboardButton("📊 Guruhlar jadvali", callback_data="wc_standings")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")],
        ])
        await query.edit_message_text(
            "🌍 *FIFA World Cup 2026*\n\n"
            "🗓 11 Iyun — 19 Iyul 2026\n"
            "🏟 AQSh · Kanada · Meksika\n"
            "⚽ 48 jamoa · 104 o\'yin\n\n"
            "Bo\'limni tanlang:",
            parse_mode="Markdown",
            reply_markup=kb
        )

    elif data.startswith("wc_stage:"):
        stage = data.split(":", 1)[1]
        await query.edit_message_text(f"⏳ {stage} o\'yinlari yuklanmoqda...", parse_mode="Markdown")
        fixtures = await get_wc_fixtures(stage)
        if not fixtures:
            await query.edit_message_text(
                f"⏳ *{stage}* o\'yinlari hali boshlanmagan yoki ma\'lumot yo\'q.\n\nWorld Cup 2026 — 11 Iyundan boshlanadi!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="wc2026")]])
            )
            return
        lines = [f"🌍 *World Cup 2026 — {stage}*\n"]
        for f in fixtures[:30]:
            home = f["teams"]["home"]["name"]
            away = f["teams"]["away"]["name"]
            status = f["fixture"]["status"]["short"]
            date_raw = f["fixture"]["date"]
            dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
            hg = f["goals"]["home"]
            ag = f["goals"]["away"]
            venue = f["fixture"].get("venue", {}).get("city", "")
            fid = f["fixture"]["id"]
            if status in ("FT", "AET", "PEN"):
                line = f"✅ {dt.strftime('%d.%m')} | *{home}* {hg}:{ag} *{away}* | {venue}"
            elif status in ("1H", "2H", "HT"):
                elapsed = f["fixture"]["status"]["elapsed"]
                line = f"🔴 {elapsed}\' | {home} {hg}:{ag} {away} | {venue}"
            else:
                line = f"🕐 {dt.strftime('%d.%m %H:%M')} | {home} vs {away} | {venue}"
            lines.append(line)
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n_...qisqartirildi_"
        await query.edit_message_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="wc2026")]]))

    elif data == "wc_standings":
        await query.edit_message_text("⏳ Guruhlar jadvali yuklanmoqda...", parse_mode="Markdown")
        standings = await get_wc_groups()
        if not standings:
            await query.edit_message_text(
                "⏳ Guruhlar jadvali hali mavjud emas.\nWorld Cup 2026 — 11 Iyundan boshlanadi!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="wc2026")]])
            )
            return
        lines = ["🌍 *World Cup 2026 — Guruhlar jadvali*\n"]
        for group in standings[:12]:
            group_name = group[0]["group"] if group else ""
            lines.append(f"\n*{group_name}*")
            lines.append("─" * 24)
            for team in group:
                t = team["team"]["name"]
                pts = team["points"]
                w = team["all"]["win"]
                d = team["all"]["draw"]
                l = team["all"]["lose"]
                gd = team["goalsDiff"]
                lines.append(f"  {t}: {pts}pts ({w}G {d}D {l}Y) GF:{gd:+d}")
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n_...qisqartirildi_"
        await query.edit_message_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="wc2026")]]))

    elif data == "my_club":
        await query.edit_message_text(
            "⭐ *Sevimli klubingizni kiriting*\n\nMasalan: `Arsenal`, `Barcelona`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]])
        )
        context.user_data["awaiting_club"] = True

    elif data == "notifications":
        user_id = query.from_user.id
        club = context.bot_data.get("subscriptions", {}).get(str(user_id))
        if club:
            text = f"🔔 *Bildirishnomalar*\n\n*{club['name']}* klubiga obuna bo'lgansiz ✅"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Obunani bekor qilish", callback_data="unsubscribe")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]
            ])
        else:
            text = "🔔 *Bildirishnomalar*\n\nHech qanday klubga obuna bo'lmagansiz."
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
        await query.edit_message_text("📋 *Asosiy menyu*", parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data.startswith("select_club:"):
        parts = data.split(":")
        team_id = int(parts[1])
        team_name = parts[2]
        user_id = str(query.from_user.id)
        if "subscriptions" not in context.bot_data:
            context.bot_data["subscriptions"] = {}
        context.bot_data["subscriptions"][user_id] = {"id": team_id, "name": team_name, "last_goals": {}}
        await query.edit_message_text(
            f"✅ *{team_name}* klubiga obuna bo'ldingiz!\n🔔 Gol urganida xabar keladi.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bosh menyu", callback_data="back_menu")]])
        )

    elif data.startswith("day:"):
        date_str = data.split(":")[1]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        await show_fixtures_for_date(query, date_str, f"📅 {dt.strftime('%d.%m.%Y')} o'yinlari")

    elif data.startswith("match_detail:"):
        fixture_id = int(data.split(":")[1])
        await query.edit_message_text("⏳ Ma'lumotlar yuklanmoqda...", parse_mode="Markdown")
        fdata = await api_get("fixtures", {"id": fixture_id})
        fixtures = fdata.get("response", [])
        if not fixtures:
            await query.edit_message_text("❌ O'yin topilmadi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]))
            return
        detail = await format_match_detail(fixtures[0])
        if len(detail) > 4000:
            detail = detail[:4000] + "\n\n_...qisqartirildi_"
        await query.edit_message_text(detail, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]))

    elif data.startswith("search_team2:"):
        parts = data.split(":")
        t1id, t2id = int(parts[1]), int(parts[2])
        await query.edit_message_text("⏳ O'yinlar qidirilmoqda...", parse_mode="Markdown")
        fixtures = await search_fixtures_by_teams(t1id, t2id)
        if not fixtures:
            await query.edit_message_text("❌ O'yinlar topilmadi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]))
            return
        fixtures = sorted(fixtures, key=lambda x: x["fixture"]["date"], reverse=True)[:10]
        buttons = []
        for f in fixtures:
            home = f["teams"]["home"]["name"]
            away = f["teams"]["away"]["name"]
            hg = f["goals"]["home"] or 0
            ag = f["goals"]["away"] or 0
            date = f["fixture"]["date"][:10]
            fid = f["fixture"]["id"]
            buttons.append([InlineKeyboardButton(f"{date} | {home} {hg}:{ag} {away}", callback_data=f"match_detail:{fid}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
        await query.edit_message_text("🔍 *O'yinlar ro'yxati:*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("team_fix:"):
        parts = data.split(":")
        team_id = int(parts[1])
        team_name = parts[2]
        await query.edit_message_text(f"⏳ *{team_name}* o'yinlari yuklanmoqda...", parse_mode="Markdown")

        last_fix = await get_team_last_fixtures(team_id)
        next_fix = await get_team_next_fixtures(team_id)

        lines = [f"📋 *{team_name}* o'yinlari\n"]

        lines.append("⏮ *Oxirgi 5 ta o'yin:*")
        lines.append("─" * 26)
        if last_fix:
            for f in sorted(last_fix, key=lambda x: x["fixture"]["date"], reverse=True):
                lines.append(format_team_fixture_row(f, team_id))
        else:
            lines.append("Ma'lumot yo'q")

        lines.append("")
        lines.append("⏭ *Keyingi 10 ta o'yin:*")
        lines.append("─" * 26)
        if next_fix:
            for f in next_fix:
                lines.append(format_team_fixture_row(f, team_id))
        else:
            lines.append("Rejalashtirilgan o'yinlar yo'q")

        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n\n_...qisqartirildi_"

        await query.edit_message_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")]]))

async def show_fixtures_for_date(query, date_str: str, title: str):
    await query.edit_message_text(f"⏳ {title} yuklanmoqda...", parse_mode="Markdown")
    fixtures = await get_fixtures(date_str)
    msg = build_fixtures_message(fixtures, title)
    if len(msg) > 4000:
        msg = msg[:4000] + "\n\n_...va boshqa o'yinlar_"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu"),
        InlineKeyboardButton("🔄 Yangilash", callback_data=f"day:{date_str}")
    ]])
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)

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
    await query.edit_message_text("📆 *Haftalik jadval*\nKun tanlang:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Jamoa o'yinlari qidirish
    if context.user_data.get("awaiting_team_fixtures"):
        context.user_data["awaiting_team_fixtures"] = False
        msg = await update.message.reply_text(f"🔍 *{text}* qidirilmoqda...", parse_mode="Markdown")
        teams = await search_team(text)
        if not teams:
            await msg.edit_text("❌ Jamoa topilmadi.")
            return
        buttons = []
        for t in teams:
            name = t["team"]["name"]
            tid = t["team"]["id"]
            country = t["team"].get("country", "")
            buttons.append([InlineKeyboardButton(f"{name} ({country})", callback_data=f"team_fix:{tid}:{name}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
        await msg.edit_text("🔍 *Topilgan jamoalar:*\nTanlang:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # O'yin qidirish
    if context.user_data.get("awaiting_match_search"):
        context.user_data["awaiting_match_search"] = False
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Ikki jamoa nomini yozing.\nMasalan: `Arsenal Chelsea`",
                parse_mode="Markdown", reply_markup=main_menu_keyboard())
            return
        mid = len(parts) // 2
        t1q = " ".join(parts[:mid])
        t2q = " ".join(parts[mid:])
        msg = await update.message.reply_text(f"🔍 *{t1q}* va *{t2q}* qidirilmoqda...", parse_mode="Markdown")
        t1_list = await search_team(t1q)
        t2_list = await search_team(t2q)
        if not t1_list:
            await msg.edit_text(f"❌ *{t1q}* topilmadi.", parse_mode="Markdown")
            return
        if not t2_list:
            await msg.edit_text(f"❌ *{t2q}* topilmadi.", parse_mode="Markdown")
            return
        t1 = t1_list[0]["team"]
        t2 = t2_list[0]["team"]
        fixtures = await search_fixtures_by_teams(t1["id"], t2["id"])
        if not fixtures:
            await msg.edit_text(f"❌ *{t1['name']}* va *{t2['name']}* o'rtasida o'yinlar topilmadi.",
                parse_mode="Markdown", reply_markup=main_menu_keyboard())
            return
        fixtures = sorted(fixtures, key=lambda x: x["fixture"]["date"], reverse=True)[:10]
        buttons = []
        for f in fixtures:
            home = f["teams"]["home"]["name"]
            away = f["teams"]["away"]["name"]
            hg = f["goals"]["home"] or 0
            ag = f["goals"]["away"] or 0
            date = f["fixture"]["date"][:10]
            fid = f["fixture"]["id"]
            buttons.append([InlineKeyboardButton(f"{date} | {home} {hg}:{ag} {away}", callback_data=f"match_detail:{fid}")])
        buttons.append([InlineKeyboardButton("🔙 Asosiy menyu", callback_data="back_menu")])
        await msg.edit_text(f"🔍 *{t1['name']} vs {t2['name']}* — so'nggi o'yinlar:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Klub tanlash
    if context.user_data.get("awaiting_club"):
        context.user_data["awaiting_club"] = False
        msg = await update.message.reply_text(f"🔍 *{text}* qidirilmoqda...", parse_mode="Markdown")
        teams = await search_team(text)
        if not teams:
            await msg.edit_text("❌ Klub topilmadi.")
            return
        buttons = []
        for t in teams:
            name = t["team"]["name"]
            tid = t["team"]["id"]
            country = t["team"].get("country", "")
            buttons.append([InlineKeyboardButton(f"{name} ({country})", callback_data=f"select_club:{tid}:{name}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_menu")])
        await msg.edit_text("🔍 *Topilgan klublar:*\nO'zingiznikini tanlang:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    await update.message.reply_text("Menyu uchun /start yoki /menu ishlating.",
        reply_markup=main_menu_keyboard())

# ============================================================
# Gol bildirishnoma
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
            fid = str(fixture["fixture"]["id"])
            hg = fixture["goals"]["home"] or 0
            ag = fixture["goals"]["away"] or 0
            elapsed = fixture["fixture"]["status"]["elapsed"] or 0
            prev_h = last_goals.get(fid, {}).get("home", 0)
            prev_a = last_goals.get(fid, {}).get("away", 0)
            hname = home["name"]
            aname = away["name"]
            if home["id"] == team_id and hg > prev_h:
                for _ in range(hg - prev_h):
                    await context.bot.send_message(chat_id=user_id,
                        text=f"⚽ *GOL! {team_name}*\n\n🏟 {hname} *{hg}* : {ag} {aname}\n⏱ {elapsed}'",
                        parse_mode="Markdown")
            elif away["id"] == team_id and ag > prev_a:
                for _ in range(ag - prev_a):
                    await context.bot.send_message(chat_id=user_id,
                        text=f"⚽ *GOL! {team_name}*\n\n🏟 {hname} {hg} : *{ag}* {aname}\n⏱ {elapsed}'",
                        parse_mode="Markdown")
            sub["last_goals"][fid] = {"home": hg, "away": ag}

# ============================================================
# Stats (admin)
# ============================================================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    subscriptions = context.bot_data.get("subscriptions", {})
    total = len(subscriptions)
    clubs = {}
    for sub in subscriptions.values():
        name = sub.get("name", "Noma'lum")
        clubs[name] = clubs.get(name, 0) + 1
    top = sorted(clubs.items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = "\n".join([f"  {i+1}. {n} — {c} ta" for i, (n, c) in enumerate(top)]) or "  Hali yo'q"
    await update.message.reply_text(
        f"📊 *Bot statistikasi*\n\n👥 Jami: *{total}*\n\n⭐ Top klublar:\n{top_text}",
        parse_mode="Markdown")

# ============================================================
# Main
# ============================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.job_queue.run_repeating(check_goals, interval=60, first=10)
    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)
