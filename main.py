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

# Mazo de cartas completo con emojis
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
                  player_actions TEXT DEFAULT '',
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

# Mostrar mesa con cartas y estado
async def mostrar_mesa(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT community_cards, pot, round, players, player_names, current_turn, current_bet FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return ""
    
    community = room[0] or ""
    pot = room[1]
    ronda = room[2]
    players = room[3].split(',') if room[3] else []
    player_names = room[4].split(',') if room[4] else []
    current_turn = room[5]
    current_bet = room[6]
    
    # Nombre de la ronda
    nombres_ronda = {
        'preflop': 'Pre-Flop',
        'flop': 'Flop',
        'turn': 'Turn',
        'river': 'River',
        'showdown': 'Showdown'
    }
    
    # Cartas comunitarias formateadas
    if community:
        cartas_lista = community.split(',')
        if len(cartas_lista) >= 3:
            cartas_display = f"{cartas_lista[0]}  {cartas_lista[1]}  {cartas_lista[2]}"
            if len(cartas_lista) >= 4:
                cartas_display += f"  |  {cartas_lista[3]}"
            if len(cartas_lista) >= 5:
                cartas_display += f"  |  {cartas_lista[4]}"
        else:
            cartas_display = "  ".join(cartas_lista)
    else:
        cartas_display = "---"
    
    # Encontrar jugador actual
    turno_nombre = ""
    for i, player_id in enumerate(players):
        if player_id == current_turn and i < len(player_names):
            turno_nombre = player_names[i]
    
    mensaje = f"""
🎰 **TEXAS HOLD'EM POKER** 🎰

💰 **Bote:** {pot} fichas
📊 **Ronda:** {nombres_ronda.get(ronda, ronda)}
🎯 **Turno de:** {turno_nombre}
🎫 **Apuesta actual:** {current_bet} fichas

🃏 **Cartas Comunitarias:**
{cartas_display}

👥 **Jugadores:**
"""
    
    for i, name in enumerate(player_names):
        if i < len(players):
            if players[i] == current_turn:
                mensaje += f"• 👑 {name} (TURNO)\n"
            else:
                mensaje += f"• {name}\n"
    
    conn.close()
    return mensaje

# Enviar mesa con botones CORREGIDO
async def enviar_mesa_con_botones(room_id, context, user_id_actual=None):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT players, current_turn, current_bet FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return
    
    players = room[0].split(',') if room[0] else []
    current_turn = room[1]
    current_bet = room[2]
    
    mensaje_mesa = await mostrar_mesa(room_id, context)
    
    # Para cada jugador
    for player_id in players:
        try:
            # Determinar qué botones mostrar
            if player_id == current_turn:
                # JUGADOR EN TURNO - muestra todos los botones
                keyboard = [
                    [
                        InlineKeyboardButton("📤 Subir 10", callback_data=f"raise_{room_id}_10"),
                        InlineKeyboardButton("📤 Subir 50", callback_data=f"raise_{room_id}_50")
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
                # JUGADOR ESPERANDO - solo botones básicos
                keyboard = [
                    [InlineKeyboardButton("👀 Ver Mesa", callback_data=f"view_{room_id}"),
                     InlineKeyboardButton("💰 Mis Fichas", callback_data=f"chips_{room_id}")]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Si es el jugador actual que hizo la acción, editar su mensaje
            if user_id_actual and str(user_id_actual) == player_id:
                # Buscar el último mensaje para editarlo
                try:
                    await context.bot.send_message(
                        chat_id=int(player_id),
                        text=mensaje_mesa,
                        reply_markup=reply_markup
                    )
                except:
                    pass
            else:
                # Para otros jugadores, enviar nuevo mensaje
                await context.bot.send_message(
                    chat_id=int(player_id),
                    text=mensaje_mesa,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error enviando a {player_id}: {e}")
    
    conn.close()

# Verificar si todos han actuado
async def verificar_ronda_completa(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT players, player_actions, player_folded FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return False
    
    players = room[0].split(',') if room[0] else []
    player_actions = room[1].split(',') if room[1] else []
    player_folded = room[2].split(',') if room[2] else []
    
    # Filtrar jugadores activos (no retirados)
    jugadores_activos = [p for p in players if p not in player_folded]
    
    # Si todos los activos han actuado
    if len(player_actions) >= len(jugadores_activos):
        conn.close()
        await asyncio.sleep(2)  # Pequeña pausa
        await avanzar_ronda(room_id, context)
        return True
    
    conn.close()
    return False

# Avanzar a siguiente ronda
async def avanzar_ronda(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT round, players, player_folded, pot, community_cards, private_cards FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    
    if not room:
        conn.close()
        return
    
    ronda_actual = room[0]
    players = room[1].split(',') if room[1] else []
    folded = room[2].split(',') if room[2] else []
    pot_actual = room[3]
    community_str = room[4] or ""
    private_str = room[5] or ""
    
    # Si solo queda 1 jugador activo, gana
    jugadores_activos = [p for p in players if p not in folded]
    
    if len(jugadores_activos) == 1:
        await finalizar_mano_por_retirada(room_id, jugadores_activos[0], pot_actual, context)
        conn.close()
        return
    
    # Determinar siguiente ronda
    nueva_ronda = ronda_actual
    cartas_comunidad = community_str.split(',') if community_str else []
    cartas_usadas = (private_str.split(',') if private_str else []) + cartas_comunidad
    
    mensaje_ronda = ""
    
    if ronda_actual == 'preflop':
        nueva_ronda = 'flop'
        # Repartir FLOP (3 cartas)
        mazo = [carta for carta in DECK if carta not in cartas_usadas]
        random.shuffle(mazo)
        flop = mazo[:3]
        cartas_comunidad = flop
        
        mensaje_ronda = "🃏 **¡FLOP REPARTIDO!** 🃏\nTres cartas comunitarias.\n\nNueva ronda de apuestas."
        
    elif ronda_actual == 'flop':
        nueva_ronda = 'turn'
        # Repartir TURN (1 carta)
        mazo = [carta for carta in DECK if carta not in cartas_usadas]
        random.shuffle(mazo)
        if mazo:
            cartas_comunidad.append(mazo[0])
        
        mensaje_ronda = "🃏 **¡TURN REPARTIDO!** 🃏\nCuarta carta comunitaria.\n\nNueva ronda de apuestas."
        
    elif ronda_actual == 'turn':
        nueva_ronda = 'river'
        # Repartir RIVER (1 carta)
        mazo = [carta for carta in DECK if carta not in cartas_usadas]
        random.shuffle(mazo)
        if mazo:
            cartas_comunidad.append(mazo[0])
        
        mensaje_ronda = "🃏 **¡RIVER REPARTIDO!** 🃏\nQuinta carta comunitaria.\n\nÚltima ronda de apuestas."
        
    elif ronda_actual == 'river':
        await showdown(room_id, context)
        conn.close()
        return
    
    # Actualizar base de datos
    c.execute("UPDATE game_rooms SET round=?, community_cards=?, current_bet=0, player_actions='', current_turn=? WHERE room_id=?", 
             (nueva_ronda, ','.join(cartas_comunidad), players[0], room_id))
    
    conn.commit()
    conn.close()
    
    # Enviar mensaje de nueva ronda
    for player_id in players:
        try:
            await context.bot.send_message(
                chat_id=int(player_id),
                text=mensaje_ronda
            )
        except:
            pass
    
    # Mostrar mesa actualizada CON BOTONES
    await enviar_mesa_con_botones(room_id, context)

# Finalizar mano por retirada
async def finalizar_mano_por_retirada(room_id, ganador_id, pot, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT username FROM users WHERE user_id=?", (int(ganador_id),))
    ganador_nombre = c.fetchone()[0]
    
    # Dar premio al ganador
    c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (pot, ganador_id))
    
    c.execute("SELECT players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
    room = c.fetchone()
    players = room[0].split(',') if room[0] else []
    player_names = room[1].split(',') if room[1] else []
    
    # Notificar a todos
    for i, player_id in enumerate(players):
        try:
            nombre = player_names[i] if i < len(player_names) else "Jugador"
            
            if player_id == ganador_id:
                msg = f"🏆 **¡FELICIDADES {nombre}!** 🏆\n\n¡Todos se retiraron!\nHas ganado {pot} fichas.\n\n🎰 Nueva mano en 5 segundos..."
            else:
                msg = f"😞 **{ganador_nombre} gana por retirada.**\n\nPremio: {pot} fichas\n\n🎰 Nueva mano en 5 segundos..."
            
            await context.bot.send_message(
                chat_id=int(player_id),
                text=msg
            )
        except:
            pass
    
    conn.close()
    
    # Esperar y reiniciar
    await asyncio.sleep(5)
    await reiniciar_para_nueva_mano(room_id, context)
    # Showdown - determinar ganador
async def showdown(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT players, player_names, private_cards, community_cards, pot FROM game_rooms WHERE room_id=?", (room_id,))
    data = c.fetchone()
    
    players = data[0].split(',') if data[0] else []
    player_names = data[1].split(',') if data[1] else []
    private_str = data[2] or ""
    community_str = data[3] or ""
    pot = data[4]
    
    # Cartas
    todas_cartas = private_str.split(',') if private_str else []
    cartas_com = community_str.split(',') if community_str else []
    
    # Determinar ganador (simplificado - por ahora aleatorio)
    ganador_idx = random.randint(0, len(players)-1)
    ganador_id = players[ganador_idx]
    ganador_nombre = player_names[ganador_idx] if ganador_idx < len(player_names) else "Jugador"
    
    # Dar premio
    c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (pot, ganador_id))
    
    # Mostrar resultados a cada jugador
    for i, player_id in enumerate(players):
        try:
            nombre = player_names[i] if i < len(player_names) else "Jugador"
            
            # Cartas de este jugador
            if i*2+1 < len(todas_cartas):
                carta1 = todas_cartas[i*2]
                carta2 = todas_cartas[i*2+1]
                cartas_jugador = f"{carta1}  {carta2}"
            else:
                cartas_jugador = "??  ??"
            
            cartas_com_display = "  ".join(cartas_com)
            
            if player_id == ganador_id:
                msg = f"🏆 **¡FELICIDADES {nombre}!** 🏆\n\n" \
                      f"Tus cartas: {cartas_jugador}\n" \
                      f"Mesa: {cartas_com_display}\n\n" \
                      f"Has ganado {pot} fichas!\n\n" \
                      f"🎰 **Nueva mano en 5 segundos...**"
            else:
                msg = f"😞 **{ganador_nombre} gana la mano.**\n\n" \
                      f"Tus cartas: {cartas_jugador}\n" \
                      f"Mesa: {cartas_com_display}\n\n" \
                      f"Premio: {pot} fichas\n\n" \
                      f"🎰 **Nueva mano en 5 segundos...**"
            
            await context.bot.send_message(
                chat_id=int(player_id),
                text=msg
            )
        except:
            pass
    
    conn.close()
    
    # Esperar y reiniciar
    await asyncio.sleep(5)
    await reiniciar_para_nueva_mano(room_id, context)

# Reiniciar para nueva mano automáticamente
async def reiniciar_para_nueva_mano(room_id, context):
    conn = sqlite3.connect('poker.db')
    c = conn.cursor()
    
    c.execute("SELECT players, player_names FROM game_rooms WHERE room_id=?", (room_id,))
    data = c.fetchone()
    
    if not data:
        conn.close()
        return
    
    players = data[0].split(',') if data[0] else []
    player_names = data[1].split(',') if data[1] else []
    
    # Verificar si alguien se quedó sin fichas
    c.execute("SELECT chips FROM users WHERE user_id IN (" + ",".join(["?"]*len(players)) + ")", players)
    chips_list = c.fetchall()
    
    alguien_sin_fichas = any(chips[0] <= 0 for chips in chips_list if chips)
    
    if alguien_sin_fichas:
        # Juego terminado
        for i, player_id in enumerate(players):
            try:
                nombre = player_names[i] if i < len(player_names) else "Jugador"
                c.execute("SELECT chips FROM users WHERE user_id=?", (player_id,))
                fichas = c.fetchone()[0]
                
                await context.bot.send_message(
                    chat_id=int(player_id),
                    text=f"💀 **¡JUEGO TERMINADO!** 💀\n\n"
                         f"{nombre}, te quedaste con {fichas} fichas.\n\n"
                         f"Crea nueva sala con /crear_sala"
                )
            except:
                pass
        
        # Resetear sala
        c.execute("UPDATE game_rooms SET status='waiting', current_players=1, players='', player_names='', private_cards='', community_cards='', pot=0, current_bet=0, current_turn=0, round='preflop', player_actions='', player_folded='' WHERE room_id=?", (room_id,))
    else:
        # Reiniciar para nueva mano
        c.execute("UPDATE game_rooms SET pot=0, current_bet=0, round='preflop', community_cards='', player_folded='', player_actions='', current_turn=? WHERE room_id=?", (players[0], room_id))
        
        # Iniciar nueva mano automáticamente
        await iniciar_juego_automatico(room_id, context)
    
    conn.commit()
    conn.close()

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
        # Mezclar mazo
        mazo = DECK.copy()
        random.shuffle(mazo)
        
        # Repartir 2 cartas a cada jugador
        cartas_repartidas = []
        for i in range(len(players)):
            if i*2+1 < len(mazo):
                cartas_repartidas.extend([mazo[i*2], mazo[i*2+1]])
        
        # Enviar cartas privadas a cada jugador
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
        
        # Guardar estado inicial
        c.execute("UPDATE game_rooms SET status='playing', private_cards=?, pot=?, current_bet=?, current_turn=?, round='preflop' WHERE room_id=?", 
                 (','.join(cartas_repartidas), pot, current_bet, players[1], room_id))
        
        conn.commit()
        
        # Mostrar mesa inicial CON BOTONES
        await enviar_mesa_con_botones(room_id, context)
    
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

# Manejar acciones del juego CORREGIDO
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith('view_'):
        room_id = data.split('_')[1]
        mensaje = await mostrar_mesa(room_id, context)
        await query.edit_message_text(mensaje)
    
    elif data.startswith('chips_'):
        room_id = data.split('_')[1]
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        c.execute("SELECT username, chips FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        if user:
            await query.edit_message_text(f"💰 {user[0]}, tienes {user[1]} fichas")
        conn.close()
    
    elif data.startswith('raise_'):
        parts = data.split('_')
        room_id = parts[1]
        cantidad = int(parts[2])
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        # Obtener estado actual
        c.execute("SELECT pot, players, current_bet, player_actions FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        if not room:
            conn.close()
            return
        
        pot = room[0]
        players = room[1].split(',') if room[1] else []
        old_bet = room[2]
        player_actions_str = room[3] or ""
        
        # Calcular aumento real
        aumento = cantidad - old_bet
        nuevo_pot = pot + aumento
        nueva_apuesta = cantidad
        
        # Actualizar bote y apuesta
        c.execute("UPDATE game_rooms SET pot=?, current_bet=? WHERE room_id=?", 
                 (nuevo_pot, nueva_apuesta, room_id))
        
        # Quitar fichas al jugador
        c.execute("UPDATE users SET chips = chips - ? WHERE user_id=?", (cantidad, user_id))
        
        # Cambiar turno
        idx = players.index(str(user_id))
        siguiente_idx = (idx + 1) % len(players)
        siguiente = players[siguiente_idx]
        
        c.execute("UPDATE game_rooms SET current_turn=? WHERE room_id=?", (siguiente, room_id))
        
        # Resetear acciones (porque subió la apuesta)
        c.execute("UPDATE game_rooms SET player_actions=? WHERE room_id=?", (str(user_id), room_id))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text(f"✅ Subiste la apuesta a {cantidad} fichas")
        # Actualizar mesa para TODOS con botones
        await enviar_mesa_con_botones(room_id, context, user_id)
    
    elif data.startswith('call_'):
        room_id = data.split('_')[1]
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        c.execute("SELECT current_bet, pot, players, player_actions FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        if not room:
            conn.close()
            return
        
        current_bet = room[0]
        pot = room[1]
        players = room[2].split(',') if room[2] else []
        player_actions_str = room[3] or ""
        
        # Igualar apuesta
        nuevo_pot = pot + current_bet
        c.execute("UPDATE game_rooms SET pot=? WHERE room_id=?", (nuevo_pot, room_id))
        c.execute("UPDATE users SET chips = chips - ? WHERE user_id=?", (current_bet, user_id))
        
        # Cambiar turno
        idx = players.index(str(user_id))
        siguiente_idx = (idx + 1) % len(players)
        siguiente = players[siguiente_idx]
        
        c.execute("UPDATE game_rooms SET current_turn=? WHERE room_id=?", (siguiente, room_id))
        
        # Agregar jugador a acciones
        acciones_lista = player_actions_str.split(',') if player_actions_str else []
        acciones_lista.append(str(user_id))
        c.execute("UPDATE game_rooms SET player_actions=? WHERE room_id=?", (','.join(acciones_lista), room_id))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text(f"✅ Igualaste la apuesta de {current_bet} fichas")
        # Actualizar mesa para TODOS con botones
        await enviar_mesa_con_botones(room_id, context, user_id)
        
        # Verificar si ronda completa
        await verificar_ronda_completa(room_id, context)
    
    elif data.startswith('check_'):
        room_id = data.split('_')[1]
        
        conn = sqlite3.connect('poker.db')
        c = conn.cursor()
        
        c.execute("SELECT players, player_actions FROM game_rooms WHERE room_id=?", (room_id,))
        room = c.fetchone()
        if not room:
            conn.close()
            return
        
        players = room[0].split(',') if room[0] else []
        player_actions_str = room[1] or ""
        
        # Cambiar turno
        idx = players.index(str(user_id))
        siguiente_idx = (idx + 1) % len(players)
        siguiente = players[siguiente_idx]
        
        c.execute("UPDATE game_rooms SET current_turn=? WHERE room_id=?", (siguiente, room_id))
        
        # Agregar jugador a acciones
        acciones_lista = player_actions_str.split(',') if player_actions_str else []
        acciones_lista.append(str(user_id))
        c.execute("UPDATE game_rooms SET player_actions=? WHERE room_id=?", (','.join(acciones_lista), room_id))
        
        conn.commit()
        conn.close()
        
        await query.edit_message_text("✅ Pasaste tu turno")
        # Actualizar mesa para TODOS con botones
        await enviar_mesa_con_botones(room_id, context, user_id)
        
        # Verificar si ronda completa
        await verificar_ronda_completa(room_id, context)
    
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
    logger.info("🤖 Bot de Poker TEXAS HOLD'EM COMPLETO iniciado...")
    application.run_polling()

if __name__ == '__main__':
    main()
