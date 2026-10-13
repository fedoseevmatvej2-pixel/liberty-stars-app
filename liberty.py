import asyncio
import sqlite3
import os
import random
import string
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = "8229198388:AAEMEtKRLHMzLU8S2xk2bsQ5NvoIbsn1cJQ"
ADMIN_IDS = [6298571875, 7972590840]
DB_FILE = os.path.expanduser("~/liberty.db")
START_BONUS = 10
REF_BONUS = 5
MIN_DEPOSIT = 5
MIN_BET = 1

bot = Bot(API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    c = db(); cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT, full_name TEXT,
        balance INTEGER DEFAULT 0,
        deposited INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0,
        games_won INTEGER DEFAULT 0,
        referrer_id INTEGER,
        ref_earned INTEGER DEFAULT 0,
        ref_paid INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS promos(
        code TEXT PRIMARY KEY, amount INTEGER, uses_left INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS promo_uses(
        code TEXT, user_id INTEGER, PRIMARY KEY(code,user_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, amount INTEGER, type TEXT, note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.commit(); c.close()

db_init()

def get_user(uid):
    c = db(); cur = c.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone(); c.close(); return r

def create_user(uid, username, full_name, referrer_id=None):
    c = db(); cur = c.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id,username,full_name,balance,referrer_id) VALUES(?,?,?,?,?)",
                (uid, username, full_name, START_BONUS, referrer_id))
    c.commit(); c.close()
    add_trx(uid, START_BONUS, "bonus", "Стартовый бонус")

def add_balance(uid, amount):
    c = db(); cur = c.cursor()
    cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
    c.commit(); c.close()

def add_trx(uid, amount, ttype, note=""):
    c = db(); cur = c.cursor()
    cur.execute("INSERT INTO transactions(user_id,amount,type,note) VALUES(?,?,?,?)",
                (uid, amount, ttype, note))
    c.commit(); c.close()

def is_admin(uid):
    return uid in ADMIN_IDS

def stat_game(uid, won=False):
    c = db(); cur = c.cursor()
    cur.execute("UPDATE users SET games_played=games_played+1 WHERE user_id=?", (uid,))
    if won:
        cur.execute("UPDATE users SET games_won=games_won+1 WHERE user_id=?", (uid,))
    c.commit(); c.close()

def pay_referrer(uid):
    u = get_user(uid)
    if not u or not u["referrer_id"]: return
    if u["deposited"] < MIN_DEPOSIT or u["games_played"] < 1 or u["ref_paid"] == 1: return
    rid = u["referrer_id"]
    if not get_user(rid): return
    add_balance(rid, REF_BONUS)
    c = db(); cur = c.cursor()
    cur.execute("UPDATE users SET ref_earned=ref_earned+? WHERE user_id=?", (REF_BONUS, rid))
    cur.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (uid,))
    c.commit(); c.close()
    add_trx(rid, REF_BONUS, "ref", f"Реферал {uid}")
    try:
        asyncio.create_task(bot.send_message(rid, f"🎉 +{REF_BONUS}⭐ за активного реферала!"))
    except Exception: pass
# ============ КЛАВИАТУРЫ ============
def bottom_menu(uid):
    rows = [
        [InlineKeyboardButton(text="🎮 Игры", callback_data="tab_games"),
         InlineKeyboardButton(text="💰 Баланс", callback_data="tab_balance"),
         InlineKeyboardButton(text="👤 Профиль", callback_data="tab_profile")],
    ]
    if is_admin(uid):
        rows.append([InlineKeyboardButton(text="🛠 Админ", callback_data="tab_admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def games_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Слоты Liberty", callback_data="g_slots"),
         InlineKeyboardButton(text="💼 Слоты Бизнеса", callback_data="g_slots_biz")],
        [InlineKeyboardButton(text="💣 Мины", callback_data="g_mines"),
         InlineKeyboardButton(text="🎲 Кубик", callback_data="g_dice")],
        [InlineKeyboardButton(text="🎡 Рулетка", callback_data="g_roulette"),
         InlineKeyboardButton(text="🪙 Монетка", callback_data="g_coin")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def balance_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Пополнить", callback_data="deposit_menu")],
        [InlineKeyboardButton(text="🎟 Промокод", callback_data="promo_enter")],
        [InlineKeyboardButton(text="📜 История", callback_data="history")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def deposit_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 5", callback_data="dep_5"),
         InlineKeyboardButton(text="⭐ 10", callback_data="dep_10"),
         InlineKeyboardButton(text="⭐ 25", callback_data="dep_25")],
        [InlineKeyboardButton(text="⭐ 50", callback_data="dep_50"),
         InlineKeyboardButton(text="⭐ 100", callback_data="dep_100"),
         InlineKeyboardButton(text="⭐ 250", callback_data="dep_250")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="dep_custom")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="tab_balance")],
    ])

