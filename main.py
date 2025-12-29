import os
from telegram import Update
from telegram.ext import Application, CommandHandler

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context):
    await update.message.reply_text("🎰 ¡Bot de Poker funcionando!")

async def registro_test(update: Update, context):
    await update.message.reply_text("✅ Registro exitoso")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registro_test", registro_test))
    app.run_polling()

if __name__ == "__main__":
    main()
