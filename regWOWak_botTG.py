import asyncio
import hashlib
import os
import pymysql
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# --- НАСТРОЙКИ ---
BOT_TOKEN = 'YOUR_TOKEN_HERE'
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'mangos',
    'password': 'mangos',
    'database': 'classicrealmd',
    'port': 3306,
    'autocommit': True
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- СОСТОЯНИЯ ---
class RegState(StatesGroup):
    waiting_for_username = State()
    waiting_for_password = State()
    waiting_for_new_password = State()

# --- КЛАВИАТУРА ---
def get_main_menu():
    buttons = [
        [KeyboardButton(text="⚔️ Создать аккаунт"), KeyboardButton(text="🗑 Удалить мой аккаунт")],
        [KeyboardButton(text="🔑 Сменить пароль"), KeyboardButton(text="ℹ️ Мой аккаунт")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- МАТЕМАТИКА ---
def calculate_srp6(username, password):
    g, N = 7, int('894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7', 16)
    salt_bin = os.urandom(32)
    h_bin = hashlib.sha1(f"{username.upper()}:{password.upper()}".encode('utf-8')).digest()
    x_bin = hashlib.sha1(salt_bin[::-1] + h_bin).digest()
    x_int = int.from_bytes(x_bin, byteorder='little')
    v_int = pow(g, x_int, N)
    return salt_bin.hex().upper(), v_int.to_bytes(32, byteorder='big').hex().upper()

# --- ЛОГИКА БАЗЫ (ИСПРАВЛЕНА УТЕЧКА СОЕДИНЕНИЙ) ---
def execute_db(query, params=None, fetchone=False, fetchall=False):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetchone:
                return cursor.fetchone()
            if fetchall:
                return cursor.fetchall()
    finally:
        conn.close()

def get_user_account(tgid):
    return execute_db("SELECT username FROM account WHERE tgid = %s", (tgid,), fetchone=True)

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать в терминал доступа к серверу WoW.", reply_markup=get_main_menu())

@dp.message(F.text == "ℹ️ Мой аккаунт")
async def my_acc(message: types.Message):
    acc = get_user_account(message.from_user.id)
    if acc:
        await message.answer(f"Ваш привязанный аккаунт: `{acc[0]}`", parse_mode="Markdown")
    else:
        await message.answer("У вас еще нет созданных аккаунтов в базе данных.")

@dp.message(F.text == "⚔️ Создать аккаунт")
async def start_reg(message: types.Message, state: FSMContext):
    if get_user_account(message.from_user.id):
        return await message.answer("У вас уже есть аккаунт! Система разрешает только один профиль на пользователя.")
    await message.answer("Введите желаемый логин:")
    await state.set_state(RegState.waiting_for_username)

@dp.message(RegState.waiting_for_username)
async def reg_user(message: types.Message, state: FSMContext):
    login = message.text.strip().upper()
    existing = execute_db("SELECT id FROM account WHERE username = %s", (login,), fetchone=True)
    if existing:
        return await message.answer("Этот логин уже занят, выберите другой:")
        
    await state.update_data(username=login)
    await message.answer(f"Логин `{login}` свободен. Введите пароль:", parse_mode="Markdown")
    await state.set_state(RegState.waiting_for_password)

@dp.message(RegState.waiting_for_password)
async def reg_pass(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = data['username']
    s, v = calculate_srp6(username, message.text.strip())
    
    sql = """INSERT INTO account (username, v, s, email, tgid, joindate, expansion) 
             VALUES (%s, %s, %s, %s, %s, NOW(), 0)"""
    execute_db(sql, (username, v, s, f"{username}@local.host", message.from_user.id))
    
    await message.answer(f"✅ Аккаунт `{username}` успешно создан! Добро пожаловать в Азерот.", reply_markup=get_main_menu(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🔑 Сменить пароль")
async def change_pass_start(message: types.Message, state: FSMContext):
    acc = get_user_account(message.from_user.id)
    if not acc:
        return await message.answer("Ошибка: Сначала создайте аккаунт.")
    await message.answer(f"Инициализация смены пароля для `{acc[0]}`. Введите новый пароль:", parse_mode="Markdown")
    await state.set_state(RegState.waiting_for_new_password)

@dp.message(RegState.waiting_for_new_password)
async def change_pass_finish(message: types.Message, state: FSMContext):
    acc = get_user_account(message.from_user.id)
    username = acc[0]
    s, v = calculate_srp6(username, message.text.strip())
    
    execute_db("UPDATE account SET s=%s, v=%s WHERE username=%s", (s, v, username))
    
    await message.answer(f"✅ Пароль для `{username}` успешно обновлен в базе.", parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🗑 Удалить мой аккаунт")
async def delete_acc(message: types.Message):
    acc = get_user_account(message.from_user.id)
    if not acc:
        return await message.answer("У вас нет активных аккаунтов в системе.")
    
    execute_db("DELETE FROM account WHERE tgid = %s", (message.from_user.id,))
    await message.answer(f"🗑 Записи стерты. Аккаунт `{acc[0]}` полностью удален из базы данных.", parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())