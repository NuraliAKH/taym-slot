import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery

from config import BOT_TOKEN
import database
from uzum_api import UzumClient, UzumApiError
from engine import engine
import keyboards

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("UzumBot")

# FSM States
class SetupState(StatesGroup):
    waiting_for_token = State()

class TaskWizardState(StatesGroup):
    mode = State() # 'AUTO_SNIPE' or 'NOTIFY'
    invoices_list = State()
    selected_invoice_ids = State()
    stock_id = State()
    selected_dates = State()
    page = State()

router = Router()

# In-memory wizard store for temporary fast pagination
wizard_cache: Dict[int, Dict[str, Any]] = {}

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    
    if not user or not user.get("token"):
        await state.set_state(SetupState.waiting_for_token)
        guide_text = (
            "👋 **Добро пожаловать в бота тайм-слотов Uzum Seller!**\n\n"
            "Этот бот умеет:\n"
            "1. 🎯 **Автоматически ловить и бронировать слоты** (Auto-Snipe) при их освобождении.\n"
            "2. 🔔 **Мгновенно уведомлять** о появлении свободных слотов с кнопкой бронирования.\n\n"
            "🔐 **Для начала работы отправьте ваш токен Uzum Seller:**\n"
            "1. Откройте [seller.uzum.uz](https://seller.uzum.uz) в браузере.\n"
            "2. Нажмите `F12` (DevTools) -> вкладка **Application** (или Сеть/Network).\n"
            "3. В Cookies или LocalStorage скопируйте токен авторизации (или отправьте значение `token`).\n\n"
            "👇 **Отправьте токен в ответном сообщении:**"
        )
        await message.answer(guide_text, parse_mode="Markdown")
        return

    # User already configured
    shop_id = user.get("selected_shop_id")
    seller_id = user.get("seller_id")
    phone = user.get("phone_number", "Не указан")
    
    welcome_text = (
        f"👋 **Главное меню Uzum Seller Slot Bot**\n\n"
        f"👤 **Продавец ID:** `{seller_id}`\n"
        f"📱 **Телефон:** `{phone}`\n"
        f"🏬 **Текущий магазин:** `#{shop_id}`\n\n"
        f"Выберите действие в меню ниже:"
    )
    await message.answer(welcome_text, reply_markup=keyboards.main_menu_keyboard(), parse_mode="Markdown")

def extract_clean_token(raw_text: str) -> str:
    """Intelligently extracts the seller access token from various user inputs."""
    text = raw_text.strip()
    
    # Check if pasted JSON with tokens
    if "tokens" in text or "access" in text:
        try:
            import json
            data = json.loads(text)
            if isinstance(data, dict):
                # Check {"user": {"tokens": {"access": "..."}}}
                acc = data.get("user", {}).get("tokens", {}).get("access")
                if acc:
                    return acc.strip()
                # Check {"tokens": {"access": "..."}}
                acc = data.get("tokens", {}).get("access")
                if acc:
                    return acc.strip()
                # Check {"access": "..."}
                acc = data.get("access") or data.get("accessToken") or data.get("token")
                if acc:
                    return acc.strip()
        except Exception:
            pass

    # Check regex for accessToken => ... or token: ... or accessToken=...
    import re
    m = re.search(r'(?:accessToken|access|token)\s*(?:=>|:|=)\s*["\']?([a-zA-Z0-9_\-]+)["\']?', text)
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 15 and not candidate.startswith("eyJ"):
            return candidate

    # If raw string without spaces
    if "\n" not in text and " " not in text:
        # Strip quotes if any
        return text.strip('"\'')

    return text

