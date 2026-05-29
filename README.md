# ⚽ FutScore Telegram Bot

FotMob'ga o'xshagan futbol Telegram boti — o'zbek tilida!

---

## 🚀 Bosqichma-bosqich sozlash

### 1-qadam: Telegram Bot tokeni olish

1. Telegramda **@BotFather** ga yozing
2. `/newbot` buyrug'ini yuboring
3. Bot uchun nom bering (masalan: `FutScore Bot`)
4. Username bering (masalan: `futscore_uz_bot`)
5. BotFather sizga **token** beradi — uni saqlang!
   ```
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

---

### 2-qadam: Football API kaliti olish

1. **https://dashboard.api-football.com** ga kiring
2. Ro'yxatdan o'ting (bepul)
3. Dashboard'da **API Key** ni ko'ring va nusxa oling
4. Bepul plan: **100 ta so'rov/kun** (o'rtacha bot uchun yetarli)

---

### 3-qadam: Railway'ga deploy qilish (BEPUL)

1. **https://railway.app** ga kiring
2. GitHub akkauntingiz bilan tizimga kiring
3. **New Project** → **Deploy from GitHub repo** bosing
4. Ushbu papkani GitHub'ga yuklang:
   ```
   git init
   git add .
   git commit -m "FutScore bot"
   git branch -M main
   git remote add origin https://github.com/SIZNING_USERNAME/futscore-bot.git
   git push -u origin main
   ```
5. Railway'da repo'ni tanlang
6. **Variables** bo'limiga o'ting va qo'shing:
   ```
   BOT_TOKEN = (BotFather'dan olgan tokeningiz)
   FOOTBALL_API_KEY = (API-Football'dan olgan kalitingiz)
   ```
7. **Deploy** bosing — bot 2-3 daqiqada ishga tushadi!

---

## 📱 Bot buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/start` | Botni ishga tushirish |
| `/menu` | Asosiy menyuni ko'rish |

## 🎛 Bot imkoniyatlari

- 📅 **Bugungi o'yinlar** — barcha ligalar
- 🔴 **Jonli o'yinlar** — real vaqtda
- ⏮ **Kechagi natijalar**
- ⏭ **Ertangi jadval**
- 📆 **Haftalik jadval** — 2 kun oldin / 5 kun keyin
- ⭐ **Mening klubim** — sevimli klub tanlash
- 🔔 **Gol bildirishnomasi** — klub gol ursa xabar keladi

---

## 🔔 Gol bildirishnoma qanday ishlaydi?

1. Foydalanuvchi `/start` bosadi
2. "⭐ Mening klubim" tugmasini bosadi
3. Klub nomini yozadi (masalan: "Arsenal")
4. Ro'yxatdan o'z klubini tanlaydi
5. Endi o'sha klub har gol urganida foydalanuvchiga avtomatik xabar keladi:

```
⚽ GOL! Arsenal

🏟 Arsenal 2 : 1 Chelsea
⏱ 74' daqiqa
```

Bot har 60 soniyada jonli o'yinlarni tekshirib turadi.

---

## 📁 Fayl tuzilmasi

```
fotmob_bot/
├── bot.py           # Asosiy bot kodi
├── requirements.txt # Kutubxonalar
├── railway.toml     # Railway sozlamalari
├── .env.example     # Environment o'zgaruvchilari namunasi
└── README.md        # Ushbu fayl
```

---

## ⚠️ Muhim eslatmalar

- **Bepul Railway plan**: oyiga 500 soat (1 bot uchun yetarli)
- **Bepul API plan**: kuniga 100 so'rov (asosiy foydalanish uchun yetarli)
- Ko'p foydalanuvchi uchun **API-Football Pro** planiga o'ting

---

## 🆘 Muammo bo'lsa

Railway'da **Logs** bo'limini oching — u yerda xato xabarlarini ko'rishingiz mumkin.
