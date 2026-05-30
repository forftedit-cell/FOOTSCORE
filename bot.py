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
SEASON = 2025
WC_LEAGUE_ID = 1
WC_SEASON = 2026

TOP_LEAGUES = {
    39: "Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga",
    61: "Ligue 1",
    2: "Champions League",
    3: "Europa League",
    848: "Conference League",
}

async def api_get(endpoint, params):
    url = f"{API_BASE}/{endpoint}"
    logger.info(f"API request: {url} params={params}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                logger.info(f"API response status: {resp.status}")
                data = await resp.json()
                logger.info(f"API response keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
                return data
    except Exception as e:
        logger.error(f"API error: {e}")
        return {}

async def get_fixtures(date_str):
    data = await api_get("fixtures", {"date": date_str, "season": SEASON})
    return data.get("response", [])

async def get_live_fixtures():
    data = await api_get("fixtures", {"live": "all"})
    return data.get("response", [])

async def search_team(name):
    data = await api_get("teams", {"search": name})
    return data.get("response", [])[:5]

async def get_team_last(team_id):
    data = await api_get("fixtures", {"team": team_id, "last": 5, "season": SEASON})
    return data.get("response", [])

async def get_team_next(team_id):
    data = await api_get("fixtures", {"team": team_id, "next": 10})
    return data.get("response", [])

async def get_h2h(t1, t2):
    data = await api_get("fixtures/headtohead", {"h2h": f"{t1}-{t2}", "last": 10})
    return data.get("response", [])

async def get_events(fid):
    data = await api_get("fixtures/events", {"fixture": fid})
    return data.get("response", [])

async def get_stats(fid):
    data = await api_get("fixtures/statistics", {"fixture": fid})
    return data.get("response", [])

async def get_wc_fixtures(stage=None):
    params = {"league": WC_LEAGUE_ID, "season": WC_SEASON}
    if stage:
        params["round"] = stage
    data = await api_get("fixtures", params)
    return data.get("response", [])

async def get_wc_standings():
    data = await api_get("standings", {"league": WC_LEAGUE_ID, "season": WC_SEASON})
    return data.get("response", [])

def fmt_fixture(f):
    home = f["teams"]["home"]["name"]
    away = f["teams"]["away"]["name"]
    hg = f["goals"]["home"]
    ag = f["goals"]["away"]
    status = f["fixture"]["status"]["short"]
    elapsed = f["fixture"]["status"]["elapsed"]
    league = f["league"]["name"]
    if status in ("FT", "AET", "PEN"):
        t = "FT"
        score = f"{hg}:{ag}"
        hb = f"*{home}*" if (hg or 0) > (ag or 0) else home
        ab = f"*{away}*" if (ag or 0) > (hg or 0) else away
        return f"{t}  {hb} {score} {ab}\n[{league}]"
    elif status in ("1H", "2H", "HT", "ET"):
        return f"LIVE {elapsed}'  {home} {hg}:{ag} {away}\n[{league}]"
    elif status == "NS":
        dt = datetime.fromisoformat(f["fixture"]["date"].replace("Z", "+00:00"))
        return f"{dt.strftime('%H:%M')}  {home} vs {away}\n[{league}]"
    return f"{status}  {home} vs {away}\n[{league}]"

def build_fixtures_msg(fixtures, title):
    if not fixtures:
        return f"*{title}*\n\nO'yinlar topilmadi."
    grouped = {}
    for f in fixtures:
        lid = f["league"]["id"]
        lname = f["league"]["name"]
        grouped.setdefault((lid, lname), []).append(f)
    lines = [f"*{title}*\n"]
    for league_id, league_label in TOP_LEAGUES.items():
        for (lid, lname), matches in grouped.items():
            if lid == league_id:
                lines.append(f"\n{league_label}")
                lines.append("-" * 24)
                for m in matches:
                    lines.append(fmt_fixture(m))
                break
    top_ids = set(TOP_LEAGUES.keys())
    for (lid, lname), matches in grouped.items():
        if lid not in top_ids:
            lines.append(f"\n{lname}")
            lines.append("-" * 24)
            for m in matches:
                lines.append(fmt_fixture(m))
    return "\n".join(lines)

def fmt_team_row(f, team_id):
    home = f["teams"]["home"]
    away = f["teams"]["away"]
    hg = f["goals"]["home"] or 0
    ag = f["goals"]["away"] or 0
    status = f["fixture"]["status"]["short"]
    date = f["fixture"]["date"][:10]
    league = f["league"]["name"]
    if status in ("FT", "AET", "PEN"):
        if home["id"] == team_id:
            res = "G" if hg > ag else ("D" if hg == ag else "Y")
            opp = away["name"]
            loc = "Uy"
        else:
            res = "G" if ag > hg else ("D" if ag == hg else "Y")
            opp = home["name"]
            loc = "Tashqari"
        emoji = "+" if res == "G" else ("=" if res == "D" else "-")
        return f"{emoji} {date} | {opp} {hg}:{ag} ({loc}) [{league}]"
    elif status == "NS":
        dt = datetime.fromisoformat(f["fixture"]["date"].replace("Z", "+00:00"))
        opp = away["name"] if home["id"] == team_id else home["name"]
        loc = "Uy" if home["id"] == team_id else "Tashqari"
        return f"Kelgusi {dt.strftime('%d.%m %H:%M')} | {opp} ({loc}) [{league}]"
    return f"{date} | {f['teams']['home']['name']} vs {f['teams']['away']['name']}"

async def fmt_match_detail(fixture):
    fid = fixture["fixture"]["id"]
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    hg = fixture["goals"]["home"] or 0
    ag = fixture["goals"]["away"] or 0
    league = fixture["league"]["name"]
    dt = datetime.fromisoformat(fixture["fixture"]["date"].replace("Z", "+00:00"))
    lines = [
        f"*{home} vs {away}*",
        f"{league}",
        f"{dt.strftime('%d.%m.%Y %H:%M')}",
        f"Hisob: *{hg} : {ag}*",
        ""
    ]
    events = await get_events(fid)
    if events:
        lines.append("*Voqealar:*")
        for e in events:
            etype = e.get("type", "")
            detail = e.get("detail", "")
            minute = e.get("time", {}).get("elapsed", "?")
            player = e.get("player", {}).get("name", "")
            team = e.get("team", {}).get("name", "")
            if etype == "Goal":
                prefix = "OG" if detail == "Own Goal" else ("Pen" if detail == "Penalty" else "Gol")
                lines.append(f"  {minute}' {prefix} - {player} ({team})")
            elif etype == "Card":
                card = "Sariq" if detail == "Yellow Card" else "Qizil"
                lines.append(f"  {minute}' {card} - {player} ({team})")
    stats = await get_stats(fid)
    if stats and len(stats) >= 2:
        lines.append("")
        lines.append("*Statistika:*")
        hs = {s["type"]: s["value"] for s in stats[0].get("statistics", [])}
        as_ = {s["type"]: s["value"] for s in stats[1].get("statistics", [])}
        for key, label in [
            ("Ball Possession", "Top"), ("Total Shots", "Urinish"),
            ("Shots on Goal", "Darvozaga"), ("Corner Kicks", "Burchak"),
            ("Fouls", "Faul"), ("Yellow Cards", "Sariq"), ("Red Cards", "Qizil"),
        ]:
            hv = hs.get(key, 0) or 0
            av = as_.get(key, 0) or 0
            lines.append(f"  {label}: {hv} - {av}")
    return "\n".join(lines)

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Bugungi o'yinlar", callback_data="today"),
            InlineKeyboardButton("Jonli", callback_data="live"),
        ],
        [
            InlineKeyboardButton("Kechagi", callback_data="yesterday"),
            InlineKeyboardButton("Ertangi", callback_data="tomorrow"),
        ],
        [InlineKeyboardButton("Haftalik jadval", callback_data="week")],
        [
            InlineKeyboardButton("O'yin qidirish", callback_data="search_match"),
            InlineKeyboardButton("Jamoa o'yinlari", callback_data="team_fixtures"),
        ],
        [
            InlineKeyboardButton("World Cup 2026", callback_data="wc2026"),
        ],
        [
            InlineKeyboardButton("Mening klubim", callback_data="my_club"),
            InlineKeyboardButton("Bildirishnomalar", callback_data="notifications"),
        ],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*FutScore Botga xush kelibsiz!*\n\n"
        "Barcha ligalar natijalari, jonli o'yinlar,\n"
        "jamoa o'yinlari, World Cup 2026 va gol bildirishnomalari!\n\n"
        "Menyudan tanlang:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Asosiy menyu:", reply_markup=main_menu())

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    back_btn = [[InlineKeyboardButton("Orqaga", callback_data="back_menu")]]

    if data == "back_menu":
        await query.edit_message_text("Asosiy menyu:", reply_markup=main_menu())

    elif data == "today":
        await show_date(query, datetime.now().strftime("%Y-%m-%d"), "Bugungi o'yinlar")

    elif data == "yesterday":
        d = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        await show_date(query, d, "Kechagi o'yinlar")

    elif data == "tomorrow":
        d = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        await show_date(query, d, "Ertangi o'yinlar")

    elif data == "live":
        await query.edit_message_text("Yuklanmoqda...")
        fx = await get_live_fixtures()
        msg = build_fixtures_msg(fx, "Jonli o'yinlar")
        if len(msg) > 4000:
            msg = msg[:4000] + "\n...qisqartirildi"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Orqaga", callback_data="back_menu"),
            InlineKeyboardButton("Yangilash", callback_data="live"),
        ]])
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)

    elif data == "week":
        today = datetime.now()
        buttons = []
        for i in range(-2, 6):
            d = today + timedelta(days=i)
            label = d.strftime("%d.%m %a")
            if i == 0:
                label = "Bugun " + label
            buttons.append(InlineKeyboardButton(label, callback_data=f"day:{d.strftime('%Y-%m-%d')}"))
        rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        rows.append([InlineKeyboardButton("Orqaga", callback_data="back_menu")])
        await query.edit_message_text("Kun tanlang:", reply_markup=InlineKeyboardMarkup(rows))

    elif data.startswith("day:"):
        date_str = data.split(":")[1]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        await show_date(query, date_str, f"{dt.strftime('%d.%m.%Y')} o'yinlari")

    elif data == "search_match":
        await query.edit_message_text(
            "O'yin qidirish\n\nIkki jamoa nomini yozing:\nMasalan: Arsenal Chelsea",
            reply_markup=InlineKeyboardMarkup(back_btn)
        )
        context.user_data["mode"] = "search_match"

    elif data == "team_fixtures":
        await query.edit_message_text(
            "Jamoa o'yinlari\n\nJamoa nomini yozing:\nMasalan: Arsenal",
            reply_markup=InlineKeyboardMarkup(back_btn)
        )
        context.user_data["mode"] = "team_fixtures"

    elif data == "my_club":
        await query.edit_message_text(
            "Sevimli klubingizni kiriting:\nMasalan: Arsenal",
            reply_markup=InlineKeyboardMarkup(back_btn)
        )
        context.user_data["mode"] = "my_club"

    elif data == "notifications":
        subs = context.bot_data.get("subscriptions", {})
        club = subs.get(str(query.from_user.id))
        if club:
            txt = f"Siz *{club['name']}* klubiga obunasiz.\nGol urganida xabar keladi!"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Obunani bekor qilish", callback_data="unsubscribe")],
                [InlineKeyboardButton("Orqaga", callback_data="back_menu")],
            ])
        else:
            txt = "Hech qanday klubga obuna emassiz."
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Klub tanlash", callback_data="my_club")],
                [InlineKeyboardButton("Orqaga", callback_data="back_menu")],
            ])
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=kb)

    elif data == "unsubscribe":
        subs = context.bot_data.get("subscriptions", {})
        subs.pop(str(query.from_user.id), None)
        await query.edit_message_text("Obuna bekor qilindi.",
            reply_markup=InlineKeyboardMarkup(back_btn))

    elif data.startswith("select_club:"):
        parts = data.split(":")
        tid = int(parts[1])
        tname = parts[2]
        subs = context.bot_data.setdefault("subscriptions", {})
        subs[str(query.from_user.id)] = {"id": tid, "name": tname, "last_goals": {}}
        await query.edit_message_text(
            f"*{tname}* klubiga obuna boldingiz!\nGol urganida xabar keladi.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back_btn)
        )

    elif data.startswith("match_detail:"):
        fid = int(data.split(":")[1])
        await query.edit_message_text("Yuklanmoqda...")
        fdata = await api_get("fixtures", {"id": fid})
        fx = fdata.get("response", [])
        if not fx:
            await query.edit_message_text("Topilmadi.", reply_markup=InlineKeyboardMarkup(back_btn))
            return
        detail = await fmt_match_detail(fx[0])
        if len(detail) > 4000:
            detail = detail[:4000] + "\n...qisqartirildi"
        await query.edit_message_text(detail, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back_btn))

    elif data.startswith("team_fix:"):
        parts = data.split(":")
        tid = int(parts[1])
        tname = parts[2]
        await query.edit_message_text("Yuklanmoqda...")
        last_fx = await get_team_last(tid)
        next_fx = await get_team_next(tid)
        lines = [f"*{tname} - O'yinlar*\n"]
        lines.append("*Oxirgi 5 ta:*")
        lines.append("-" * 22)
        if last_fx:
            for f in sorted(last_fx, key=lambda x: x["fixture"]["date"], reverse=True):
                lines.append(fmt_team_row(f, tid))
        else:
            lines.append("Ma'lumot yo'q")
        lines.append("")
        lines.append("*Keyingi 10 ta:*")
        lines.append("-" * 22)
        if next_fx:
            for f in next_fx:
                lines.append(fmt_team_row(f, tid))
        else:
            lines.append("Rejalashtirilgan o'yin yo'q")
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n...qisqartirildi"
        await query.edit_message_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back_btn))

    elif data == "wc2026":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Guruh bosqichi", callback_data="wc_stage:Group Stage")],
            [InlineKeyboardButton("Round of 32", callback_data="wc_stage:Round of 32")],
            [InlineKeyboardButton("Round of 16", callback_data="wc_stage:Round of 16")],
            [InlineKeyboardButton("Chorak final", callback_data="wc_stage:Quarter-finals")],
            [InlineKeyboardButton("Yarim final", callback_data="wc_stage:Semi-finals")],
            [InlineKeyboardButton("Final", callback_data="wc_stage:Final")],
            [InlineKeyboardButton("Guruhlar jadvali", callback_data="wc_standings")],
            [InlineKeyboardButton("Orqaga", callback_data="back_menu")],
        ])
        await query.edit_message_text(
            "*FIFA World Cup 2026*\n\n"
            "11 Iyun - 19 Iyul 2026\n"
            "AQSh, Kanada, Meksika\n"
            "48 jamoa, 104 o'yin\n\n"
            "Bo'limni tanlang:",
            parse_mode="Markdown",
            reply_markup=kb
        )

    elif data.startswith("wc_stage:"):
        stage = data.split(":", 1)[1]
        await query.edit_message_text("Yuklanmoqda...")
        fx = await get_wc_fixtures(stage)
        if not fx:
            await query.edit_message_text(
                f"*{stage}* - hali boshlanmagan.\n\nWorld Cup 2026 - 11 Iyundan!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="wc2026")]])
            )
            return
        lines = [f"*World Cup 2026 - {stage}*\n"]
        for f in fx[:30]:
            home = f["teams"]["home"]["name"]
            away = f["teams"]["away"]["name"]
            status = f["fixture"]["status"]["short"]
            dt = datetime.fromisoformat(f["fixture"]["date"].replace("Z", "+00:00"))
            hg = f["goals"]["home"]
            ag = f["goals"]["away"]
            city = f["fixture"].get("venue", {}).get("city", "")
            if status in ("FT", "AET", "PEN"):
                lines.append(f"FT | {home} {hg}:{ag} {away} | {city}")
            elif status in ("1H", "2H", "HT"):
                lines.append(f"LIVE | {home} {hg}:{ag} {away} | {city}")
            else:
                lines.append(f"{dt.strftime('%d.%m %H:%M')} | {home} vs {away} | {city}")
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n...qisqartirildi"
        await query.edit_message_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="wc2026")]]))

    elif data == "wc_standings":
        await query.edit_message_text("Yuklanmoqda...")
        standings = await get_wc_standings()
        if not standings:
            await query.edit_message_text(
                "Guruhlar jadvali hali mavjud emas.\nWorld Cup 2026 - 11 Iyundan!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="wc2026")]])
            )
            return
        lines = ["*World Cup 2026 - Guruhlar*\n"]
        for group in standings[:12]:
            gname = group[0]["group"] if group else ""
            lines.append(f"\n*{gname}*")
            for team in group:
                t = team["team"]["name"]
                pts = team["points"]
                w = team["all"]["win"]
                d = team["all"]["draw"]
                l = team["all"]["lose"]
                lines.append(f"  {t}: {pts}pts ({w}G {d}D {l}Y)")
        msg = "\n".join(lines)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n...qisqartirildi"
        await query.edit_message_text(msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Orqaga", callback_data="wc2026")]]))

async def show_date(query, date_str, title):
    await query.edit_message_text("Yuklanmoqda...")
    fx = await get_fixtures(date_str)
    msg = build_fixtures_msg(fx, title)
    if len(msg) > 4000:
        msg = msg[:4000] + "\n...qisqartirildi"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Orqaga", callback_data="back_menu"),
        InlineKeyboardButton("Yangilash", callback_data=f"day:{date_str}"),
    ]])
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.get("mode")

    if mode == "team_fixtures":
        context.user_data["mode"] = None
        msg = await update.message.reply_text(f"Qidirilmoqda: {text}...")
        teams = await search_team(text)
        if not teams:
            await msg.edit_text("Topilmadi.")
            return
        buttons = []
        for t in teams:
            name = t["team"]["name"]
            tid = t["team"]["id"]
            country = t["team"].get("country", "")
            buttons.append([InlineKeyboardButton(f"{name} ({country})", callback_data=f"team_fix:{tid}:{name}")])
        buttons.append([InlineKeyboardButton("Orqaga", callback_data="back_menu")])
        await msg.edit_text("Tanlang:", reply_markup=InlineKeyboardMarkup(buttons))

    elif mode == "search_match":
        context.user_data["mode"] = None
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("Ikki jamoa nomini yozing. Masalan: Arsenal Chelsea")
            return
        mid = len(parts) // 2
        t1q = " ".join(parts[:mid])
        t2q = " ".join(parts[mid:])
        msg = await update.message.reply_text(f"Qidirilmoqda: {t1q} va {t2q}...")
        t1list = await search_team(t1q)
        t2list = await search_team(t2q)
        if not t1list:
            await msg.edit_text(f"{t1q} topilmadi.")
            return
        if not t2list:
            await msg.edit_text(f"{t2q} topilmadi.")
            return
        t1 = t1list[0]["team"]
        t2 = t2list[0]["team"]
        fx = await get_h2h(t1["id"], t2["id"])
        if not fx:
            await msg.edit_text(f"{t1['name']} va {t2['name']} o'rtasida o'yinlar topilmadi.")
            return
        fx = sorted(fx, key=lambda x: x["fixture"]["date"], reverse=True)[:10]
        buttons = []
        for f in fx:
            home = f["teams"]["home"]["name"]
            away = f["teams"]["away"]["name"]
            hg = f["goals"]["home"] or 0
            ag = f["goals"]["away"] or 0
            date = f["fixture"]["date"][:10]
            fid = f["fixture"]["id"]
            buttons.append([InlineKeyboardButton(f"{date} | {home} {hg}:{ag} {away}", callback_data=f"match_detail:{fid}")])
        buttons.append([InlineKeyboardButton("Orqaga", callback_data="back_menu")])
        await msg.edit_text(f"{t1['name']} vs {t2['name']} - so'nggi o'yinlar:",
            reply_markup=InlineKeyboardMarkup(buttons))

    elif mode == "my_club":
        context.user_data["mode"] = None
        msg = await update.message.reply_text(f"Qidirilmoqda: {text}...")
        teams = await search_team(text)
        if not teams:
            await msg.edit_text("Topilmadi.")
            return
        buttons = []
        for t in teams:
            name = t["team"]["name"]
            tid = t["team"]["id"]
            country = t["team"].get("country", "")
            buttons.append([InlineKeyboardButton(f"{name} ({country})", callback_data=f"select_club:{tid}:{name}")])
        buttons.append([InlineKeyboardButton("Orqaga", callback_data="back_menu")])
        await msg.edit_text("Klubingizni tanlang:", reply_markup=InlineKeyboardMarkup(buttons))

    else:
        await update.message.reply_text("/start yoki /menu", reply_markup=main_menu())

