import asyncio
import random
import logging
from typing import Dict, List, Any, Optional, Callable, Awaitable
from uzum_api import UzumClient
import database
from config import DEFAULT_POLL_INTERVAL

logger = logging.getLogger("UzumEngine")

def is_time_in_range(time_str: str, time_range: str) -> bool:
    """
    Checks if a time "HH:MM" satisfies the time_range condition.
    """
    if time_range == "ANY":
        return True
    
    hour, minute = map(int, time_str.split(":"))
    total_minutes = hour * 60 + minute

    if time_range == "MORNING": # 06:00 - 12:00
        return 6 * 60 <= total_minutes < 12 * 60
    elif time_range == "DAY": # 12:00 - 18:00
        return 12 * 60 <= total_minutes < 18 * 60
    elif time_range == "EVENING": # 18:00 - 23:59
        return 18 * 60 <= total_minutes <= 24 * 60
    elif "-" in time_range:
        try:
            start_s, end_s = time_range.split("-")
            sh, sm = map(int, start_s.strip().split(":"))
            eh, em = map(int, end_s.strip().split(":"))
            return (sh * 60 + sm) <= total_minutes <= (eh * 60 + em)
        except Exception:
            return True
    return True

class SlotTask:
    def __init__(
        self,
        task_id: str,
        user_id: int,
        token: str,
        shop_id: int,
        mode: str, # 'AUTO_SNIPE' or 'NOTIFY'
        invoice_ids: List[int],
        stock_id: int,
        target_dates: List[str], # ['2026-08-28', ...]
        time_range: str = "ANY",
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        notify_callback: Optional[Callable[[int, str, Optional[Any]], Awaitable[None]]] = None
    ):
        self.task_id = task_id
        self.user_id = user_id
        self.token = token
        self.shop_id = shop_id
        self.mode = mode
        self.invoice_ids = invoice_ids
        self.stock_id = stock_id
        self.target_dates = target_dates
        self.time_range = time_range
        self.poll_interval = poll_interval
        self.notify_callback = notify_callback
        
        self.is_running = False
        self._task_handle: Optional[asyncio.Task] = None
        self._notified_slot_ids = set()

    async def start(self):
        self.is_running = True
        self._task_handle = asyncio.create_task(self._run_loop())

    async def stop(self, status: str = "CANCELLED"):
        self.is_running = False
        if self._task_handle and not self._task_handle.done():
            self._task_handle.cancel()
        await database.update_task_status(self.task_id, status)

    async def _run_loop(self):
        logger.info(f"Task {self.task_id} started (Mode: {self.mode}) for user {self.user_id}")
        async with UzumClient(token=self.token) as client:
            consecutive_errors = 0
            while self.is_running:
                try:
                    slots = await client.get_available_slots(
                        shop_id=self.shop_id,
                        invoice_ids=self.invoice_ids
                    )
                    consecutive_errors = 0

                    # Filter slots by target dates and time window
                    matching_slots = []
                    for s in slots:
                        if s["date_str"] in self.target_dates:
                            if is_time_in_range(s["time_str"], self.time_range):
                                matching_slots.append(s)

                    if matching_slots:
                        logger.info(f"Task {self.task_id}: Found {len(matching_slots)} matching slots!")
                        
                        if self.mode == "AUTO_SNIPE":
                            # Sort slots by time (earliest first)
                            matching_slots.sort(key=lambda x: x["timeFrom"])
                            best_slot = matching_slots[0]
                            
                            success, msg, _ = await client.set_time_slot(
                                shop_id=self.shop_id,
                                invoice_ids=self.invoice_ids,
                                stock_id=self.stock_id,
                                time_from_ms=best_slot["timeFrom"]
                            )
                            
                            if success:
                                text = (
                                    f"🎯 **СЛОТ УСПЕШНО ЗАБРОНИРОВАН!**\n\n"
                                    f"📅 **Дата:** {best_slot['date_display']}\n"
                                    f"⏰ **Интервал:** {best_slot['time_range_display']}\n"
                                    f"📦 **Накладные:** {', '.join(map(str, self.invoice_ids))}\n"
                                    f"🏬 **Магазин:** #{self.shop_id}\n\n"
                                    f"✅ Задача завершена."
                                )
                                if self.notify_callback:
                                    await self.notify_callback(self.user_id, text, None)
                                await self.stop(status="COMPLETED")
                                return
                            else:
                                logger.warning(f"Snipe attempt failed: {msg}")
                                # continue loop, try next on next tick

                        elif self.mode == "NOTIFY":
                            # Send notification with action buttons for newly discovered slots
                            new_slots = [s for s in matching_slots if s["timeFrom"] not in self._notified_slot_ids]
                            if new_slots:
                                for s in new_slots:
                                    self._notified_slot_ids.add(s["timeFrom"])
                                
                                text = (
                                    f"🔔 **ОБНАРУЖЕН СВОБОДНЫЙ СЛОТ!**\n\n"
                                    f"📅 **Дата:** {new_slots[0]['date_display']}\n"
                                    f"⏰ **Интервалы:** {', '.join([s['time_range_display'] for s in new_slots[:5]])}\n"
                                    f"📦 **Для накладных:** {', '.join(map(str, self.invoice_ids))}\n"
                                    f"🏬 **Магазин:** #{self.shop_id}\n\n"
                                    f"Нажмите кнопку ниже, чтобы занять его прямо сейчас:"
                                )
                                if self.notify_callback:
                                    # Pass best slot data for inline keyboard quick booking
                                    await self.notify_callback(self.user_id, text, new_slots[:3])
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Task {self.task_id} error ({consecutive_errors}): {e}")
                    if consecutive_errors >= 10:
                        if self.notify_callback:
                            await self.notify_callback(
                                self.user_id,
                                f"⚠️ Задача #{self.task_id[:8]} приостановлена из-за повторяющихся сетевых ошибок.\n({e})",
                                None
                            )
                        await self.stop(status="FAILED")
                        return

                # Add slight random jitter (e.g. 1.8s - 2.4s) to look organic
                jitter = random.uniform(0.9, 1.2)
                await asyncio.sleep(self.poll_interval * jitter)