@router.message(SetupState.waiting_for_token)
async def process_token_input(message: Message, state: FSMContext):
    raw_token = message.text.strip()
    token = extract_clean_token(raw_token)
    
    if not token or len(token) < 15 or token.startswith("eyJ"):
        await message.answer(
            "❌ **Это не токен продавца Uzum Seller.**\n\n"
            "Вы отправили токен покупателя (`eyJ...`) или неверный формат.\n"
            "Нужен токен продавца **`accessToken`** (из `seller.uzum.uz`, около 27 символов, например `XyZ123...`).\n\n"
            "👉 Найдите в Cookies `seller.uzum.uz` строку **accessToken** или в Network в запросе `check_token` скопируйте `token`.",
            parse_mode="Markdown"
        )
        return

    wait_msg = await message.answer("⏳ Проверяем токен в Uzum Seller API...")

    try:
        async with UzumClient(token=token) as client:
            info = await client.check_token()

        seller_id = info.get("seller_id")
        phone = info.get("phone_number", "")
        shops = info.get("shops", [])
        selected_shop_id = shops[0]["id"] if shops else 81989

        await database.save_user(
            user_id=message.from_user.id,
            token=token,
            seller_id=seller_id,
            phone_number=phone,
            shops=shops,
            selected_shop_id=selected_shop_id
        )
        await state.clear()
        
        await wait_msg.edit_text(
            f"✅ **Успешная авторизация!**\n\n"
            f"👤 **Продавец ID:** `{seller_id}`\n"
            f"🏬 **Магазинов найдено:** {len(shops)}\n"
            f"🎯 **Выбран магазин:** `#{selected_shop_id}`\n\n"
            f"Теперь вы можете отслеживать или автоматически бронировать слоты.",
            parse_mode="Markdown"
        )
        await message.answer("Главное меню доступно:", reply_markup=keyboards.main_menu_keyboard())
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        await wait_msg.edit_text(
            f"❌ **Не удалось войти по этому токену.**\n\n"
            f"Ошибка: `{e}`\n\n"
            f"Пожалуйста, проверьте токен и попробуйте отправить снова."
        )

# --- Main Menu Handlers ---

@router.message(F.text == "📋 Накладные")
async def show_invoices(message: Message):
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    if not user:
        await message.answer("Пожалуйста, выполните команду /start для авторизации.")
        return

    shop_id = user.get("selected_shop_id")
    wait_msg = await message.answer("⏳ Загружаем список накладных...")
    try:
        async with UzumClient(token=user["token"]) as client:
            invoices = await client.get_invoices(shop_id=shop_id, size=30)

        if not invoices:
            await wait_msg.edit_text("ℹ️ У вас пока нет созданных накладных в этом магазине.")
            return

        lines = [f"📋 **Список накладных (Магазин #{shop_id}):**\n"]
        for inv in invoices[:15]:
            status = inv["status"]
            num = inv["invoice_number"] or inv["id"]
            qty = inv["total_items"]
            if inv["has_slot"]:
                slot = inv["slot_info"]
                slot_str = f"🟢 Слот: `{slot['from']}`"
            else:
                slot_str = "🔴 **Слот НЕ назначен**"

            lines.append(f"📦 **№{num}** ({qty} шт) — {status}\n   {slot_str}")

        await wait_msg.edit_text("\n\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка загрузки накладных: `{e}`", parse_mode="Markdown")

