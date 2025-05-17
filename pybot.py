import json
import asyncio
import nest_asyncio
import os
import socket
import threading
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Завантаження токена та chat_id з config.json


BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

# Отримати наступну гонку з races.json
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

# Перевіряємо чи є гонка цього тижня
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

# Надсилання опитування (планувальник передає bot)
async def send_weekly_poll(context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot  # Get bot instance correctly
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


# Форматування тексту для повідомлення
def format_race_info(race):
    if race is None:
        return "🚫 Всі гонки вже завершились цього сезону."
    return (
        f"🏁 Наступна гонка: {race['name']}\n"
        f"📍 {race['circuit']} ({race['location']})\n"
        f"📅 Дата: {race['date_str']}\n"
        f"🕔 Час: {race['time']}"
    )

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🏎️ Показати наступну гонку", callback_data="next_race")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привіт! Натисни кнопку, щоб дізнатися про наступну гонку:",
        reply_markup=reply_markup
    )

# Команда /next
async def next_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    race = get_next_race_details()
    race_info = format_race_info(race)
    await update.message.reply_text(race_info)

# Команда /poll
async def manual_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        print("✅ /poll command received")  # Debug print
        race = get_race_this_week()
        if race:
            question = f"🏁 Чи будеш ти дивитись {race['raceName']} цієї неділі?"
            options = ["Так, буду! ✅", "Ні, не буду("]
            await context.bot.send_poll(
                chat_id=GROUP_CHAT_ID,
                question=question,
                options=options,
                is_anonymous=False,
                allows_multiple_answers=False
            )
        else:
            await update.message.reply_text("🚫 Цього тижня немає гонки — опитування не буде.")
    except Exception as e:
        print(f"❌ Error in manual_poll: {e}")


# Обробка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "next_race":
        race = get_next_race_details()
        race_info = format_race_info(race)
        await query.edit_message_text(race_info)

# Запуск бота
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()
    
    if app is None:
        print("❌ Не вдалося створити бота. Перевірте залежності.")
        return  # Вихід з функції

    # Фейк порт для Render
    def fake_port():
        s = socket.socket()
        s.bind(("", 10000))
        s.listen(1)
        while True:
            conn, addr = s.accept()
            conn.close()

    threading.Thread(target=fake_port, daemon=True).start()

    # Обробники
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_race))
    app.add_handler(CommandHandler("poll", manual_poll))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Планувальник
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_weekly_poll,
        trigger=CronTrigger(day_of_week="mon", hour=11, minute=30),
        args=[app]
    )
    scheduler.start()

    print("✅ Бот запущено")
    print(f"🔍 Application object: {app}")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    nest_asyncio.apply()  # Додаємо модифікацію
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())  # Використовуємо loop.run_until_complete()
    except RuntimeError as e:
        print(f"❌ RuntimeError: {e}")