class EngineManager:
    """Singleton engine managing all active monitoring tasks."""
    def __init__(self):
        self.active_tasks: Dict[str, SlotTask] = {}
        self.notify_callback: Optional[Callable[[int, str, Optional[Any]], Awaitable[None]]] = None

    def set_notify_callback(self, cb: Callable[[int, str, Optional[Any]], Awaitable[None]]):
        self.notify_callback = cb

    async def register_task(
        self,
        task_id: str,
        user_id: int,
        token: str,
        shop_id: int,
        mode: str,
        invoice_ids: List[int],
        stock_id: int,
        target_dates: List[str],
        time_range: str = "ANY",
        poll_interval: float = DEFAULT_POLL_INTERVAL
    ) -> SlotTask:
        # If task with this ID exists, stop it first
        if task_id in self.active_tasks:
            await self.active_tasks[task_id].stop()

        task = SlotTask(
            task_id=task_id,
            user_id=user_id,
            token=token,
            shop_id=shop_id,
            mode=mode,
            invoice_ids=invoice_ids,
            stock_id=stock_id,
            target_dates=target_dates,
            time_range=time_range,
            poll_interval=poll_interval,
            notify_callback=self.notify_callback
        )
        self.active_tasks[task_id] = task
        await task.start()
        return task

    async def cancel_task(self, task_id: str) -> bool:
        if task_id in self.active_tasks:
            task = self.active_tasks.pop(task_id)
            await task.stop(status="CANCELLED")
            return True
        await database.update_task_status(task_id, "CANCELLED")
        return False

    def get_user_active_tasks(self, user_id: int) -> List[SlotTask]:
        return [t for t in self.active_tasks.values() if t.user_id == user_id and t.is_running]

# Global engine instance
engine = EngineManager()
