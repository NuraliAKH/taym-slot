import asyncio
import os
import shutil
import database
import keyboards
import config
from engine import is_time_in_range, engine
from uzum_api import UzumClient

async def test_suite():
    print("Testing config and imports...")
    assert config.DEFAULT_POLL_INTERVAL > 0
    print("  Config OK.")

    print("Testing database operations...")
    test_db = "test_uzum.db"
    config.DB_PATH = test_db
    if os.path.exists(test_db):
        os.remove(test_db)

    await database.init_db()
    
    # Test user save and get
    await database.save_user(
        user_id=12345,
        token="test_token_1234567890",
        seller_id=284483,
        phone_number="998335090304",
        shops=[{"id": 81989, "title": "Test Shop"}],
        selected_shop_id=81989
    )
    user = await database.get_user(12345)
    assert user is not None
    assert user["seller_id"] == 284483
    assert user["selected_shop_id"] == 81989
    print("  User DB OK.")

    # Test task creation
    await database.create_task(
        task_id="task-001",
        user_id=12345,
        shop_id=81989,
        mode="AUTO_SNIPE",
        invoice_ids=[3888933, 3888931],
        stock_id=34,
        target_dates=["2026-08-28", "2026-08-29"],
        time_range="MORNING"
    )
    tasks = await database.get_user_tasks(12345, status="RUNNING")
    assert len(tasks) == 1
    assert tasks[0]["invoice_ids"] == [3888933, 3888931]
    assert tasks[0]["time_range"] == "MORNING"
    print("  Task DB OK.")

    print("Testing engine time filters...")
    assert is_time_in_range("09:15", "MORNING") == True
    assert is_time_in_range("14:30", "MORNING") == False
    assert is_time_in_range("14:30", "DAY") == True
    assert is_time_in_range("20:00", "EVENING") == True
    assert is_time_in_range("10:00", "ANY") == True
    assert is_time_in_range("08:30", "08:00-12:00") == True
    assert is_time_in_range("13:30", "08:00-12:00") == False
    print("  Time filter OK.")

    print("Testing keyboard generation...")
    invoices_sample = [
        {"id": 3888933, "invoice_number": "1100038889338", "total_items": 10, "has_slot": False},
        {"id": 3888931, "invoice_number": "1100038889314", "total_items": 6, "has_slot": True}
    ]
    kb_inv = keyboards.invoices_multiselect_keyboard(invoices_sample, [3888933], "AUTO_SNIPE")
    assert len(kb_inv.inline_keyboard) > 0

    kb_dates = keyboards.dates_selection_keyboard(["2026-08-28"], "AUTO_SNIPE")
    assert len(kb_dates.inline_keyboard) > 0
    print("  Keyboards OK.")

    # Cleanup test db
    if os.path.exists(test_db):
        os.remove(test_db)

    print("\nALL MODULE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test_suite())
