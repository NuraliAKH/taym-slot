from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import TIMEZONE_OFFSET

UZ_TZ = timezone(timedelta(hours=TIMEZONE_OFFSET))

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main persistent reply menu."""
    kb = [
        [
            KeyboardButton(text="🎯 Поймать слот (Автобронь)"),
            KeyboardButton(text="🔔 Уведомить о слоте")
        ],
        [
            KeyboardButton(text="📋 Накладные"),
            KeyboardButton(text="⚡ Активные задачи")
        ],
        [
            KeyboardButton(text="⚙️ Магазин и Настройки")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def shops_keyboard(shops: List[Dict[str, Any]], current_shop_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Inline buttons to switch active shop."""
    buttons = []
    for s in shops:
        sid = s.get("id")
        title = s.get("title", f"Магазин #{sid}")
        mark = "✅ " if sid == current_shop_id else ""
        buttons.append([InlineKeyboardButton(text=f"{mark}{title}", callback_data=f"set_shop:{sid}")])
    buttons.append([InlineKeyboardButton(text="🔑 Обновить токен", callback_data="auth_reenter")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def invoices_multiselect_keyboard(
    invoices: List[Dict[str, Any]],
    selected_ids: List[int],
    mode: str,
    page: int = 0,
    page_size: int = 6
) -> InlineKeyboardMarkup:
    """Multiselect inline keyboard for invoices."""
    total_pages = (len(invoices) + page_size - 1) // page_size or 1
    page_invoices = invoices[page * page_size : (page + 1) * page_size]
    
    rows = []
    for inv in page_invoices:
        inv_id = inv["id"]
        inv_num = inv["invoice_number"] or str(inv_id)
        is_sel = inv_id in selected_ids
        mark = "☑️" if is_sel else "⬜"
        
        slot_tag = " (есть слот)" if inv.get("has_slot") else " (без слота)"
        text = f"{mark} №{inv_num} | {inv.get('total_items', 0)} шт{slot_tag}"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"toggle_inv:{inv_id}:{mode}")])
    
    # Pagination row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"inv_page:{page-1}:{mode}"))
    nav_row.append(InlineKeyboardButton(text=f"Стр {page+1}/{total_pages}", callback_data="noop"))
    if (page + 1) < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"inv_page:{page+1}:{mode}"))
    if len(nav_row) > 1:
        rows.append(nav_row)

    # Action row
    action_row = []
    all_selected = len(selected_ids) == len(invoices) and len(invoices) > 0
    toggle_all_text = "Снять все" if all_selected else "Выбрать все"
    action_row.append(InlineKeyboardButton(text=toggle_all_text, callback_data=f"toggle_all_inv:{mode}"))
    
    if selected_ids:
        action_row.append(InlineKeyboardButton(
            text=f"Далее ({len(selected_ids)}) ➡️",
            callback_data=f"confirm_inv:{mode}"
        ))
    else:
        action_row.append(InlineKeyboardButton(
            text="Выберите накладную 👆",
            callback_data="noop"
        ))
    rows.append(action_row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_wizard")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def dates_selection_keyboard(selected_dates: List[str], mode: str) -> InlineKeyboardMarkup:
    """Select target dates for monitoring/sniper."""
    now = datetime.now(UZ_TZ)
    rows = []
    
    # Next 7 days
    date_buttons = []
    for i in range(7):
        target_dt = now + timedelta(days=i)
        date_str = target_dt.strftime("%Y-%m-%d")
        display = target_dt.strftime("%d.%m")
        if i == 0:
            display += " (Сегодня)"
        elif i == 1:
            display += " (Завтра)"
            
        mark = "✅ " if date_str in selected_dates else ""
        date_buttons.append(InlineKeyboardButton(
            text=f"{mark}{display}",
            callback_data=f"toggle_date:{date_str}:{mode}"
        ))
    
    # Group by 2 per row
    for j in range(0, len(date_buttons), 2):
        rows.append(date_buttons[j:j+2])
        
    action_row = []
    action_row.append(InlineKeyboardButton(text="📅 Любой день", callback_data=f"select_all_dates:{mode}"))
    if selected_dates:
        action_row.append(InlineKeyboardButton(
            text=f"Далее ({len(selected_dates)} дн.) ➡️",
            callback_data=f"confirm_dates:{mode}"
        ))
    rows.append(action_row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_wizard")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def time_range_keyboard(mode: str) -> InlineKeyboardMarkup:
    """Select preferred time window."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Любое время (24ч)", callback_data=f"set_time:ANY:{mode}")],
        [InlineKeyboardButton(text="🌅 Утро (06:00 - 12:00)", callback_data=f"set_time:MORNING:{mode}")],
        [InlineKeyboardButton(text="☀️ День (12:00 - 18:00)", callback_data=f"set_time:DAY:{mode}")],
        [InlineKeyboardButton(text="🌙 Вечер (18:00 - 24:00)", callback_data=f"set_time:EVENING:{mode}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_wizard")]
    ])

def instant_book_keyboard(shop_id: int, invoice_ids: List[int], stock_id: int, slots: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Instant booking buttons attached to alert message."""
    rows = []
    for s in slots:
        btn_text = f"⚡ Занять слот: {s['date_display']} {s['time_range_display']}"
        # invoice_ids compressed in callback
        inv_str = ",".join(map(str, invoice_ids))
        cb_data = f"book:{shop_id}:{stock_id}:{s['timeFrom']}:{inv_str}"
        # Telegram callback data limit is 64 bytes, handle safely
        if len(cb_data) <= 64:
            rows.append([InlineKeyboardButton(text=btn_text, callback_data=cb_data)])
        else:
            # Fallback if too many invoice IDs
            rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"book_quick:{shop_id}:{stock_id}:{s['timeFrom']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def active_tasks_keyboard(tasks: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """List of active running tasks with cancel buttons."""
    rows = []
    for t in tasks:
        tid = t["task_id"]
        mode_icon = "🎯 Снайпер" if t["mode"] == "AUTO_SNIPE" else "🔔 Монитор"
        dates_cnt = len(t["target_dates"])
        btn_text = f"❌ Стоп {mode_icon} ({dates_cnt} дат, #{tid[:6]})"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"cancel_task:{tid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
