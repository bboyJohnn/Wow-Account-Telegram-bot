import asyncio
import hashlib
import os
import re
import pymysql
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logging.warning('python-dotenv is not installed; .env file will not be loaded')

# --- НАСТРОЙКИ ---
REQUIRED_ENV = ['BOT_TOKEN', 'DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DB_PORT']
missing_env = [name for name in REQUIRED_ENV if not os.getenv(name)]
if missing_env:
    raise RuntimeError(f"Необходимые переменные окружения не заданы: {', '.join(missing_env)}")

BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT')),
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
    waiting_for_delete_confirmation = State()

# --- КЛАВИАТУРА ---
def get_main_menu():
    buttons = [
        [KeyboardButton(text="⚔️ Создать аккаунт"), KeyboardButton(text="🗑 Удалить мой аккаунт")],
        [KeyboardButton(text="🔑 Сменить пароль"), KeyboardButton(text="ℹ️ Мой аккаунт")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- МАТЕМАТИКА (ПОБЕДНАЯ) ---
def calculate_srp6(username, password):
    g, N = 7, int('894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7', 16)
    salt_bin = os.urandom(32)
    h_bin = hashlib.sha1(f"{username.upper()}:{password.upper()}".encode('utf-8')).digest()
    x_bin = hashlib.sha1(salt_bin[::-1] + h_bin).digest()
    x_int = int.from_bytes(x_bin, byteorder='little')
    v_int = pow(g, x_int, N)
    return salt_bin.hex().upper(), v_int.to_bytes(32, byteorder='big').hex().upper()

# --- ВАЛИДАЦИЯ ---
USERNAME_PATTERN = re.compile(r'^[A-Z]{3,10}$')

def validate_username(username: str) -> bool:
    return bool(USERNAME_PATTERN.fullmatch(username))


def validate_password(password: str) -> bool:
    password = password.strip()
    return 8 <= len(password) <= 20 and not password.isspace()

# --- ЛОГИКА БАЗЫ ---

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


def get_user_account(tgid):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM account WHERE tgid = %s", (tgid,))
            row = cursor.fetchone()
            return row[0] if row else None
    except pymysql.MySQLError:
        logging.exception('Ошибка при получении аккаунта пользователя')
        return None
    finally:
        conn.close()

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🌟 **Добро пожаловать в Kryto Saito WoW!** 🌟\n\n"
        "🏰 *Королевство Азерота ждёт своих героев!*\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "ℹ️ Мой аккаунт")
async def my_acc(message: types.Message):
    acc = get_user_account(message.from_user.id)
    if acc:
        await message.answer(
            f"🛡️ **Ваш аккаунт:** `{acc}`\n\n"
            "⚔️ *Готов ли ты к битвам?*",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "❌ *У вас ещё нет аккаунта в Азероте!*\n\n"
            "Создайте его, чтобы присоединиться к приключениям!",
            parse_mode="Markdown"
        )

@dp.message(F.text == "⚔️ Создать аккаунт")
async def start_reg(message: types.Message, state: FSMContext):
    if get_user_account(message.from_user.id):
        return await message.answer(
            "⚠️ *У вас уже есть аккаунт!*\n\n"
            "Каждый герой может иметь только один аккаунт в королевстве.",
            parse_mode="Markdown"
        )
    await message.answer(
        "📜 *Создание аккаунта героя*\n\n"
        "Введите желаемый логин (латинские буквы A-Z, 3-10 символов):",
        parse_mode="Markdown"
    )
    await state.set_state(RegState.waiting_for_username)

@dp.message(RegState.waiting_for_username)
async def reg_user(message: types.Message, state: FSMContext):
    login = message.text.strip().upper()
    if not validate_username(login):
        return await message.answer(
            "❌ *Неправильный логин!*\n\n"
            "Он должен быть 3-10 латинских букв без пробелов.\n"
            "Попробуйте снова:",
            parse_mode="Markdown"
        )

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM account WHERE username = %s", (login,))
            if cursor.fetchone():
                return await message.answer(
                    "🚫 *Этот логин уже занят!* \n\n"
                    "Другой герой уже носит это имя. Выберите другое:",
                    parse_mode="Markdown"
                )
    except pymysql.MySQLError:
        logging.exception('Ошибка при проверке логина')
        return await message.answer(
            "💥 *Произошла ошибка при проверке логина.*\n\n"
            "Попробуйте позже.",
            parse_mode="Markdown"
        )
    finally:
        conn.close()

    await state.update_data(username=login)
    await message.answer(
        f"✅ *Логин `{login}` свободен!*\n\n"
        "Теперь введите пароль (8-20 символов):",
        parse_mode="Markdown"
    )
    await state.set_state(RegState.waiting_for_password)

@dp.message(RegState.waiting_for_password)
async def reg_pass(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if not validate_password(password):
        return await message.answer(
            "❌ *Пароль должен быть 8-20 символов.*\n\n"
            "Введите новый пароль:",
            parse_mode="Markdown"
        )

    data = await state.get_data()
    username = data['username']
    s, v = calculate_srp6(username, password)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """INSERT INTO account (username, v, s, email, tgid, joindate, expansion) 
                     VALUES (%s, %s, %s, %s, %s, NOW(), 0)"""
            cursor.execute(sql, (username, v, s, f"{username}@local.host", message.from_user.id))
    except pymysql.MySQLError:
        logging.exception('Ошибка при создании аккаунта')
        return await message.answer(
            "💥 *Не удалось создать аккаунт.*\n\n"
            "Попробуйте позже.",
            parse_mode="Markdown"
        )
    finally:
        conn.close()

    await message.answer(
        f"🎉 **Аккаунт `{username}` успешно создан!** 🎉\n\n"
        "🏆 *Добро пожаловать в Азерот, герой!*",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )
    await state.clear()

@dp.message(F.text == "🔑 Сменить пароль")
async def change_pass_start(message: types.Message, state: FSMContext):
    acc = get_user_account(message.from_user.id)
    if not acc:
        return await message.answer(
            "❌ *Сначала создайте аккаунт!*\n\n"
            "Без аккаунта нельзя менять пароль.",
            parse_mode="Markdown"
        )
    await message.answer(
        f"🔐 *Меняем пароль для аккаунта `{acc}`*\n\n"
        "Введите новый пароль (8-20 символов):",
        parse_mode="Markdown"
    )
    await state.set_state(RegState.waiting_for_new_password)

@dp.message(RegState.waiting_for_new_password)
async def change_pass_finish(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if not validate_password(password):
        return await message.answer(
            "❌ *Пароль должен быть 8-20 символов.*\n\n"
            "Введите новый пароль:",
            parse_mode="Markdown"
        )

    acc = get_user_account(message.from_user.id)
    if not acc:
        await state.clear()
        return await message.answer(
            "❌ *Аккаунт не найден.*\n\n"
            "Начните заново.",
            parse_mode="Markdown"
        )
    username = acc
    s, v = calculate_srp6(username, password)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE account SET s=%s, v=%s WHERE username=%s", (s, v, username))
    except pymysql.MySQLError:
        logging.exception('Ошибка при смене пароля')
        return await message.answer(
            "💥 *Не удалось изменить пароль.*\n\n"
            "Попробуйте позже.",
            parse_mode="Markdown"
        )
    finally:
        conn.close()

    await message.answer(
        f"✅ **Пароль для `{username}` успешно изменён!**\n\n"
        "🛡️ *Ваша крепость защищена!*",
        parse_mode="Markdown"
    )
    await state.clear()

@dp.message(F.text == "🗑 Удалить мой аккаунт")
async def delete_acc(message: types.Message, state: FSMContext):
    acc = get_user_account(message.from_user.id)
    if not acc:
        return await message.answer(
            "❌ *У вас нет активных аккаунтов.*\n\n"
            "Нечего удалять.",
            parse_mode="Markdown"
        )

    await message.answer(
        f"⚠️ **Внимание, герой!**\n\n"
        f"Аккаунт `{acc}` будет удалён навсегда.\n"
        "Это действие нельзя отменить.\n\n"
        "Если вы уверены, введите `УДАЛИТЬ`:",
        parse_mode="Markdown"
    )
    await state.set_state(RegState.waiting_for_delete_confirmation)

@dp.message(RegState.waiting_for_delete_confirmation)
async def delete_acc_confirm(message: types.Message, state: FSMContext):
    if message.text.strip().upper() != 'УДАЛИТЬ':
        await state.clear()
        return await message.answer(
            "❌ *Удаление отменено.*\n\n"
            "Если хотите, используйте меню заново.",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

    acc = get_user_account(message.from_user.id)
    if not acc:
        await state.clear()
        return await message.answer(
            "❌ *Аккаунт не найден.*\n\n"
            "Начните заново.",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM account WHERE tgid = %s", (message.from_user.id,))
    except pymysql.MySQLError:
        logging.exception('Ошибка при удалении аккаунта')
        return await message.answer(
            "💥 *Не удалось удалить аккаунт.*\n\n"
            "Попробуйте позже.",
            parse_mode="Markdown"
        )
    finally:
        conn.close()
        await state.clear()

    await message.answer(
        f"🗑 **Аккаунт `{acc}` полностью удалён.**\n\n"
        "💔 *Прощай, герой...*",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

@dp.message(Command('cancel'))
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ *Действие отменено.*\n\n"
        "Возвращаемся в главное меню.",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )


async def main():
    logging.info('Bot started and waiting for updates...')
    print('Бот запущен и ожидает сообщений...')
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
