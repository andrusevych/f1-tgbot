import json
import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    Application,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
from contextlib import asynccontextmanager

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://https://f1-tgbot-1.onrender.com/webhook/{BOT_TOKEN}"

application = ApplicationBuilder().token(BOT_TOKEN).build()

def get_next_race_details():
    try:
        with open("races.json", "r", encoding="utf-8") as file:
            races = json.load(file)
        today = datetime.utcnow().date()
        for race in races:
            race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
            if race_date >= today:
                return {
                    "name": race["raceName"],
                    "date": race_date,
                    "date_str": race["date"],
                    "time": race["time"],
                    "circuit": race["Circuit"]["circuitName"],
                    "location": f"{race['Circuit']['Location']['locality']}, {race['Circuit']['Location']['country']}",
                }
        return None
    except Exception as e:
        print(f"❌ Помилка при читанні гонок: {e}")
        return None

def get_race_this_week():
    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    with open("races.json", "r", encoding="utf-8") as file:
        races = json.load(file)

    for race in races:
        race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
        if monday <= race_date <= sunday:
            return race
    return None

async def send_weekly_poll(app: Application):
    bot = app.bot
    race = get_race_this_week()
    if race:
        question = f"🏁 Чи будеш ти дивитись {race['raceName']} цієї неділі?"
        options = ["Так, буду! ✅", "Ні, не буду("]
        await bot.send_poll(
            chat_id=GROUP_CHAT_ID,
            question=question,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False
        )
        print(f"📤 Опитування надіслано для гонки: {race['raceName']}")
    else:
        print("ℹ️ Цього тижня немає гонки — опитування не надіслано.")

def format_race_info(race):
    if race is None:
        return "🚫 Всі гонки вже завершились цього сезону."
    return (
        f"🏁 Наступна гонка: {race['name']}\n"
        f"📍 {race['circuit']} ({race['location']})\n"
        f"📅 Дата: {race['date_str']}\n"
        f"🕔 Час: {race['time']}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🏎️ Показати наступну гонку", callback_data="next_race")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привіт! Натисни кнопку, щоб дізнатися про наступну гонку:",
        reply_markup=reply_markup
    )

async def next_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    race = get_next_race_details()
    race_info = format_race_info(race)
    await update.message.reply_text(race_info)

async def manual_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    race = get_race_this_week()
    if race:
        question = f"🏁 Чи будеш ти дивитись {race['raceName']} цієї неділі?"
        options = ["Так, буду! ✅", "Ні, не буду("]
        await update.effective_chat.send_poll(
            question=question,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False
        )
    else:
        await update.message.reply_text("🚫 Цього тижня немає гонки — опитування не буде.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "next_race":
        race = get_next_race_details()
        race_info = format_race_info(race)
        await query.edit_message_text(race_info)

# Додаємо обробники до application
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("next", next_race))
application.add_handler(CommandHandler("poll", manual_poll))
application.add_handler(CallbackQueryHandler(button_handler))


scheduler = AsyncIOScheduler()

async def process_updates(application: Application):
    try:
        while True:
            update = await application.update_queue.get()
            await application.process_update(update)
    except asyncio.CancelledError:
        print("process_updates task cancelled")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🚀 STARTUP
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)

    scheduler.add_job(
    send_weekly_poll,
    trigger=CronTrigger(day_of_week="mon", hour=11, minute=30),
    args=[application]
)
    scheduler.start()
    print("Webhook встановлено і scheduler запущено")

    # Запускаємо таск обробки оновлень
    update_task = asyncio.create_task(process_updates(application))

    yield  # ⏳ Між startup і shutdown

    # 🧹 SHUTDOWN
    update_task.cancel()
    await application.bot.delete_webhook()
    scheduler.shutdown()
    print("Webhook видалено і scheduler зупинено")
    
app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update_data = await request.json()
    update = Update.de_json(update_data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

if not BOT_TOKEN or not GROUP_CHAT_ID:
    raise RuntimeError("❌ BOT_TOKEN або GROUP_CHAT_ID не задані у середовищі!")
