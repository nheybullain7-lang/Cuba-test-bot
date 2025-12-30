import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import sqlite3
from datetime import datetime

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Base de datos
def init_db():
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, chips INTEGER DEFAULT 1000)''')
    c.execute('''CREATE TABLE IF NOT EXISTS game_rooms
                 (room_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  creator_id INTEGER, 
                  status TEXT DEFAULT 'waiting',
                  current_players INTEGER DEFAULT 1,
                  max_players INTEGER DEFAULT 6)''')
    conn.commit()
    conn.close()

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎲 ¡Bienvenido a Cuba Poker Bot! 🎲\n\n"
        "Comandos disponibles:\n"
        "/start - Muestra este mensaje\n"
        "/registro_test [nombre] - Registra un usuario de prueba\n"
        "/unirse - Únete a una sala de poker\n"
        "/crear_sala - Crea una nueva sala\n"
        "/salas - Muestra salas disponibles\n"
        "/chips - Muestra tus fichas\n"
    )

# Comando /registro_test
async def registro_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /registro_test [tu_nombre]")
        return
    
    username = args[0]
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    # Verificar si ya existe
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if c.fetchone():
        await update.message.reply_text(f"✅ Ya estás registrado como {username}!")
    else:
        c.execute("INSERT INTO users (user_id, username, chips) VALUES (?, ?, 1000)",
                 (user_id, username))
        conn.commit()
        await update.message.reply_text(f"✅ Registrado como {username} con 1000 fichas!")
    
    conn.close()

# Comando /unirse
async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    # Verificar registro
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        await update.message.reply_text("❌ Debes registrarte primero con /registro_test [nombre]")
        conn.close()
        return
    
    # Buscar sala disponible
    c.execute("SELECT * FROM game_rooms WHERE status='waiting' AND current_players < max_players LIMIT 1")
    room = c.fetchone()
    
    if room:
        room_id = room[0]
        c.execute("UPDATE game_rooms SET current_players = current_players + 1 WHERE room_id=?", (room_id,))
        await update.message.reply_text(f"✅ ¡Te uniste a la sala {room_id}!\nEsperando más jugadores...")
    else:
        await update.message.reply_text("📝 No hay salas disponibles. Crea una con /crear_sala")
    
    conn.commit()
    conn.close()

# Comando /crear_sala
async def crear_sala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    # Verificar registro
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        await update.message.reply_text("❌ Debes registrarte primero con /registro_test [nombre]")
        conn.close()
        return
    
    # Crear sala
    c.execute("INSERT INTO game_rooms (creator_id) VALUES (?)", (user_id,))
    conn.commit()
    
    c.execute("SELECT last_insert_rowid()")
    room_id = c.fetchone()[0]
    
    await update.message.reply_text(
        f"✅ ¡Sala {room_id} creada!\n"
        f"Comparte este ID para que otros se unan con /unirse\n"
        f"Estado: Esperando jugadores..."
    )
    
    conn.close()

# Comando /salas
async def salas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT room_id, current_players, max_players FROM game_rooms WHERE status='waiting'")
    rooms = c.fetchall()
    
    if not rooms:
        await update.message.reply_text("📭 No hay salas disponibles. ¡Crea una con /crear_sala!")
    else:
        mensaje = "🏠 **Salas Disponibles:**\n\n"
        for room in rooms:
            mensaje += f"• Sala {room[0]}: {room[1]}/{room[2]} jugadores\n"
        
        mensaje += "\nÚnete con /unirse"
        await update.message.reply_text(mensaje)
    
    conn.close()

# Comando /chips
async def chips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT username, chips FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    
    if user:
        await update.message.reply_text(f"💰 {user[0]}, tienes {user[1]} fichas")
    else:
        await update.message.reply_text("❌ No estás registrado. Usa /registro_test [nombre]")
    
    conn.close()

def main():
    # Inicializar base de datos
    init_db()
    
    # Obtener token
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        logger.error("❌ No se encontró BOT_TOKEN en variables de entorno")
        return
    
    # Crear aplicación
    application = Application.builder().token(TOKEN).build()
    
    # Añadir handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("registro_test", registro_test))
    application.add_handler(CommandHandler("unirse", unirse))
    application.add_handler(CommandHandler("crear_sala", crear_sala))
    application.add_handler(CommandHandler("salas", salas))
    application.add_handler(CommandHandler("chips", chips))
    
    # Iniciar bot
    logger.info("🤖 Bot iniciado...")
    application.run_polling()

if __name__ == '__main__':
    main()
