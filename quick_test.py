import asyncio
import sys
from datetime import datetime
from uzum_api import UzumClient, UZ_TZ
import database
import config

sys.stdout.reconfigure(encoding='utf-8')

async def run_diagnostics():
    print("=" * 60)
    print("🚀 БЫСТРАЯ ПРОВЕРКА СИСТЕМЫ ПОИСКА И БРОНИРОВАНИЯ СЛОТОВ")
    print("=" * 60)

    # 1. Проверка базы данных
    await database.init_db()
    users = []
    async with database.aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = database.aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY updated_at DESC") as cursor:
            rows = await cursor.fetchall()
            users = [dict(r) for r in rows]

    if not users:
        print("❌ В базе данных нет сохраненных пользователей с токеном.")
        print("   Запустите бота (python bot.py) и отправьте токен через /start.")
        return

    # Берем последнего активного пользователя
    user = users[0]
    user_id = user["user_id"]
    token = user["token"]
    shop_id = user.get("selected_shop_id") or 81989

    print(f"✅ База данных подключена успешно.")
    print(f"👤 Пользователь: ID {user_id} | Магазин: #{shop_id}")
    print(f"🔑 Токен (маска): {token[:6]}...{token[-4:]}")
    print("-" * 60)

    async with UzumClient(token=token) as client:
        # 2. Проверка токена
        print("⏳ [1/3] Проверяем авторизацию токена в Uzum Seller API...")
        try:
            auth_info = await client.check_token()
            if auth_info.get("valid"):
                print(f"✅ Токен АКТИВЕН! Продавец ID: {auth_info.get('seller_id')}, Телефон: {auth_info.get('phone_number')}")
            else:
                print("⚠️ Токен вернул статус неактивен.")
        except Exception as e:
            print(f"❌ Ошибка проверки токена: {e}")
            return

        print("-" * 60)

        # 3. Проверка получения накладных
        print(f"⏳ [2/3] Загружаем накладные магазина #{shop_id}...")
        try:
            invoices = await client.get_invoices(shop_id=shop_id, size=10)
            print(f"✅ Успешно получено {len(invoices)} накладных:")
            for inv in invoices[:4]:
                slot_mark = f"🟢 Слот: {inv['slot_info']['from']}" if inv['has_slot'] else "🔴 Без слота"
                print(f"   • №{inv['invoice_number']} (ID: {inv['id']}) — {inv['status']} | {slot_mark}")
        except Exception as e:
            print(f"❌ Ошибка получения накладных: {e}")
            return

        print("-" * 60)

        # 4. Проверка получения доступных слотов
        if not invoices:
            print("⚠️ Нет накладных для проверки слотов.")
            return

        test_invoice_ids = [inv["id"] for inv in invoices[:2]]
        print(f"⏳ [3/3] Запрашиваем доступные тайм-слоты для накладных {test_invoice_ids}...")
        try:
            slots = await client.get_available_slots(shop_id=shop_id, invoice_ids=test_invoice_ids)
            print(f"✅ УСПЕХ! Найдено свободных слотов в системе: {len(slots)}")
            for s in slots[:5]:
                print(f"   📅 {s['date_display']} | Интервал: {s['time_range_display']} (timestamp: {s['timeFrom']})")
            if len(slots) > 5:
                print(f"   ... и еще {len(slots) - 5} доступных слотов на следующие дни.")
        except Exception as e:
            print(f"❌ Ошибка запроса слотов: {e}")
            return

    print("=" * 60)
    print("🎉 ВСЕ ПРОВЕРКИ УСПЕШНО ПРОЙДЕНЫ! API ПОЛНОСТЬЮ РАБОТАЕТ!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