async def check_goals(context: ContextTypes.DEFAULT_TYPE):
    subs = context.bot_data.get("subscriptions", {})
    if not subs:
        return
    live = await get_live_fixtures()
    for uid, sub in subs.items():
        tid = sub["id"]
        tname = sub["name"]
        last = sub.get("last_goals", {})
        for f in live:
            home = f["teams"]["home"]
            away = f["teams"]["away"]
            if home["id"] != tid and away["id"] != tid:
                continue
            fid = str(f["fixture"]["id"])
            hg = f["goals"]["home"] or 0
            ag = f["goals"]["away"] or 0
            elapsed = f["fixture"]["status"]["elapsed"] or 0
            ph = last.get(fid, {}).get("home", 0)
            pa = last.get(fid, {}).get("away", 0)
            hn = home["name"]
            an = away["name"]
            if home["id"] == tid and hg > ph:
                for _ in range(hg - ph):
                    await context.bot.send_message(chat_id=uid,
                        text=f"GOL! {tname}\n\n{hn} {hg}:{ag} {an}\n{elapsed}'",
                        parse_mode="Markdown")
            elif away["id"] == tid and ag > pa:
                for _ in range(ag - pa):
                    await context.bot.send_message(chat_id=uid,
                        text=f"GOL! {tname}\n\n{hn} {hg}:{ag} {an}\n{elapsed}'",
                        parse_mode="Markdown")
            sub["last_goals"][fid] = {"home": hg, "away": ag}

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Faqat admin uchun.")
        return
    subs = context.bot_data.get("subscriptions", {})
    total = len(subs)
    clubs = {}
    for s in subs.values():
        n = s.get("name", "?")
        clubs[n] = clubs.get(n, 0) + 1
    top = sorted(clubs.items(), key=lambda x: x[1], reverse=True)[:5]
    top_txt = "\n".join([f"{i+1}. {n} - {c} ta" for i, (n, c) in enumerate(top)]) or "Yo'q"
    await update.message.reply_text(
        f"*Statistika*\n\nFoydalanuvchilar: *{total}*\n\nTop klublar:\n{top_txt}",
        parse_mode="Markdown"
    )

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi!")
        return
    logger.info("Bot ishga tushmoqda...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.job_queue.run_repeating(check_goals, interval=60, first=10)
    logger.info("Bot tayyor!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