@router.message(F.text.in_(["🎯 Поймать слот (Автобронь)", "🔔 Уведомить о слоте"]))
async def start_slot_wizard(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    if not user:
        await message.answer("Пожалуйста, выполните команду /start для авторизации.")
        return

    mode = "AUTO_SNIPE" if "Поймать слот" in message.text else "NOTIFY"
    shop_id = user.get("selected_shop_id")
    
    wait_msg = await message.answer("⏳ Загружаем накладные для выбора...")
    try:
        async with UzumClient(token=user["token"]) as client:
            invoices = await client.get_invoices(shop_id=shop_id, size=50)

        if not invoices:
            await wait_msg.edit_text("❌ В этом магазине нет накладных. Сначала создайте накладную в кабинете Uzum.")
            return

        # Preselect invoices without slots by default
        default_selected = [inv["id"] for inv in invoices if not inv.get("has_slot")]

        wizard_cache[user_id] = {
            "invoices": invoices,
            "selected_ids": default_selected,
            "selected_dates": [],
            "stock_id": invoices[0]["stock_id"],
            "page": 0,
            "mode": mode
        }

        mode_title = "🎯 **Автобронирование (Снайпер)**" if mode == "AUTO_SNIPE" else "🔔 **Мониторинг слотов (Уведомления)**"
        text = (
            f"{mode_title}\n\n"
            f"**Шаг 1 из 3:** Выберите накладные для которых нужен тайм-слот.\n"
            f"🏬 Магазин: `#{shop_id}`\n\n"
            f"Отметьте нужные накладные галочками и нажмите **Далее**:"
        )

        kb = keyboards.invoices_multiselect_keyboard(
            invoices=invoices,
            selected_ids=default_selected,
            mode=mode,
            page=0
        )
        await wait_msg.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Ошибка: `{e}`", parse_mode="Markdown")

# --- Wizard Callbacks ---

@router.callback_query(F.data.startswith("toggle_inv:"))
async def cb_toggle_invoice(cb: CallbackQuery):
    _, inv_id_str, mode = cb.data.split(":")
    inv_id = int(inv_id_str)
    user_id = cb.from_user.id
    
    data = wizard_cache.get(user_id)
    if not data:
        await cb.answer("Сессия истекла, запустите выбор заново.", show_alert=True)
        return

    if inv_id in data["selected_ids"]:
        data["selected_ids"].remove(inv_id)
    else:
        data["selected_ids"].append(inv_id)

    kb = keyboards.invoices_multiselect_keyboard(
        invoices=data["invoices"],
        selected_ids=data["selected_ids"],
        mode=mode,
        page=data["page"]
    )
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("toggle_all_inv:"))
async def cb_toggle_all_invoices(cb: CallbackQuery):
    _, mode = cb.data.split(":")
    user_id = cb.from_user.id
    data = wizard_cache.get(user_id)
    if not data:
        await cb.answer("Сессия истекла.", show_alert=True)
        return

    all_ids = [inv["id"] for inv in data["invoices"]]
    if len(data["selected_ids"]) == len(all_ids):
        data["selected_ids"] = []
    else:
        data["selected_ids"] = list(all_ids)

    kb = keyboards.invoices_multiselect_keyboard(
        invoices=data["invoices"],
        selected_ids=data["selected_ids"],
        mode=mode,
        page=data["page"]
    )
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("inv_page:"))
async def cb_inv_page(cb: CallbackQuery):
    _, page_str, mode = cb.data.split(":")
    page = int(page_str)
    user_id = cb.from_user.id
    data = wizard_cache.get(user_id)
    if not data:
        await cb.answer()
        return

    data["page"] = page
    kb = keyboards.invoices_multiselect_keyboard(
        invoices=data["invoices"],
        selected_ids=data["selected_ids"],
        mode=mode,
        page=page
    )
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("confirm_inv:"))
async def cb_confirm_invoices(cb: CallbackQuery):
    _, mode = cb.data.split(":")
    user_id = cb.from_user.id
    data = wizard_cache.get(user_id)
    if not data or not data["selected_ids"]:
        await cb.answer("Выберите хотя бы одну накладную!", show_alert=True)
        return

    text = (
        f"📅 **Шаг 2 из 3:** Выберите желаемые даты доставки.\n\n"
        f"Выбрано накладных: `{len(data['selected_ids'])} шт.`\n\n"
        f"Нажмите на интересующие даты (можно выбрать несколько) или выберите **Любой день**:"
    )
    kb = keyboards.dates_selection_keyboard(selected_dates=data["selected_dates"], mode=mode)
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await cb.answer()

@router.callback_query(F.data.startswith("toggle_date:"))
async def cb_toggle_date(cb: CallbackQuery):
    _, date_str, mode = cb.data.split(":")
    user_id = cb.from_user.id
    data = wizard_cache.get(user_id)
    if not data:
        await cb.answer()
        return

    if date_str in data["selected_dates"]:
        data["selected_dates"].remove(date_str)
    else:
        data["selected_dates"].append(date_str)

    kb = keyboards.dates_selection_keyboard(selected_dates=data["selected_dates"], mode=mode)
    await cb.message.edit_reply_markup(reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("select_all_dates:"))
