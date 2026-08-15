import hmac
import hashlib
import json
import urllib.parse
import os
import asyncio
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from pydantic import BaseModel
import uvicorn

# ==========================================
# ⚙️ НАСТРОЙКИ (Берем данные из переменных окружения Render)
# ==========================================
BOT_TOKEN = "8745402475:AAEtCvZf1IxIjW3Z5usFfeXrylanqyXres8"
WEBAPP_URL = https://bnmoney.onrender.com

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

# База данных пользователей (в памяти сервера)
USERS_DB = {}

def verify_telegram_data(init_data: str) -> dict:
    if not init_data:
        return {"user": {"id": 99999999, "username": "demo_guest", "first_name": "Demo"}}
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed_data:
            raise ValueError("No hash provided")

        hash_to_check = parsed_data.pop("hash")
        sorted_items = sorted(parsed_data.items(), key=lambda x: x[0])
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted_items])

        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != hash_to_check:
            raise ValueError("Invalid hash signature")

        if "user" in parsed_data:
            parsed_data["user"] = json.loads(parsed_data["user"])

        return parsed_data
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Ошибка авторизации: {str(e)}")

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username or f"id{user_id}"
    first_name = message.from_user.first_name or "Пользователь"

    referrer_username = None
    if command.args and command.args.startswith("ref_"):
        referrer_username = command.args.replace("ref_", "")
        if referrer_username.lower() == username.lower():
            referrer_username = None

    if user_id not in USERS_DB:
        USERS_DB[user_id] = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "balance": 0.00,
            "referrer": referrer_username,
            "subscriptions": []
        }
    else:
        USERS_DB[user_id]["username"] = username
        USERS_DB[user_id]["first_name"] = first_name

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚀 ОТКРЫТЬ ЛИЧНЫЙ КАБИНЕТ",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ])

    inviter_text = f"\n👑 Ваш пригласитель: <b>@{referrer_username}</b>" if referrer_username else ""

    await message.answer(
        f"<b>Добро пожаловать в BNMONEY, {first_name}!</b>\n"
        f"Ваш аккаунт <b>@{username}</b> зарегистрирован.{inviter_text}\n\n"
        f"Нажмите кнопку ниже для входа в кабинет:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

class SubscribeRequest(BaseModel):
    plan_price: float
    target_price: float

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Файл index.html не найден!</h1>"

@app.get("/api/user/me")
async def get_me(authorization: str = Header(None)):
    auth_data = verify_telegram_data(authorization)
    tg_user = auth_data["user"]
    user_id = tg_user["id"]
    username = tg_user.get("username") or f"id{user_id}"
    first_name = tg_user.get("first_name", "Пользователь")

    if user_id not in USERS_DB:
        USERS_DB[user_id] = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "balance": 0.00,
            "referrer": None,
            "subscriptions": []
        }

    bot_info = await bot.get_me()
    user_data = USERS_DB[user_id].copy()
    user_data["bot_username"] = bot_info.username
    return user_data

@app.post("/api/subscribe")
async def process_subscription(data: SubscribeRequest, authorization: str = Header(None)):
    auth_data = verify_telegram_data(authorization)
    user_id = auth_data["user"]["id"]

    user = USERS_DB.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")

    if user["balance"] < data.plan_price:
        raise HTTPException(status_code=400, detail="Недостаточно средств!")

    user["balance"] -= data.plan_price
    user["subscriptions"].append({
        "plan_price": data.plan_price,
        "target_price": data.target_price
    })

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"⚡ <b>Активация подписки!</b>\n\n"
                 f"Тариф: <b>{data.plan_price}$ ➔ {data.target_price}$</b>\n"
                 f"Остаток: <b>{user['balance']:.2f} USDT</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Ошибка отправки: {e}")

    return {"status": "success", "new_balance": user["balance"]}

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
