import os
import logging
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import sqlite3

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
                  private_cards TEXT DEFAULT '',
                  community_cards TEXT DEFAULT '',
                  pot INTEGER DEFAULT 0,
                  current_bet INTEGER DEFAULT 0,
                  current_turn INTEGER DEFAULT 0,
                  round TEXT DEFAULT 'preflop',
                  player_bets TEXT DEFAULT '',
                  player_folded TEXT DEFAULT '')''')
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
    
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if c.fetchone():
        await update.message.reply_text(f"✅ Ya estás registrado como {username}!")
    else:
        c.execute("INSERT INTO users (user_id, username, chips) VALUES (?, ?, 1000)",
                 (user_id, username))
        conn.commit()
        await update.message.reply_text(f"✅ Registrado como {username} con 1000 fichas!")
    
    conn.close()

# Evaluar mano de poker
def evaluar_mano(cartas):
    # Convertir cartas a formato evaluable
    valores = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 
               '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
    
    # Por ahora, devolver valor aleatorio (implementación simplificada)
    return random.randint(1, 10000)

# Mostrar mesa
async def mostrar_mesa(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT community_cards, pot, round, players, player_names, current_turn FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return
    
    community = room[0] or ""
    pot = room[1]
    ronda = room[2]
    players = room[3].split(',') if room[3] else []
    player_names = room[4].split(',') if room[4] else []
    current_turn = room[5]
    
    # Nombre de la ronda
    nombres_ronda = {
        'preflop': 'Pre-Flop',
        'flop': 'Flop',
        'turn': 'Turn',
        'river': 'River',
        'showdown': 'Showdown'
    }
    
    # Cartas comunitarias
    cartas_display = " ".join(community.split(',')) if community else "---"
    
    # Encontrar jugador actual
    turno_nombre = ""
    for i, player_id in enumerate(players):
        if player_id == current_turn and i < len(player_names):
            turno_nombre = player_names[i]
    
    mensaje = f"""
🎰 **TEXAS HOLD'EM POKER** 🎰

💰 **Bote:** {pot} fichas
🃏 **Cartas Comunitarias:** {cartas_display}
📊 **Ronda:** {nombres_ronda.get(ronda, ronda)}
🎯 **Turno de:** {turno_nombre}

👥 **Jugadores:**
"""
    
    for i, name in enumerate(player_names):
        if i < len(players):
            if players[i] == current_turn:
                mensaje += f"• 👑 {name} (TURNO)\n"
            else:
                mensaje += f"• {name}\n"
    
    # Botones para el jugador en turno
    current_user = context._user_id if hasattr(context, '_user_id') else None
    
    if current_user and current_user == current_turn:
        keyboard = [
            [
                InlineKeyboardButton("📤 Apostar 10", callback_data=f"bet_{room_id}_10"),
                InlineKeyboardButton("📤 Apostar 50", callback_data=f"bet_{room_id}_50")
            ],
            [
                InlineKeyboardButton("✅ Igualar", callback_data=f"call_{room_id}"),
                InlineKeyboardButton("🔄 Pasar", callback_data=f"check_{room_id}")
            ],
            [
                InlineKeyboardButton("🏳️ Retirarse", callback_data=f"fold_{room_id}"),
                InlineKeyboardButton("👀 Ver Mesa", callback_data=f"view_{room_id}")
            ]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("👀 Ver Mesa", callback_data=f"view_{room_id}"),
             InlineKeyboardButton("💰 Ver Fichas", callback_data=f"chips_{room_id}")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Enviar a todos los jugadores
    for player_id in players:
        try:
            await context.bot.send_message(
                chat_id=int(player_id),
                text=mensaje,
                reply_markup=reply_markup
            )
        except:
            pass
    
    conn.close()
    # Avanzar ronda
async def avanzar_ronda(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT round, players, player_folded FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return
    
    ronda_actual = room[0]
    players = room[1].split(',') if room[1] else []
    folded = room[2].split(',') if room[2] else []
    
    # Si solo queda 1 jugador no doblado, gana
    jugadores_activos = [p for p in players if p not in folded]
    
    if len(jugadores_activos) == 1:
        # Ganador por retirada
        ganador_id = jugadores_activos[0]
        c.execute("SELECT pot FROM game_rooms WHERE room_id=?", (room_id,))
        pot = c.fetchone()[0]
        
        c.execute("SELECT username FROM users WHERE user_id=?", (int(ganador_id),))
        ganador_nombre = c.fetchone()[0]
        
        c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (pot, ganador_id))
        
        # Mensaje final
        for player_id in players:
            try:
                await context.bot.send_message(
                    chat_id=int(player_id),
                    text=f"🏆 **¡{ganador_nombre} GANA!** 🏆\n\n"
                         f"Ganador por retirada del oponente.\n"
                         f"Premio: {pot} fichas\n\n"
                         f"🎰 Nueva partida disponible con /crear_sala"
                )
            except:
                pass
        
        # Resetear sala
        c.execute("UPDATE game_rooms SET status='waiting', current_players=1, players='', player_names='', private_cards='', community_cards='', pot=0, current_bet=0, current_turn=0, round='preflop', player_bets='', player_folded='' WHERE room_id=?", (room_id,))
        
        conn.commit()
        conn.close()
        return
    
    # Determinar siguiente ronda
    nueva_ronda = ronda_actual
    if ronda_actual == 'preflop':
        nueva_ronda = 'flop'
        # Repartir flop (3 cartas)
        c.execute("SELECT private_cards FROM game_rooms WHERE room_id=?", (room_id,))
        private_str = c.fetchone()[0] or ""
        cartas = private_str.split(',') if private_str else []
        cartas_usadas = len(cartas) * 2  # 2 cartas por jugador
        
        # Agregar 3 cartas comunitarias
        mazo = DECK.copy()
        random.shuffle(mazo)
        flop = mazo[cartas_usadas:cartas_usadas+3]
        c.execute("UPDATE game_rooms SET community_cards=?, round=? WHERE room_id=?", 
                 (','.join(flop), nueva_ronda, room_id))
        
        mensaje = "🃏 **¡FLOP REPARTIDO!** 🃏\n3 cartas comunitarias."
        
    elif ronda_actual == 'flop':
        nueva_ronda = 'turn'
        # Agregar turn (1 carta)
        c.execute("SELECT community_cards FROM game_rooms WHERE room_id=?", (room_id,))
        community_str = c.fetchone()[0] or ""
        cartas_com = community_str.split(',') if community_str else []
        
        mazo = DECK.copy()
        random.shuffle(mazo)
        # Encontrar carta no usada
        for carta in mazo:
            if carta not in cartas_com:
                cartas_com.append(carta)
                break
        
        c.execute("UPDATE game_rooms SET community_cards=?, round=? WHERE room_id=?", 
                 (','.join(cartas_com), nueva_ronda, room_id))
        
        mensaje = "🃏 **¡TURN REPARTIDO!** 🃏\n4ta carta comunitaria."
        
    elif ronda_actual == 'turn':
        nueva_ronda = 'river'
        # Agregar river (1 carta)
        c.execute("SELECT community_cards FROM game_rooms WHERE room_id=?", (room_id,))
        community_str = c.fetchone()[0] or ""
        cartas_com = community_str.split(',') if community_str else []
        
        mazo = DECK.copy()
        random.shuffle(mazo)
        for carta in mazo:
            if carta not in cartas_com:
                cartas_com.append(carta)
                break
        
        c.execute("UPDATE game_rooms SET community_cards=?, round=? WHERE room_id=?", 
                 (','.join(cartas_com), nueva_ronda, room_id))
        
        mensaje = "🃏 **¡RIVER REPARTIDO!** 🃏\n5ta carta comunitaria."
        
    elif ronda_actual == 'river':
        nueva_ronda = 'showdown'
        # Determinar ganador real
        c.execute("SELECT players, private_cards, community_cards FROM game_rooms WHERE room_id=?", (room_id,))
        data = c.fetchone()
        players = data[0].split(',') if data[0] else []
        private_str = data[1] or ""
        community_str = data[2] or ""
        
        # Cartas de cada jugador
        todas_cartas = private_str.split(',') if private_str else []
        cartas_com = community_str.split(',') if community_str else []
        
        # Evaluar manos
        mejores_manos = []
        for i in range(0, len(todas_cartas), 2):
            if i+1 < len(todas_cartas):
                cartas_jugador = [todas_cartas[i], todas_cartas[i+1]] + cartas_com
                valor = evaluar_mano(cartas_jugador)
                player_idx = i // 2
                if player_idx < len(players):
                    mejores_manos.append((players[player_idx], valor))
        
        # Encontrar ganador
        if mejores_manos:
            ganador_id = max(mejores_manos, key=lambda x: x[1])[0]
            
            c.execute("SELECT pot FROM game_rooms WHERE room_id=?", (room_id,))
            pot = c.fetchone()[0]
            
            c.execute("SELECT username FROM users WHERE user_id=?", (int(ganador_id),))
            ganador_nombre = c.fetchone()[0]
            
            c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (pot, ganador_id))
            
            # Mensaje final
            for player_id in players:
                try:
                    if player_id == ganador_id:
                        msg = f"🏆 **¡FELICIDADES {ganador_nombre}!** 🏆\n\nHas ganado {pot} fichas!\n\n🎰 Nueva partida disponible"
                    else:
                        msg = f"😞 **{ganador_nombre} gana la mano.**\n\nPremio: {pot} fichas\n\n🎰 Nueva partida disponible"
                    
                    await context.bot.send_message(
                        chat_id=int(player_id),
                        text=msg
                    )
                except:
                    pass
            
            # Resetear sala
            c.execute("UPDATE game_rooms SET status='waiting', current_players=1, players='', player_names='', private_cards='', community_cards='', pot=0, current_bet=0, current_turn=0, round='preflop', player_bets='', player_folded='' WHERE room_id=?", (room_id,))
            
            conn.commit()
            conn.close()
            return
    
    # Resetear apuestas para nueva ronda
    c.execute("UPDATE game_rooms SET current_bet=0, player_bets='', current_turn=? WHERE room_id=?", 
             (players[0], room_id))
    
    conn.commit()
    conn.close()
    
    # Mostrar mesa
    await mostrar_mesa(room_id, context)

# Iniciar juego automático
async def iniciar_juego_automatico(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return
    
    players = room[0].split(',') if room[0] else []
    player_names = room[1].split(',') if room[1] else []
    
    if len(players) >= 2:
        # Mezclar y repartir cartas
        mazo = DECK.copy()
        random.shuffle(mazo)
        
        # Repartir 2 cartas a cada jugador
        cartas_repartidas = []
        for i in range(len(players)):
            if i*2+1 < len(mazo):
                cartas_repartidas.extend([mazo[i*2], mazo[i*2+1]])
        
        # Enviar cartas privadas
        for i, player_id in enumerate(players):
            if i*2+1 < len(cartas_repartidas):
                carta1 = cartas_repartidas[i*2]
                carta2 = cartas_repartidas[i*2+1]
                
                try:
                    nombre = player_names[i] if i < len(player_names) else "Jugador"
                    await context.bot.send_message(
                        chat_id=int(player_id),
                        text=f"🎴 **TUS CARTAS PRIVADAS** 🎴\n\n"
                             f"🃏 {carta1}  🃏 {carta2}\n\n"
                             f"¡Buena suerte {nombre}!\n"
                             f"Mantén estas cartas en secreto."
                    )
                except:
                    pass
        
        # Configurar ciegas
        small_blind = 10
        big_blind = 20
        
        # Quitar fichas por ciegas
        if len(players) >= 2:
            c.execute("UPDATE users SET chips = chips - ? WHERE user_id=?", (small_blind, players[0]))
            c.execute("UPDATE users SET chips = chips - ? WHERE user_id=?", (big_blind, players[1]))
        
        pot = small_blind + big_blind
        current_bet = big_blind
        
        # Guardar estado
        c.execute("UPDATE game_rooms SET status='playing', private_cards=?, pot=?, current_bet=?, current_turn=?, round='preflop' WHERE room_id=?", 
                 (','.join(cartas_repartidas), pot, current_bet, players[1], room_id))
        
        conn.commit()
        
        # Mostrar mesa inicial
        await mostrar_mesa(room_id, context)
    
    conn.close()

# Comando /unirse
async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    
    if not user:
        await update.message.reply_text("❌ Debes registrarte primero con /registro_test [nombre]")
        conn.close()
        return
    
    username = user[1]
    
    # Buscar sala
    c.execute("SELECT * FROM game_rooms WHERE status='waiting' AND current_players < max_players LIMIT 1")
    room = c.fetchone()
    
    if room:
        room_id = room[0]
        current_players = room[3] + 1
        
        # Actualizar jugadores
        c.execute("SELECT players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
        data = c.fetchone()
        players_str = data[0] or ""
        names_str = data[1] or ""
        
        players = players_str.split(',') if players_str else []
        names = names_str.split(',') if names_str else []
        
        players.append(str(user_id))
        names.append(username)
        
        c.execute("UPDATE game_rooms SET current_players=?, players=?, player_names=? WHERE room_id=?",
                 (current_players, ','.join(players), ','.join(names), room_id))
        
        await update.message.reply_text(
            f"✅ ¡{username} se unió a la sala {room_id}!\n"
            f"Jugadores: {current_players}/2\n\n"
            f"⚠️ ¡El juego comienza AUTOMÁTICAMENTE con 2 jugadores!"
        )
        
        # Iniciar juego si hay 2
        if current_players >= 2:
            c.execute("UPDATE game_rooms SET status='starting' WHERE room_id=?", (room_id,))
            conn.commit()
            conn.close()
            
            await update.message.reply_text("🎰 ¡2 JUGADORES! Iniciando partida...")
            await asyncio.sleep(2)
            await iniciar_juego_automatico(room_id, context)
        else:
            conn.commit()
            conn.close()
    else:
        await update.message.reply_text("📝 No hay salas. Crea una con /crear_sala")
        conn.close()

# Comando /crear_sala
async def crear_sala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
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
        f"⚠️ Cuando otro se una con /unirse, el poker comienza AUTOMÁTICAMENTE!"
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

# Manejar acciones del juego
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith('view_'):
        room_id = data.split('_')[1]
        await mostrar_mesa(room_id, context)
    
    elif data.startswith('chips_'):
        room_id = data.split('_')[1]
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        c.execute("SELECT username, chips FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        if user:
            await query.edit_message_text(f"💰 {user[0]}, tienes {user[1]} fichas")
        conn.close()
    
    elif data.startswith('bet_'):
        parts = data.split('_')
        room_id = parts[1]
        cantidad = int(parts[2])
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        # Actualizar bote
        c.execute("SELECT pot, players FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        pot = room[0]
        players = room[1].split(',') if room[1] else []
        
        nuevo_pot = pot + cantidad
        c.execute("UPDATE game_rooms SET pot=?, current_bet=? WHERE room_id=?", 
                 (nuevo_pot, cantidad, room_id))
        
        # Quitar fichas al jugador
        c.execute("UPDATE users SET chips = chips - ? WHERE user_id=?", (cantidad, user_id))
        
        # Cambiar turno
        idx = players.index(str(user_id))
        siguiente_idx = (idx + 1) % len(players)
        siguiente = players[siguiente_idx]
        
        c.execute("UPDATE game_rooms SET current_turn=? WHERE room_id=?", (siguiente, room_id))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text(f"✅ Apostaste {cantidad} fichas")
        await mostrar_mesa(room_id, context)
    
    elif data.startswith('call_'):
        room_id = data.split('_')[1]
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        c.execute("SELECT current_bet, pot, players FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        current_bet = room[0]
        pot = room[1]
        players = room[2].split(',') if room[2] else []
        
        # Igualar apuesta
        nuevo_pot = pot + current_bet
        c.execute("UPDATE game_rooms SET pot=? WHERE room_id=?", (nuevo_pot, room_id))
        c.execute("UPDATE users SET chips = chips - ? WHERE user_id=?", (current_bet, user_id))
        
        # Cambiar turno
        idx = players.index(str(user_id))
        siguiente_idx = (idx + 1) % len(players)
        siguiente = players[siguiente_idx]
        
        c.execute("UPDATE game_rooms SET current_turn=? WHERE room_id=?", (siguiente, room_id))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text(f"✅ Igualaste la apuesta de {current_bet} fichas")
        await mostrar_mesa(room_id, context)
    
    elif data.startswith('check_'):
        room_id = data.split('_')[1]
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        c.execute("SELECT players FROM game_rooms WHERE room_id=?", (room_id,))
        players = c.fetchone()[0].split(',') if c.fetchone()[0] else []
        
        # Cambiar turno
        idx = players.index(str(user_id))
        siguiente_idx = (idx + 1) % len(players)
        siguiente = players[siguiente_idx]
        
        c.execute("UPDATE game_rooms SET current_turn=? WHERE room_id=?", (siguiente, room_id))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text("✅ Pasaste tu turno")
        await mostrar_mesa(room_id, context)
    
    elif data.startswith('fold_'):
        room_id = data.split('_')[1]
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        # Agregar a lista de retirados
        c.execute("SELECT player_folded FROM game_rooms WHERE room_id=?", (room_id,))
        folded_str = c.fetchone()[0] or ""
        folded = folded_str.split(',') if folded_str else []
        folded.append(str(user_id))
        
        c.execute("UPDATE game_rooms SET player_folded=? WHERE room_id=?", 
                 (','.join(folded), room_id))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text("🏳️ Te retiraste de la mano")
        await avanzar_ronda(room_id, context)

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
    logger.info("🤖 Bot de Poker TEXAS HOLD'EM iniciado...")
    application.run_polling()

if __name__ == '__main__':
    main()