def profile_menu(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Моя реф-ссылка", callback_data="show_ref")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="adm_create_promo")],
        [InlineKeyboardButton(text="💰 Выдать звёзды", callback_data="adm_give"),
         InlineKeyboardButton(text="💸 Снять звёзды", callback_data="adm_take")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def back_kb(to="tab_games"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=to)]
    ])

def bet_kb(game, back_to="tab_games"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1⭐", callback_data=f"{game}_bet_1"),
         InlineKeyboardButton(text="5⭐", callback_data=f"{game}_bet_5"),
         InlineKeyboardButton(text="10⭐", callback_data=f"{game}_bet_10")],
        [InlineKeyboardButton(text="25⭐", callback_data=f"{game}_bet_25"),
         InlineKeyboardButton(text="50⭐", callback_data=f"{game}_bet_50"),
         InlineKeyboardButton(text="Всё", callback_data=f"{game}_bet_all")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_to)],
    ])

# ============ СТАРТ ============
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    uid = msg.from_user.id
    args = msg.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].replace("ref_", ""))
            if ref_id == uid: ref_id = None
        except Exception: ref_id = None

    user = get_user(uid)
    if not user:
        create_user(uid, msg.from_user.username, msg.from_user.full_name, referrer_id=ref_id)
        if ref_id and get_user(ref_id):
            try:
                await bot.send_message(ref_id, f"👥 Новый реферал: {msg.from_user.full_name}")
            except Exception: pass
    text = (f"✨ <b>Liberty Stars</b> ✨\n\n"
            f"Добро пожаловать, {msg.from_user.full_name}!\n"
            f"Используй панель снизу:")
    await msg.answer(text, reply_markup=bottom_menu(uid), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def cb_back(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = f"✨ <b>Liberty Stars</b> ✨\n\nБаланс: <b>{u['balance']}⭐</b>\n\nВыбери раздел:"
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=bottom_menu(cb.from_user.id), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=bottom_menu(cb.from_user.id), parse_mode="HTML")

# ============ ИГРЫ (меню) ============
@dp.callback_query(F.data == "tab_games")
async def cb_games(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"🎮 <b>Игры Liberty Stars</b>\n\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"Выбери игру:")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=games_menu(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=games_menu(), parse_mode="HTML")

# ============ БАЛАНС ============
@dp.callback_query(F.data == "tab_balance")
async def cb_balance(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"💰 <b>Баланс</b>\n\n"
            f"Текущий: <b>{u['balance']}⭐</b>\n"
            f"Пополнено: {u['deposited']}⭐\n\n"
            f"Минимум пополнения: {MIN_DEPOSIT}⭐")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=balance_menu(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=balance_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "deposit_menu")
async def cb_deposit(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text("💰 <b>Пополнение</b>\n\nВыбери сумму:",
                                    reply_markup=deposit_menu(), parse_mode="HTML")
    except Exception:
        await cb.message.answer("💰 <b>Пополнение</b>\n\nВыбери сумму:",
                                 reply_markup=deposit_menu(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dep_") & ~F.data.in_({"dep_custom"}))
async def cb_dep_amount(cb: CallbackQuery):
    try:
        amount = int(cb.data.split("_")[1])
    except Exception:
        await cb.answer("Ошибка"); return
    if amount < MIN_DEPOSIT:
        await cb.answer(f"Минимум {MIN_DEPOSIT}⭐", show_alert=True); return
    await send_invoice(cb, amount)

@dp.callback_query(F.data == "dep_custom")
async def cb_dep_custom(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.answer(f"✏️ Напиши сумму (от {MIN_DEPOSIT}):")
    await state.set_state("dep_custom")

@dp.message(State("dep_custom"))
async def dep_custom_amount(msg: Message, state: FSMContext):
    if not msg.text.strip().isdigit():
        await msg.answer("❗ Нужно число:"); return
    amount = int(msg.text.strip())
    if amount < MIN_DEPOSIT or amount > 100000:
        await msg.answer(f"❗ Сумма от {MIN_DEPOSIT} до 100000:"); return
    await state.clear()
    await send_invoice_msg(msg, amount)

async def send_invoice(cb, amount):
    try:
        await bot.send_invoice(
            chat_id=cb.from_user.id,
            title="Пополнение Liberty Stars",
            description=f"Зачислить {amount} звёзд",
            payload=f"topup|{cb.from_user.id}|{amount}",
            provider_token="", currency="XTR",
prices=[LabeledPrice(label=f"{amount} звёзд", amount=amount)],
        )
        await cb.message.answer(f"💫 Чек на {amount}⭐ отправлен в личку.")
    except Exception as e:
        print("invoice err:", e)
        await cb.message.answer("❌ Напиши боту /start в личке и попробуй снова.")

async def send_invoice_msg(msg, amount):
    try:
        await bot.send_invoice(
            chat_id=msg.from_user.id,
            title="Пополнение Liberty Stars",
            description=f"Зачислить {amount} звёзд",
            payload=f"topup|{msg.from_user.id}|{amount}",
            provider_token="", currency="XTR",
            prices=[LabeledPrice(label=f"{amount} звёзд", amount=amount)],
        )
        await msg.answer(f"💫 Чек на {amount}⭐ отправлен.")
    except Exception as e:
        print("invoice err:", e)
        await msg.answer("❌ Напиши /start в личке и попробуй снова.")

@dp.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def on_paid(msg: Message):
    payload = msg.successful_payment.invoice_payload
    if not payload.startswith("topup|"): return
    parts = payload.split("|")
    uid = int(parts[1]); amount = int(parts[2])
    if not get_user(uid):
        create_user(uid, msg.from_user.username, msg.from_user.full_name)
    add_balance(uid, amount)
    c = db(); cur = c.cursor()
    cur.execute("UPDATE users SET deposited=deposited+? WHERE user_id=?", (amount, uid))
    c.commit(); c.close()
    add_trx(uid, amount, "deposit", "Пополнение Stars")
    await msg.answer(f"✅ Пополнено на <b>{amount}⭐</b>!", parse_mode="HTML")
    for adm in ADMIN_IDS:
        try:
            await bot.send_message(adm, f"💰 Пополнение\n{msg.from_user.full_name}\nID: {uid}\n{amount}⭐")
        except Exception: pass
    pay_referrer(uid)

# ============ ПРОМОКОД ============
@dp.callback_query(F.data == "promo_enter")
async def cb_promo_enter(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.answer("🎟 Введи промокод:")
    await state.set_state("promo_code")

@dp.message(State("promo_code"))
async def promo_code_handler(msg: Message, state: FSMContext):
    code = msg.text.strip().upper()
    c = db(); cur = c.cursor()
    cur.execute("SELECT amount,uses_left FROM promos WHERE code=?", (code,))
    row = cur.fetchone()
    if not row:
        await msg.answer("❌ Промокод не найден."); await state.clear(); c.close(); return
    cur.execute("SELECT 1 FROM promo_uses WHERE code=? AND user_id=?", (code, msg.from_user.id))
    if cur.fetchone():
        await msg.answer("❌ Ты уже использовал этот промокод."); await state.clear(); c.close(); return
    if row["uses_left"] <= 0:
        await msg.answer("❌ Промокод закончился."); await state.clear(); c.close(); return
    amount = row["amount"]
    add_balance(msg.from_user.id, amount)
    add_trx(msg.from_user.id, amount, "promo", code)
    cur.execute("UPDATE promos SET uses_left=uses_left-1 WHERE code=?", (code,))
    cur.execute("INSERT INTO promo_uses(code,user_id) VALUES(?,?)", (code, msg.from_user.id))
    c.commit(); c.close()
    await msg.answer(f"✅ Промокод активирован! +{amount}⭐")
    await state.clear()

@dp.callback_query(F.data == "history")
async def cb_history(cb: CallbackQuery):
    c = db(); cur = c.cursor()
    cur.execute("SELECT amount,type,note FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10", (cb.from_user.id,))
    rows = cur.fetchall(); c.close()
    text = "📜 <b>Последние операции</b>\n\n"
    if not rows: text += "Пока пусто."
    for r in rows:
        sign = "+" if r["amount"] > 0 else ""
        text += f"{sign}{r['amount']}⭐ — {r['note'] or r['type']}\n"
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=back_kb("tab_balance"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=back_kb("tab_balance"), parse_mode="HTML")

# ============ ПРОФИЛЬ ============
@dp.callback_query(F.data == "tab_profile")
async def cb_profile(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    c = db(); cur = c.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE referrer_id=?", (cb.from_user.id,))
    refs = cur.fetchone()["cnt"]; c.close()
    username = f"@{u['username']}" if u["username"] else "—"
    text = (f"👤 <b>Профиль</b>\n\n"
            f"Ник: {u['full_name']}\n"
            f"Юз: {username}\n"
            f"ID: <code>{u['user_id']}</code>\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"👥 <b>Рефералы</b>\n"
            f"Приглашено: {refs}\n"
            f"Заработано: {u['ref_earned']}⭐\n"
            f"За рефа: {REF_BONUS}⭐ (если пополнит от {MIN_DEPOSIT}⭐ и сыграет)")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=profile_menu(cb.from_user.id), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=profile_menu(cb.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "show_ref")
async def cb_show_ref(cb: CallbackQuery):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{cb.from_user.id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться", url=f"https://t.me/share/url?url={link}&text=Играй в Liberty Stars!")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="tab_profile")]
    ])
    await cb.answer()
    try:
        await cb.message.edit_text(f"🔗 Твоя ссылка:\n<code>{link}</code>", reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(f"🔗 Твоя ссылка:\n<code>{link}</code>", reply_markup=kb, parse_mode="HTML")

# ============ АДМИН ============
@dp.callback_query(F.data == "tab_admin")
async def cb_admin(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет доступа", show_alert=True); return
    await cb.answer()
    try:
        await cb.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_menu(), parse_mode="HTML")
    except Exception:
        await cb.message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_create_promo")
async def cb_adm_create(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await cb.answer()
    await cb.message.answer("🎟 Напиши: СУММА КОЛИЧЕСТВО\nНапример: 20 100")
    await state.set_state("adm_promo")

@dp.message(State("adm_promo"))
async def adm_promo_handler(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await msg.answer("❗ Формат: СУММА КОЛИЧЕСТВО"); return
    amount = int(parts[0]); uses = int(parts[1])
    code = "LIB" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    c = db(); cur = c.cursor()
    cur.execute("INSERT INTO promos(code,amount,uses_left) VALUES(?,?,?)", (code, amount, uses))
    c.commit(); c.close()
    await msg.answer(f"✅ Промокод:\n<code>{code}</code>\n{amount}⭐ × {uses}", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "adm_give")
async def cb_adm_give(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await cb.answer()
    await cb.message.answer("💰 Формат: ID СУММА")
    await state.set_state("adm_give")

@dp.message(State("adm_give"))
async def adm_give_handler(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await msg.answer("❗ Формат: ID СУММА"); return
    uid = int(parts[0]); amount = int(parts[1])
    if not get_user(uid): await msg.answer("Юзер не найден."); return
    add_balance(uid, amount)
    add_trx(uid, amount, "admin", f"Выдал {msg.from_user.id}")
    await msg.answer(f"✅ {amount}⭐ → {uid}")
    try: await bot.send_message(uid, f"🎁 Админ выдал тебе {amount}⭐!")
    except Exception: pass
    await state.clear()
@dp.callback_query(F.data == "adm_take")
async def cb_adm_take(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await cb.answer()
    await cb.message.answer("💸 Формат: ID СУММА")
    await state.set_state("adm_take")

@dp.message(State("adm_take"))
async def adm_take_handler(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await msg.answer("❗ Формат: ID СУММА"); return
    uid = int(parts[0]); amount = int(parts[1])
    if not get_user(uid): await msg.answer("Юзер не найден."); return
    add_balance(uid, -amount)
    add_trx(uid, -amount, "admin", f"Снял {msg.from_user.id}")
    await msg.answer(f"✅ Снято {amount}⭐ у {uid}")
    await state.clear()

@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    c = db(); cur = c.cursor()
    cur.execute("SELECT COUNT(*) as u FROM users"); users = cur.fetchone()["u"]
    cur.execute("SELECT SUM(balance) as b FROM users"); tb = cur.fetchone()["b"] or 0
    cur.execute("SELECT SUM(deposited) as d FROM users"); td = cur.fetchone()["d"] or 0
    c.close()
    text = (f"📊 <b>Статистика</b>\n\n"
            f"Пользователей: {users}\n"
            f"Общий баланс: {tb}⭐\n"
            f"Всего пополнено: {td}⭐")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=back_kb("tab_admin"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=back_kb("tab_admin"), parse_mode="HTML")
# ============ ИГРА: СЛОТЫ LIBERTY ============
SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]
SLOT_WEIGHTS = [35, 25, 20, 12, 6, 2]

def spin_slots():
    return random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)

def slots_win(symbols, bet):
    a, b, c = symbols
    if a == b == c:
        if a == "7️⃣": return bet * 20
        if a == "💎": return bet * 10
        if a == "🍇": return bet * 6
        if a == "🍊": return bet * 4
        if a == "🍋": return bet * 3
        if a == "🍒": return bet * 2
    if a == b or b == c or a == c:
        return bet * 1
    return 0

@dp.callback_query(F.data == "g_slots")
async def cb_slots(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"🎰 <b>Слоты Liberty</b>\n\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"Символы: 🍒 🍋 🍊 🍇 💎 7️⃣\n"
            f"3 одинаковых — большой выигрыш!\n\n"
            f"Выбери ставку:")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=bet_kb("slots"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=bet_kb("slots"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("slots_bet_"))
async def cb_slots_bet(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    arg = cb.data.replace("slots_bet_", "")
    bet = u["balance"] if arg == "all" else int(arg)
    if bet < MIN_BET:
        await cb.answer("Мин. ставка 1⭐", show_alert=True); return
    if bet > u["balance"]:
        await cb.answer("Недостаточно средств", show_alert=True); return
    add_balance(cb.from_user.id, -bet)
    stat_game(cb.from_user.id)

    msg = await cb.message.edit_text("🎰 Крутим... 🍒 | 🍋 | 🍊")
    for _ in range(2):
        await asyncio.sleep(0.7)
        s = spin_slots()
        try:
            await msg.edit_text(f"🎰 Крутим... {s[0]} | {s[1]} | {s[2]}")
        except Exception: pass
    await asyncio.sleep(0.7)

    s = spin_slots()
    win = slots_win(s, bet)
    if win > 0:
        add_balance(cb.from_user.id, win)
        stat_game(cb.from_user.id, won=True)
        add_trx(cb.from_user.id, win - bet, "slots", f"Ставка {bet}, выигрыш {win}")
        result = f"🎰 {s[0]} | {s[1]} | {s[2]}\n\n🎉 Выигрыш: <b>{win}⭐</b>\nБаланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>"
        pay_referrer(cb.from_user.id)
    else:
        add_trx(cb.from_user.id, -bet, "slots", f"Ставка {bet}, проигрыш")
        result = f"🎰 {s[0]} | {s[1]} | {s[2]}\n\n😔 Проигрыш\nБаланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ещё раз", callback_data="g_slots")],
        [InlineKeyboardButton(text="⬅️ Игры", callback_data="tab_games")]
    ])
    try:
        await msg.edit_text(result, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(result, reply_markup=kb, parse_mode="HTML")
    await cb.answer()

# ============ ИГРА: СЛОТЫ БИЗНЕСА ============
BIZ_SYMBOLS = ["💼", "📈", "💰", "🏦", "💎", "👑"]
BIZ_WEIGHTS = [35, 25, 20, 12, 6, 2]

def spin_biz():
    return random.choices(BIZ_SYMBOLS, weights=BIZ_WEIGHTS, k=3)

def biz_win(symbols, bet):
    a, b, c = symbols
    if a == b == c:
        if a == "👑": return bet * 25
        if a == "💎": return bet * 12
        if a == "🏦": return bet * 8
        if a == "💰": return bet * 5
        if a == "📈": return bet * 3
        if a == "💼": return bet * 2
    if a == b or b == c or a == c:
        return bet * 1
    return 0

@dp.callback_query(F.data == "g_slots_biz")
async def cb_slots_biz(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"💼 <b>Слоты Бизнеса</b>\n\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"Символы: 💼 📈 💰 🏦 💎 👑\n"
            f"3 одинаковых — крупный куш!\n\n"
            f"Выбери ставку:")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=bet_kb("biz"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=bet_kb("biz"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("biz_bet_"))
async def cb_biz_bet(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    arg = cb.data.replace("biz_bet_", "")
    bet = u["balance"] if arg == "all" else int(arg)
    if bet < MIN_BET:
        await cb.answer("Мин. ставка 1⭐", show_alert=True); return
    if bet > u["balance"]:
        await cb.answer("Недостаточно средств", show_alert=True); return
    add_balance(cb.from_user.id, -bet)
    stat_game(cb.from_user.id)

    msg = await cb.message.edit_text("💼 Крутим... 💼 | 📈 | 💰")
    for _ in range(2):
        await asyncio.sleep(0.7)
        s = spin_biz()
        try:
            await msg.edit_text(f"💼 Крутим... {s[0]} | {s[1]} | {s[2]}")
        except Exception: pass
    await asyncio.sleep(0.7)

    s = spin_biz()
    win = biz_win(s, bet)
    if win > 0:
        add_balance(cb.from_user.id, win)
        stat_game(cb.from_user.id, won=True)
        add_trx(cb.from_user.id, win - bet, "biz", f"Ставка {bet}, выигрыш {win}")
        result = f"💼 {s[0]} | {s[1]} | {s[2]}\n\n🎉 Выигрыш: <b>{win}⭐</b>\nБаланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>"
        pay_referrer(cb.from_user.id)
    else:
        add_trx(cb.from_user.id, -bet, "biz", f"Ставка {bet}, проигрыш")
        result = f"💼 {s[0]} | {s[1]} | {s[2]}\n\n😔 Проигрыш\nБаланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ещё раз", callback_data="g_slots_biz")],
        [InlineKeyboardButton(text="⬅️ Игры", callback_data="tab_games")]
    ])
    try:
        await msg.edit_text(result, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(result, reply_markup=kb, parse_mode="HTML")
    await cb.answer()

# ============ ИГРА: МИНЫ ============
mines_games = {}

def mines_field(mines_count=3, size=5):
    cells = list(range(size * size))
    bombs = set(random.sample(cells, mines_count))
    return bombs, size

def mines_mult(opened, mines_count=3, total=25):
    # коэффициент растёт с каждой открытой клеткой
    safe = total - mines_count
    if opened <= 0: return 1.0
    mult = 1.0
    for i in range(opened):
        mult *= (total - i) / (safe - i)
    return round(mult * 0.95, 2)

def mines_kb(game_id, opened, size=5):
    bombs, _ = mines_games[game_id]["bombs"], size
    rows = []
    for r in range(size):
        row = []
        for c in range(size):
            idx = r * size + c
            if idx in mines_games[game_id]["opened"]:
                row.append(InlineKeyboardButton(text="💎", callback_data=f"mine_noop_{game_id}"))
            else:
                row.append(InlineKeyboardButton(text="⬜", callback_data=f"mine_open_{game_id}_{idx}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="💰 Забрать", callback_data=f"mine_cash_{game_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(F.data == "g_mines")
async def cb_mines(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"💣 <b>Мины</b>\n\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"Поле 5×5, 3 мины.\n"
            f"Открывай клетки, множитель растёт.\n"
            f"Наткнёшься на мину — потеряешь ставку.\n"
            f"Успей забрать выигрыш!\n\n"
            f"Выбери ставку:")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=bet_kb("mines"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=bet_kb("mines"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("mines_bet_"))
async def cb_mines_bet(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    arg = cb.data.replace("mines_bet_", "")
    bet = u["balance"] if arg == "all" else int(arg)
    if bet < MIN_BET:
        await cb.answer("Мин. ставка 1⭐", show_alert=True); return
    if bet > u["balance"]:
        await cb.answer("Недостаточно средств", show_alert=True); return
        add_balance(cb.from_user.id, -bet)
        stat_game(cb.from_user.id)
    gid = f"{cb.from_user.id}_{int(time.time())}"
    bombs, size = mines_field(3, 5)
    mines_games[gid] = {"uid": cb.from_user.id, "bet": bet, "bombs": bombs,
                        "opened": set(), "size": size, "chat_id": cb.message.chat.id,
                        "msg_id": None}
    text = (f"💣 <b>Мины</b>\n\n"
            f"Ставка: {bet}⭐\n"
            f"Открыто: 0 | Множитель: x1.0\n"
            f"Потенциальный выигрыш: {bet}⭐")
    await cb.answer()
    sent = await cb.message.edit_text(text, reply_markup=mines_kb(gid, 0), parse_mode="HTML")
    mines_games[gid]["msg_id"] = sent.message_id

@dp.callback_query(F.data.startswith("mine_noop_"))
async def cb_mine_noop(cb: CallbackQuery):
    await cb.answer()

@dp.callback_query(F.data.startswith("mine_open_"))
async def cb_mine_open(cb: CallbackQuery):
    parts = cb.data.split("_")
    gid = parts[2] + "_" + parts[3]
    idx = int(parts[4])
    game = mines_games.get(gid)
    if not game or game["uid"] != cb.from_user.id:
        await cb.answer("Игра не твоя", show_alert=True); return

    if idx in game["bombs"]:
        add_trx(cb.from_user.id, -game["bet"], "mines", f"Ставка {game['bet']}, мина")
        text = (f"💣 <b>Мина!</b>\n\n"
                f"Ты потерял {game['bet']}⭐\n"
                f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ещё раз", callback_data="g_mines")],
            [InlineKeyboardButton(text="⬅️ Игры", callback_data="tab_games")]
        ])
        await cb.answer("💥 Мина!")
        try:
            await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception: pass
        mines_games.pop(gid, None)
        return

    game["opened"].add(idx)
    opened = len(game["opened"])
    mult = mines_mult(opened, len(game["bombs"]), game["size"] * game["size"])
    potential = int(game["bet"] * mult)
    text = (f"💣 <b>Мины</b>\n\n"
            f"Ставка: {game['bet']}⭐\n"
            f"Открыто: {opened} | Множитель: x{mult}\n"
            f"Потенциальный выигрыш: <b>{potential}⭐</b>")
    await cb.answer(f"💎 x{mult}")
    try:
        await cb.message.edit_text(text, reply_markup=mines_kb(gid, opened), parse_mode="HTML")
    except Exception: pass

@dp.callback_query(F.data.startswith("mine_cash_"))
async def cb_mine_cash(cb: CallbackQuery):
    parts = cb.data.split("_")
    gid = parts[2] + "_" + parts[3]
    game = mines_games.get(gid)
    if not game or game["uid"] != cb.from_user.id:
        await cb.answer("Игра не твоя", show_alert=True); return
    if not game["opened"]:
        await cb.answer("Открой хотя бы одну клетку", show_alert=True); return

    opened = len(game["opened"])
    mult = mines_mult(opened, len(game["bombs"]), game["size"] * game["size"])
    win = int(game["bet"] * mult)
    add_balance(cb.from_user.id, win)
    stat_game(cb.from_user.id, won=True)
    add_trx(cb.from_user.id, win - game["bet"], "mines", f"Ставка {game['bet']}, выигрыш {win}")
    text = (f"💰 <b>Забрал!</b>\n\n"
            f"Открыто: {opened} | Множитель: x{mult}\n"
            f"Выигрыш: <b>{win}⭐</b>\n"
            f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ещё раз", callback_data="g_mines")],
        [InlineKeyboardButton(text="⬅️ Игры", callback_data="tab_games")]
    ])
    await cb.answer(f"+{win}⭐")
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception: pass
    mines_games.pop(gid, None)
    pay_referrer(cb.from_user.id)

# ============ ИГРА: КУБИК ============
@dp.callback_query(F.data == "g_dice")
async def cb_dice(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"🎲 <b>Кубик</b>\n\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"Ставка: на 4, 5 или 6 (x2)\n"
            f"Выбери сумму:")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=bet_kb("dice"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=bet_kb("dice"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dice_bet_"))
async def cb_dice_bet(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    arg = cb.data.replace("dice_bet_", "")
    bet = u["balance"] if arg == "all" else int(arg)
    if bet < MIN_BET:
        await cb.answer("Мин. ставка 1⭐", show_alert=True); return
    if bet > u["balance"]:
        await cb.answer("Недостаточно средств", show_alert=True); return
    add_balance(cb.from_user.id, -bet)
    stat_game(cb.from_user.id)

    msg = await cb.message.edit_text("🎲 Бросаем...")
    sent = await bot.send_dice(cb.message.chat.id, emoji="🎲")
    value = sent.dice.value
    win = bet * 2 if value >= 4 else 0

    if win > 0:
        add_balance(cb.from_user.id, win)
        stat_game(cb.from_user.id, won=True)
        add_trx(cb.from_user.id, win - bet, "dice", f"Ставка {bet}, выпало {value}")
        result = (f"🎲 Выпало: <b>{value}</b>\n\n"
                  f"🎉 Выигрыш: <b>{win}⭐</b>\n"
                  f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")
        pay_referrer(cb.from_user.id)
    else:
        add_trx(cb.from_user.id, -bet, "dice", f"Ставка {bet}, выпало {value}")
        result = (f"🎲 Выпало: <b>{value}</b>\n\n"
                  f"😔 Проигрыш\n"
                  f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ещё раз", callback_data="g_dice")],
        [InlineKeyboardButton(text="⬅️ Игры", callback_data="tab_games")]
    ])
    await asyncio.sleep(2)
    try:
        await msg.edit_text(result, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(result, reply_markup=kb, parse_mode="HTML")
    await cb.answer()

# ============ ИГРА: РУЛЕТКА ============
RED = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
BLACK = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}

@dp.callback_query(F.data == "g_roulette")
async def cb_roulette(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"🎡 <b>Рулетка</b>\n\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"🔴 Красное / ⚫ Чёрное — x2\n"
            f"🟢 Зеро — x14\n\n"
            f"Сначала ставка:")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=bet_kb("roul"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=bet_kb("roul"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("roul_bet_"))
async def cb_roul_bet(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    arg = cb.data.replace("roul_bet_", "")
    bet = u["balance"] if arg == "all" else int(arg)
    if bet < MIN_BET:
        await cb.answer("Мин. ставка 1⭐", show_alert=True); return
    if bet > u["balance"]:
        await cb.answer("Недостаточно средств", show_alert=True); return
    add_balance(cb.from_user.id, -bet)
    stat_game(cb.from_user.id)
    gid = f"{cb.from_user.id}_{int(time.time())}"
    mines_games[gid] = {"uid": cb.from_user.id, "bet": bet, "type": "roulette"}
    text = f"🎡 Ставка {bet}⭐\n\nНа что ставим?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное x2", callback_data=f"roul_go_{gid}_red"),
         InlineKeyboardButton(text="⚫ Чёрное x2", callback_data=f"roul_go_{gid}_black")],
        [InlineKeyboardButton(text="🟢 Зеро x14", callback_data=f"roul_go_{gid}_zero")]
    ])
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
@dp.callback_query(F.data.startswith("roul_go_"))
async def cb_roul_go(cb: CallbackQuery):
    parts = cb.data.split("_")
    gid = parts[2] + "_" + parts[3]
    choice = parts[4]
    game = mines_games.get(gid)
    if not game or game["uid"] != cb.from_user.id:
        await cb.answer("Игра не твоя", show_alert=True); return

    num = random.randint(0, 36)
    if num == 0: color = "green"
    elif num in RED: color = "red"
    else: color = "black"

    bet = game["bet"]
    win = 0
    if choice == "red" and color == "red": win = bet * 2
    elif choice == "black" and color == "black": win = bet * 2
    elif choice == "zero" and color == "green": win = bet * 14

    emoji = "🟢" if color == "green" else ("🔴" if color == "red" else "⚫")
    if win > 0:
        add_balance(cb.from_user.id, win)
        stat_game(cb.from_user.id, won=True)
        add_trx(cb.from_user.id, win - bet, "roulette", f"Ставка {bet}, выпало {num}, выигрыш {win}")
        result = (f"🎡 Выпало: {emoji} <b>{num}</b>\n\n"
                  f"🎉 Выигрыш: <b>{win}⭐</b>\n"
                  f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")
        pay_referrer(cb.from_user.id)
    else:
        add_trx(cb.from_user.id, -bet, "roulette", f"Ставка {bet}, выпало {num}")
        result = (f"🎡 Выпало: {emoji} <b>{num}</b>\n\n"
                  f"😔 Проигрыш\n"
                  f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ещё раз", callback_data="g_roulette")],
        [InlineKeyboardButton(text="⬅️ Игры", callback_data="tab_games")]
    ])
    await cb.answer(f"{emoji} {num}")
    try:
        await cb.message.edit_text(result, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(result, reply_markup=kb, parse_mode="HTML")
    mines_games.pop(gid, None)

# ============ ИГРА: МОНЕТКА ============
@dp.callback_query(F.data == "g_coin")
async def cb_coin(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    text = (f"🪙 <b>Монетка</b>\n\n"
            f"Баланс: <b>{u['balance']}⭐</b>\n\n"
            f"Орёл или Решка — x2\n\n"
            f"Выбери ставку:")
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=bet_kb("coin"), parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=bet_kb("coin"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("coin_bet_"))
async def cb_coin_bet(cb: CallbackQuery):
    u = get_user(cb.from_user.id)
    arg = cb.data.replace("coin_bet_", "")
    bet = u["balance"] if arg == "all" else int(arg)
    if bet < MIN_BET:
        await cb.answer("Мин. ставка 1⭐", show_alert=True); return
    if bet > u["balance"]:
        await cb.answer("Недостаточно средств", show_alert=True); return
    add_balance(cb.from_user.id, -bet)
    stat_game(cb.from_user.id)
    gid = f"{cb.from_user.id}_{int(time.time())}"
    mines_games[gid] = {"uid": cb.from_user.id, "bet": bet, "type": "coin"}
    text = f"🪙 Ставка {bet}⭐\n\nЧто выбираешь?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🦅 Орёл", callback_data=f"coin_go_{gid}_eagle"),
         InlineKeyboardButton(text="🪙 Решка", callback_data=f"coin_go_{gid}_tails")]
    ])
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("coin_go_"))
async def cb_coin_go(cb: CallbackQuery):
    parts = cb.data.split("_")
    gid = parts[2] + "_" + parts[3]
    choice = parts[4]
    game = mines_games.get(gid)
    if not game or game["uid"] != cb.from_user.id:
        await cb.answer("Игра не твоя", show_alert=True); return

    result_side = random.choice(["eagle", "tails"])
    bet = game["bet"]
    if result_side == choice:
        win = bet * 2
        add_balance(cb.from_user.id, win)
        stat_game(cb.from_user.id, won=True)
        add_trx(cb.from_user.id, win - bet, "coin", f"Ставка {bet}, выигрыш {win}")
        side_emoji = "🦅" if result_side == "eagle" else "🪙"
        result = (f"🪙 Выпало: {side_emoji}\n\n"
                  f"🎉 Выигрыш: <b>{win}⭐</b>\n"
                  f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")
        pay_referrer(cb.from_user.id)
    else:
        add_trx(cb.from_user.id, -bet, "coin", f"Ставка {bet}, проигрыш")
        side_emoji = "🦅" if result_side == "eagle" else "🪙"
        result = (f"🪙 Выпало: {side_emoji}\n\n"
                  f"😔 Проигрыш\n"
                  f"Баланс: <b>{get_user(cb.from_user.id)['balance']}⭐</b>")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Ещё раз", callback_data="g_coin")],
        [InlineKeyboardButton(text="⬅️ Игры", callback_data="tab_games")]
    ])
    await cb.answer()
    try:
        await cb.message.edit_text(result, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await cb.message.answer(result, reply_markup=kb, parse_mode="HTML")
    mines_games.pop(gid, None)

async def main():
    print("Liberty Stars запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
