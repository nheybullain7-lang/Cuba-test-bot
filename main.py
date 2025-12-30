import os
import logging
import random
import asyncio
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
                  player_names TEXT DEFAULT '',
                  deck TEXT DEFAULT '',
                  community_cards TEXT DEFAULT '',
                  pot INTEGER DEFAULT 0,
                  current_bet INTEGER DEFAULT 0,
                  current_turn INTEGER DEFAULT 0,
                  round TEXT DEFAULT 'preflop',
                  bets TEXT DEFAULT '')''')
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

# Función para mostrar mesa
async def mostrar_mesa(room_id, context, mensaje_extra=""):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT community_cards, pot, round, players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return
    
    community_cards = room[0] or ""
    pot = room[1]
    round_name = room[2]
    players = room[3].split(',') if room[3] else []
    player_names = room[4].split(',') if room[4] else []
    
    # Traducir nombre de ronda
    rondas = {
        'preflop': 'Pre-Flop',
        'flop': 'Flop',
        'turn': 'Turn',
        'river': 'River',
        'showdown': 'Showdown'
    }
    round_display = rondas.get(round_name, round_name)
    
    # Formatear cartas comunitarias
    if community_cards:
        cards_display = ' '.join(community_cards.split(','))
    else:
        cards_display = "---"
    
    mensaje = f"""
🎰 **MESA DE POKER - {round_display}** 🎰

💰 **Bote:** {pot} fichas
🃏 **Cartas Comunitarias:** {cards_display}

👥 **Jugadores:**
"""
    
    for i, player_id in enumerate(players):
        if i < len(player_names):
            name = player_names[i]
            mensaje += f"• {name}\n"
    
    if mensaje_extra:
        mensaje += f"\n{mensaje_extra}"
    
    # Enviar a todos los jugadores
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
                text=mensaje,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error enviando mensaje a {player_id}: {e}")
    
    conn.close()

# Avanzar a siguiente ronda
async def avanzar_ronda(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT round, deck, players FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return
    
    current_round = room[0]
    deck_str = room[1] or ""
    deck = deck_str.split(',') if deck_str else []
    players = room[2].split(',') if room[2] else []
    
    new_round = current_round
    community_cards = ""
    
    c.execute("SELECT community_cards FROM game_rooms WHERE room_id=?", (room_id,))
    existing_cards = c.fetchone()[0] or ""
    existing_list = existing_cards.split(',') if existing_cards else []
    
    # Determinar siguiente ronda y repartir cartas
    if current_round == 'preflop' and len(deck) >= 3:
        # Flop: 3 cartas
        new_round = 'flop'
        flop_cards = deck[:3]
        community_cards = ','.join(flop_cards)
        deck = deck[3:]
        
        mensaje = "🃏 **¡FLOP REPARTIDO!** 🃏\nTres cartas comunitarias."
        
    elif current_round == 'flop' and len(deck) >= 1:
        # Turn: 1 carta
        new_round = 'turn'
        turn_card = deck[0]
        community_cards = ','.join(existing_list + [turn_card])
        deck = deck[1:]
        
        mensaje = "🃏 **¡TURN REPARTIDO!** 🃏\nCuarta carta comunitaria."
        
    elif current_round == 'turn' and len(deck) >= 1:
        # River: 1 carta
        new_round = 'river'
        river_card = deck[0]
        community_cards = ','.join(existing_list + [river_card])
        deck = deck[1:]
        
        mensaje = "🃏 **¡RIVER REPARTIDO!** 🃏\nQuinta carta comunitaria."
        
    elif current_round == 'river':
        # Showdown: determinar ganador
        new_round = 'showdown'
        
        # Simular ganador (por ahora aleatorio)
        ganador_id = random.choice(players)
        
        c.execute("SELECT username FROM users WHERE user_id=?", (int(ganador_id),))
        ganador_nombre = c.fetchone()[0] if c.fetchone() else "Jugador"
        
        c.execute("SELECT pot FROM game_rooms WHERE room_id=?", (room_id,))
        pot = c.fetchone()[0]
        
        # Dar fichas al ganador
        c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (pot, ganador_id))
        
        mensaje = f"🏆 **¡SHOWDOWN!** 🏆\n\n🎉 **{ganador_nombre} GANA {pot} FICHAS!** 🎉\n\nEl juego ha terminado."
        
        # Resetear sala
        c.execute("UPDATE game_rooms SET status='waiting', current_players=1, players='', deck='', community_cards='', pot=0, current_bet=0, round='preflop' WHERE room_id=?", (room_id,))
        
        # Enviar mensaje final
        for player_id in players:
            try:
                await context.bot.send_message(
                    chat_id=int(player_id),
                    text=mensaje
                )
            except:
                pass
        
        conn.commit()
        conn.close()
        return
    
    else:
        conn.close()
        return
    
    # Actualizar base de datos
    deck_str = ','.join(deck)
    c.execute("UPDATE game_rooms SET round=?, deck=?, community_cards=?, current_bet=0 WHERE room_id=?", 
             (new_round, deck_str, community_cards, room_id))
    
    # Resetear turno al primer jugador
    if players:
        c.execute("UPDATE game_rooms SET current_turn=? WHERE room_id=?", (players[0], room_id))
    
    conn.commit()
    conn.close()
    
    # Mostrar mesa actualizada
    await mostrar_mesa(room_id, context, mensaje)
    
    # Si es showdown, ya terminamos
    if new_round != 'showdown':
        # Esperar 3 segundos antes de siguiente acción
        await asyncio.sleep(3)

# Repartir cartas automáticamente
async def iniciar_juego_automatico(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    # Obtener jugadores
    c.execute("SELECT players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    players_str = room[0] if room else ""
    players = players_str.split(',') if players_str else []
    player_names = room[1].split(',') if room and room[1] else []
    
    if len(players) >= 2:
        # Mezclar mazo
        deck = DECK.copy()
        random.shuffle(deck)
        deck_str = ','.join(deck)
        
        # Repartir 2 cartas a cada jugador
        for i, player_id in enumerate(players):
            if i*2+1 < len(deck):
                mano = [deck[i*2], deck[i*2+1]]
                
                # Enviar cartas por privado
                try:
                    player_name = player_names[i] if i < len(player_names) else "Jugador"
                    await context.bot.send_message(
                        chat_id=int(player_id),
                        text=f"🎴 **TUS CARTAS PRIVADAS** 🎴\n\n"
                             f"🃏 {mano[0]}  🃏 {mano[1]}\n\n"
                             f"¡Buena suerte {player_name}! El juego ha comenzado."
                    )
                except:
                    pass
        
        # Configurar apuestas iniciales (ciegas)
        pot = 30  # 10 + 20 ciegas
        current_bet = 20
        
        # Guardar estado
        c.execute("UPDATE game_rooms SET status='playing', deck=?, pot=?, current_bet=?, current_turn=?, round='preflop' WHERE room_id=?",
                 (deck_str[6:], pot, current_bet, players[1], room_id))  # El jugador 2 (big blind) habla primero
        
        # Mostrar mesa inicial
        await mostrar_mesa(room_id, context, "💰 **Apuestas iniciales:** 10/20 ciegas\nEs el turno del Big Blind.")
        
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
        c.execute("SELECT players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
        room_data = c.fetchone()
        players_str = room_data[0] or ""
        player_names_str = room_data[1] or ""
        
        players_list = players_str.split(',') if players_str else []
        player_names_list = player_names_str.split(',') if player_names_str else []
        
        players_list.append(str(user_id))
        player_names_list.append(username)
        
        new_players_str = ','.join(players_list)
        new_player_names_str = ','.join(player_names_list)
        
        c.execute("UPDATE game_rooms SET current_players=?, players=?, player_names=? WHERE room_id=?",
                 (current_players, new_players_str, new_player_names_str, room_id))
        
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
    user = c.fetchone()
    
    if not user:
        await update.message.reply_text("❌ Debes registrarte primero con /registro_test [nombre]")
        conn.close()
        return
    
    username = user[1]
    
    # Crear sala
    c.execute("INSERT INTO game_rooms (creator_id, players, player_names) VALUES (?, ?, ?)", 
             (user_id, str(user_id), username))
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
    user_id = query.from_user.id
    
    if data.startswith('ver_'):
        room_id = data.split('_')[1]
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        c.execute("SELECT community_cards, pot, round FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        
        if room:
            community_cards = room[0] or "---"
            pot = room[1]
            round_name = room[2]
            
            await query.edit_message_text(
                text=f"🔍 **VISIÓN ACTUAL**\n\n"
                     f"Ronda: {round_name}\n"
                     f"Bote: {pot} fichas\n"
                     f"Cartas comunitarias: {community_cards}"
            )
        
        conn.close()
    
    elif data.startswith('apostar_'):
        parts = data.split('_')
        room_id = parts[1]
        cantidad = int(parts[2])
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        # Actualizar bote
        c.execute("SELECT pot FROM game_rooms WHERE room_id=?", (room_id,))
        pot_actual = c.fetchone()[0]
        nuevo_pot = pot_actual + cantidad
        
        c.execute("UPDATE game_rooms SET pot=? WHERE room_id=?", (nuevo_pot, room_id))
        
        # Verificar si ambos han apostado en esta ronda
        c.execute("SELECT players, round FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        players = room[0].split(',') if room[0] else []
        current_round = room[1]
        
        await query.edit_message_text(
            text=f"✅ Apostaste {cantidad} fichas!\n"
                 f"Bote actual: {nuevo_pot} fichas\n\n"
                 f"Esperando siguiente acción..."
        )
        
        conn.commit()
        conn.close()
        
        # Esperar y avanzar ronda
        await asyncio.sleep(2)
        await avanzar_ronda(room_id, context)
    
    elif data.startswith('pasar_'):
        room_id = data.split('_')[1]
        
        await query.edit_message_text(
            text="🔄 Pasaste tu turno!\n"
                 "Esperando al otro jugador..."
        )
        
        # Esperar y avanzar
        await asyncio.sleep(2)
        await avanzar_ronda(room_id, context)
    
    elif data.startswith('retirarse_'):
        room_id = data.split('_')[1]
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        # Obtener jugadores
        c.execute("SELECT players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        players = room[0].split(',') if room[0] else []
        player_names = room[1].split(',') if room[1] else []
        
        # Encontrar oponente
        oponente_id = None
        oponente_nombre = None
        for i, player_id in enumerate(players):
            if int(player_id) != user_id:
                oponente_id = player_id
                if i < len(player_names):
                    oponente_nombre = player_names[i]
        
        # Dar bote al oponente
        c.execute("SELECT pot FROM game_rooms WHERE room_id=?", (room_id,))
        pot = c.fetchone()[0]
        
        if oponente_id:
            c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (pot, oponente_id))
        
        # Resetear sala
        c.execute("UPDATE game_rooms SET status='waiting', current_players=1, players='', deck='', community_cards='', pot=0, current_bet=0, round='preflop' WHERE room_id=?", (room_id,))
        
        conn.commit()
        conn.close()
        
        mensaje = f"🏳️ Te retiraste de la mano.\n"
        if oponente_nombre:
            mensaje += f"🏆 **{oponente_nombre} gana {pot} fichas!**"
        
        await query.edit_message_text(text=mensaje)

def main():
    # Inicializar base de datos
    init_db()
    
    # Obtener token
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        logger.error("❌ No se encontró BOT_TOKEN en variables de entorno")
        return
    
    # Crear aplicación
    ap