async def cb_select_all_dates(cb: CallbackQuery):
    _, mode = cb.data.split(":")
    user_id = cb.from_user.id
    data = wizard_cache.get(user_id)
    if not data:
        await cb.answer()
        return

    # Add next 14 days
    now = datetime.now()
    data["selected_dates"] = [(now + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]
    
    # Move directly to step 3
    text = (
        f"⏰ **Шаг 3 из 3:** Выберите удобное время приема.\n\n"
        f"Выбрано дат: `Все доступные дни`\n"
        f"Накладных: `{len(data['selected_ids'])}`\n\n"
        f"Выберите временной диапазон:"
    )
    await cb.message.edit_text(text, reply_markup=keyboards.time_range_keyboard(mode=mode), parse_mode="Markdown")
    await cb.answer()

@router.callback_query(F.data.startswith("confirm_dates:"))
async def cb_confirm_dates(cb: CallbackQuery):
    _, mode = cb.data.split(":")
    user_id = cb.from_user.id
    data = wizard_cache.get(user_id)
    if not data or not data["selected_dates"]:
        await cb.answer("Выберите хотя бы одну дату!", show_alert=True)
        return

    text = (
        f"⏰ **Шаг 3 из 3:** Выберите удобное время приема.\n\n"
        f"Выбрано дат: `{len(data['selected_dates'])}`\n"
        f"Накладных: `{len(data['selected_ids'])}`\n\n"
        f"Выберите временной диапазон:"
    )
    await cb.message.edit_text(text, reply_markup=keyboards.time_range_keyboard(mode=mode), parse_mode="Markdown")
    await cb.answer()

@router.callback_query(F.data.startswith("set_time:"))
async def cb_set_time_and_launch(cb: CallbackQuery):
    _, time_range, mode = cb.data.split(":")
    user_id = cb.from_user.id
    data = wizard_cache.get(user_id)
    if not data:
        await cb.answer("Ошибка: сессия истекла.", show_alert=True)
        return

    user = await database.get_user(user_id)
    task_id = str(uuid.uuid4())
    shop_id = user.get("selected_shop_id")

    # Create task in database
    await database.create_task(
        task_id=task_id,
        user_id=user_id,
        shop_id=shop_id,
        mode=mode,
        invoice_ids=data["selected_ids"],
        stock_id=data["stock_id"],
        target_dates=data["selected_dates"],
        time_range=time_range
    )

    # Launch in engine
    await engine.register_task(
        task_id=task_id,
        user_id=user_id,
        token=user["token"],
        shop_id=shop_id,
        mode=mode,
        invoice_ids=data["selected_ids"],
        stock_id=data["stock_id"],
        target_dates=data["selected_dates"],
        time_range=time_range
    )

    # Clean cache
    wizard_cache.pop(user_id, None)

    mode_name = "🎯 **АВТОБРОНИРОВАНИЕ (СНАЙПЕР)**" if mode == "AUTO_SNIPE" else "🔔 **МОНИТОРИНГ (УВЕДОМЛЕНИЕ)**"
    dates_preview = ", ".join([datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m") for d in data["selected_dates"][:5]])
    if len(data["selected_dates"]) > 5:
        dates_preview += f" и еще {len(data['selected_dates']) - 5} дн."

    success_text = (
        f"🚀 **ЗАДАЧА УСПЕШНО ЗАПУЩЕНА!**\n\n"
        f"⚙️ **Режим:** {mode_name}\n"
        f"📦 **Накладные:** `{len(data['selected_ids'])} шт.`\n"
        f"📅 **Даты:** `{dates_preview}`\n"
        f"⏰ **Интервал:** `{time_range}`\n"
        f"🏬 **Магазин:** `#{shop_id}`\n\n"
        f"⚡ Бот непрерывно опрашивает API Uzum. Как только появится подходящий слот, он выполнит свою задачу!"
    )
    await cb.message.edit_text(success_text, parse_mode="Markdown")
    await cb.answer()

@router.callback_query(F.data == "cancel_wizard")
async def cb_cancel_wizard(cb: CallbackQuery):
    user_id = cb.from_user.id
    wizard_cache.pop(user_id, None)
    await cb.message.edit_text("❌ Операция отменена.")
    await cb.answer()

# --- Active Tasks & Management ---

@router.message(F.text == "⚡ Активные задачи")
async def show_active_tasks(message: Message):
    user_id = message.from_user.id
    tasks = await database.get_user_tasks(user_id=user_id, status="RUNNING")
    
    if not tasks:
        await message.answer("ℹ️ У вас сейчас нет активных задач мониторинга или снайпера.\n\nЗапустите через меню: 🎯 **Поймать слот** или 🔔 **Уведомить о слоте**.")
        return

    lines = ["⚡ **Список ваших активных задач:**\n"]
    for t in tasks:
        mode_icon = "🎯 Снайпер (Автобронь)" if t["mode"] == "AUTO_SNIPE" else "🔔 Монитор"
        dates_str = ", ".join(t["target_dates"][:4])
        lines.append(
            f"🔹 **#{t['task_id'][:8]}** | {mode_icon}\n"
            f"   📦 Накладных: {len(t['invoice_ids'])} | 🏬 Магазин: #{t['shop_id']}\n"
            f"   📅 Даты: {dates_str}\n"
            f"   ⏰ Время: {t['time_range']}"
        )

    await message.answer(
        "\n\n".join(lines),
        reply_markup=keyboards.active_tasks_keyboard(tasks),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("cancel_task:"))
async def cb_cancel_task(cb: CallbackQuery):
    _, task_id = cb.data.split(":")
    await engine.cancel_task(task_id)
    await database.update_task_status(task_id, "CANCELLED")
    
    await cb.answer("Задача остановлена!", show_alert=True)
    await cb.message.edit_text(f"🛑 Задача `#{task_id[:8]}` успешно остановлена.")

# --- Settings & Shop Switch ---

@router.message(F.text == "⚙️ Магазин и Настройки")
async def show_settings(message: Message):
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    if not user:
        await message.answer("Выполните /start для авторизации.")
        return

    shops = user.get("shops", [])
    current_shop = user.get("selected_shop_id")

    text = (
        f"⚙️ **Настройки профиля Uzum Seller**\n\n"
        f"👤 **Seller ID:** `{user.get('seller_id')}`\n"
        f"📱 **Телефон:** `{user.get('phone_number')}`\n"
        f"🏬 **Текущий активный магазин:** `#{current_shop}`\n\n"
        f"Для смены магазина нажмите на него ниже:"
    )
    await message.answer(text, reply_markup=keyboards.shops_keyboard(shops, current_shop), parse_mode="Markdown")

@router.callback_query(F.data.startswith("set_shop:"))
async def cb_set_shop(cb: CallbackQuery):
    _, shop_id_str = cb.data.split(":")
    shop_id = int(shop_id_str)
    user_id = cb.from_user.id
    
    await database.update_selected_shop(user_id, shop_id)
    user = await database.get_user(user_id)
    
    await cb.answer(f"Выбран магазин #{shop_id}!")
    await cb.message.edit_reply_markup(reply_markup=keyboards.shops_keyboard(user.get("shops", []), shop_id))

@router.callback_query(F.data == "auth_reenter")
async def cb_auth_reenter(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SetupState.waiting_for_token)
    await cb.message.answer("🔑 Отправьте новый токен авторизации Uzum Seller:")
    await cb.answer()

# --- Quick Booking Callback from Notifications ---

@router.callback_query(F.data.startswith("book:"))
async def cb_quick_book(cb: CallbackQuery):
    parts = cb.data.split(":")
    shop_id = int(parts[1])
    stock_id = int(parts[2])
    time_from_ms = int(parts[3])
    invoice_ids = [int(x) for x in parts[4].split(",")]

    user_id = cb.from_user.id
    user = await database.get_user(user_id)
    if not user:
        await cb.answer("Авторизуйтесь через /start", show_alert=True)
        return

    await cb.answer("⚡ Бронируем слот...", show_alert=False)
    async with UzumClient(token=user["token"]) as client:
        success, msg, _ = await client.set_time_slot(
            shop_id=shop_id,
            invoice_ids=invoice_ids,
            stock_id=stock_id,
            time_from_ms=time_from_ms
        )

    if success:
        dt = datetime.fromtimestamp(time_from_ms / 1000)
        await cb.message.reply(f"🎉 **СЛОТ УСПЕШНО ЗАБРОНИРОВАН!**\n📅 {dt.strftime('%d.%m.%Y %H:%M')}\nНакладные: {invoice_ids}")
    else:
        await cb.message.reply(f"❌ Не удалось занять слот: `{msg}`", parse_mode="Markdown")

# --- Notification Dispatcher for Engine ---

async def engine_notify(user_id: int, text: str, slots_data: Optional[List[Dict[str, Any]]]):
    """Called by Engine when a slot is caught or found."""
    try:
        bot = Bot.get_current()
        if not bot:
            return
        
        # If slots data provided and it's a notification, build quick booking keyboard
        kb = None
        if slots_data and len(slots_data) > 0:
            user = await database.get_user(user_id)
            if user:
                # Find active tasks for this user to get invoices and stock
                tasks = await database.get_user_tasks(user_id, status="RUNNING")
                if tasks:
                    t = tasks[0]
                    kb = keyboards.instant_book_keyboard(
                        shop_id=t["shop_id"],
                        invoice_ids=t["invoice_ids"],
                        stock_id=t["stock_id"],
                        slots=slots_data
                    )

        await bot.send_message(chat_id=user_id, text=text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send engine notification to user {user_id}: {e}")

# --- Main Entry Point ---

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in .env! Please set your Telegram bot token.")
        print("\n" + "!"*60)
        print("ВНИМАНИЕ: BOT_TOKEN не указан в .env файле!")
        print("Создайте бота в @BotFather, получите токен и укажите его в .env файле.")
        print("!"*60 + "\n")
        return

    await database.init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Attach notification callback to engine
    engine.set_notify_callback(engine_notify)

    # Resume running tasks from database on startup
    # (can be expanded if needed)

    logger.info("Bot is starting polling...")
    logger.info("Uzum Timeslot Bot successfully started and listening for updates!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")

