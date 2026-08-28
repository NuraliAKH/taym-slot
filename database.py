import json
import aiosqlite
from typing import Optional, List, Dict, Any
import config

async def init_db():
    """Initializes the database schema."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                token TEXT NOT NULL,
                seller_id INTEGER,
                phone_number TEXT,
                selected_shop_id INTEGER,
                shops_json TEXT DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                shop_id INTEGER NOT NULL,
                mode TEXT NOT NULL, -- 'AUTO_SNIPE' or 'NOTIFY'
                invoice_ids_json TEXT NOT NULL, -- JSON list of invoice IDs
                stock_id INTEGER NOT NULL,
                target_dates_json TEXT NOT NULL, -- JSON list of dates 'YYYY-MM-DD'
                time_range TEXT DEFAULT 'ANY', -- 'ANY', 'MORNING', 'DAY', 'EVENING' or '08:00-14:00'
                status TEXT DEFAULT 'RUNNING', -- 'RUNNING', 'COMPLETED', 'CANCELLED', 'FAILED'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()

async def save_user(user_id: int, token: str, seller_id: int, phone_number: str, shops: List[Dict[str, Any]], selected_shop_id: Optional[int] = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        if selected_shop_id is None and shops:
            selected_shop_id = shops[0].get("id") or shops[0].get("shopId")

        await db.execute("""
            INSERT INTO users (user_id, token, seller_id, phone_number, selected_shop_id, shops_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                token = excluded.token,
                seller_id = excluded.seller_id,
                phone_number = excluded.phone_number,
                selected_shop_id = COALESCE(excluded.selected_shop_id, users.selected_shop_id),
                shops_json = excluded.shops_json,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, token, seller_id, phone_number, selected_shop_id, json.dumps(shops, ensure_ascii=False)))
        await db.commit()

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["shops"] = json.loads(data["shops_json"]) if data.get("shops_json") else []
            return data

async def update_selected_shop(user_id: int, shop_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET selected_shop_id = ? WHERE user_id = ?", (shop_id, user_id))
        await db.commit()

async def create_task(task_id: str, user_id: int, shop_id: int, mode: str, invoice_ids: List[int], stock_id: int, target_dates: List[str], time_range: str = "ANY"):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO tasks (task_id, user_id, shop_id, mode, invoice_ids_json, stock_id, target_dates_json, time_range, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')
        """, (task_id, user_id, shop_id, mode, json.dumps(invoice_ids), stock_id, json.dumps(target_dates), time_range))
        await db.commit()

async def get_user_tasks(user_id: int, status: Optional[str] = "RUNNING") -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM tasks WHERE user_id = ?"
        params = [user_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        
        async with db.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            tasks = []
            for r in rows:
                t = dict(r)
                t["invoice_ids"] = json.loads(t["invoice_ids_json"])
                t["target_dates"] = json.loads(t["target_dates_json"])
                tasks.append(t)
            return tasks

async def update_task_status(task_id: str, status: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
        await db.commit()
