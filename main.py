import os
import logging
import random
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

# Mazo de cartas
SUITS = ['♠️', '♥️', '♦️', '♣️']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
DECK = [f"{rank}{suit}" for suit in SUITS for rank in RANKS]

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
                  max_players INTEGER DEFAULT 2,
                  players TEXT DEFAULT '',
                  deck TEXT DEFAULT '',
                  pot INTEGER DEFAULT 0,
                  current_turn INTEGER DEFAULT 0)''')
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
        "/chips - Muestra tus fichas\n\n"
        "⚠️ ¡ALERTA! Al unirte 2 jugadores, el juego comienza AUTOMÁTICAMENTE!"
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

# Repartir cartas automáticamente
async def iniciar_juego_automatico(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    # Obtener jugadores
    c.execute("SELECT players FROM game_rooms WHERE room_id=?", (room_id,))
    players_str = c.fetchone()[0]
    players = players_str.split(',') if players_str else []
    
    if len(players) >= 2:
        # Mezclar mazo
        deck = DECK.copy()
        random.shuffle(deck)
        
        # Repartir 2 cartas a cada jugador
        manos = {}
        for i, player_id in enumerate(players):
            if i*2+1 < len(deck):
                mano = [deck[i*2], deck[i*2+1]]
                manos[int(player_id)] = mano
        
                # Enviar cartas por privado
                try:
                    await context.bot.send_message(
                        chat_id=int(player_id),
                        text=f"🃏 **TUS CARTAS:**\n{mano[0]} {mano[1]}\n\n"
                             f"¡El juego ha comenzado! Espera tu turno para apostar."
                    )
                except:
                    pass
        
        # Guardar estado
        deck_str = ','.join(deck[4:])  # Quitar cartas repartidas
        c.execute("UPDATE game_rooms SET status='playing', deck=?, pot=50, current_turn=? WHERE room_id=?",
                 (deck_str, players[0], room_id))
        
        # Mensaje en grupo (si hay chat_id de grupo)
        for player_id in players:
            try:
                keyboard = [
                    [InlineKeyboardButton("✅ Ver", callback_data=f"ver_{room_id}"),
                     InlineKeyboardButton("📤 Apostar 10", callback_data=f"apostar_{room_id}_10"),
                     InlineKeyboardButton("📤 Apostar 50", callback_data=f"apostar_{room_id}_50")],
                    [InlineKeyboardButton("🔄 Pasar", callback_data=f"pasar_{room_id}"),
                     InlineKeyboardButton("🏳️ Retirarse", callback_data=f"retirarse_{room_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=int(player_id),
                    text="🎰 **MESA DE POKER** 🎰\n\n"
                         "¡Juego iniciado! Bote: 50 fichas\n"
                         "Es el turno del primer jugador.\n"
                         "Usa los botones para jugar:",
                    reply_markup=reply_markup
                )
            except:
                pass
        
        conn.commit()
    
    conn.close()

# Comando /unirse
async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    # Verificar registro
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    
    if not user:
        await update.message.reply_text("❌ Debes registrarte primero con /registro_test [nombre]")
        conn.close()
        return
    
    username = user[1]
    
    # Buscar sala disponible
    c.execute("SELECT * FROM game_rooms WHERE status='waiting' AND current_players < max_players LIMIT 1")
    room = c.fetchone()
    
    if room:
        room_id = room[0]
        current_players = room[3] + 1
        
        # Obtener jugadores actuales
        c.execute("SELECT players FROM game_rooms WHERE room_id=?", (room_id,))
        players_str = c.fetchone()[0] or ""
        players_list = players_str.split(',') if players_str else []
        players_list.append(str(user_id))
        new_players_str = ','.join(players_list)
        
        c.execute("UPDATE game_rooms SET current_players=?, players=? WHERE room_id=?",
                 (current_players, new_players_str, room_id))
        
        await update.message.reply_text(
            f"✅ ¡{username} se unió a la sala {room_id}!\n"
            f"Jugadores: {current_players}/2\n\n"
            f"⚠️ Cuando se una el segundo jugador, el juego comenzará AUTOMÁTICAMENTE!"
        )
        
        # Si ya hay 2 jugadores, iniciar juego
        if current_players >= 2:
            c.execute("UPDATE game_rooms SET status='starting' WHERE room_id=?", (room_id,))
            await update.message.reply_text("🎰 ¡2 JUGADORES! El juego comienza en 3 segundos...")
            conn.commit()
            conn.close()
            
            # Esperar y iniciar
            import asyncio
            await asyncio.sleep(3)
            await iniciar_juego_automatico(room_id, context)
        else:
            conn.commit()
            conn.close()
    else:
        await update.message.reply_text("📝 No hay salas disponibles. Crea una con /crear_sala")
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
    c.execute("INSERT INTO game_rooms (creator_id, players) VALUES (?, ?)", 
             (user_id, str(user_id)))
    conn.commit()
    
    c.execute("SELECT last_insert_rowid()")
    room_id = c.fetchone()[0]
    
    await update.message.reply_text(
        f"✅ ¡Sala {room_id} creada!\n"
        f"Esperando otro jugador...\n\n"
        f"⚠️ Cuando otro jugador se una con /unirse, el juego comenzará AUTOMÁTICAMENTE!"
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
        
        mensaje += "\n⚠️ Únete con /unirse - ¡El juego es AUTOMÁTICO!"
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

# Manejar botones
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('ver_'):
        room_id = data.split('_')[1]
        await query.edit_message_text(
            text="📋 **ESTADO DE LA MESA**\n\n"
                 "Esperando acciones de los jugadores...\n"
                 "Usa los botones para apostar o pasar."
        )
    
    elif data.startswith('apostar_'):
        parts = data.split('_')
        room_id = parts[1]
        cantidad = int(parts[2])
        
        await query.edit_message_text(
            text=f"✅ Apostaste {cantidad} fichas!\n"
                 f"Esperando al otro jugador..."
        )
    
    elif data.startswith('pasar_'):
        room_id = data.split('_')[1]
        await query.edit_message_text(
            text="🔄 Pasaste tu turno!\n"
                 "Esperando al otro jugador..."
        )
    
    elif data.startswith('retirarse_'):
        room_id = data.split('_')[1]
        await query.edit_message_text(
            text="🏳️ Te retiraste de la mano.\n"
                 "El otro jugador gana el bote."
        )

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
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Iniciar bot
    logger.info("🤖 Bot de Poker Automático iniciado...")
    application.run_polling()

if __name__ == '__main__':
    main()
