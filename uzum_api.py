import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import httpx
from config import UZUM_BASE_API_URL, DEFAULT_HEADERS, DEFAULT_TIMEOUT, TIMEZONE_OFFSET

UZ_TZ = timezone(timedelta(hours=TIMEZONE_OFFSET))

class UzumApiError(Exception):
    """Custom exception for Uzum API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

class UzumClient:
    """High performance asynchronous client for Uzum Seller API."""
    def __init__(self, token: str, base_url: str = UZUM_BASE_API_URL):
        self.token = token.strip()
        self.base_url = base_url.rstrip("/")
        
        headers = dict(DEFAULT_HEADERS)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["x-auth-token"] = self.token
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
        )

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def check_token(self) -> Dict[str, Any]:
        """
        Validates token via POST /api/auth/seller/check_token.
        Returns seller info and available shop IDs.
        """
        url = "/api/auth/seller/check_token"
        try:
            # check_token accepts application/x-www-form-urlencoded with token param
            resp = await self.client.post(
                url,
                data={"token": self.token},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if resp.status_code != 200:
                raise UzumApiError(f"Ошибка проверки токена: {resp.status_code} {resp.text}", resp.status_code)
            
            data = resp.json()
            # Extract shop IDs from permissions
            shop_ids = set()
            permissions = data.get("permissions", {})
            for perm_name, p_shops in permissions.items():
                if isinstance(p_shops, list):
                    for sid in p_shops:
                        shop_ids.add(sid)
            
            shops = [{"id": sid, "title": f"Магазин #{sid}"} for sid in sorted(shop_ids)]
            return {
                "valid": data.get("active", True),
                "user_name": data.get("user_name"),
                "phone_number": data.get("phoneNumber"),
                "seller_id": data.get("sellerId"),
                "shops": shops,
                "raw": data
            }
        except httpx.RequestError as e:
            raise UzumApiError(f"Сетевая ошибка при проверке токена: {e}")

    async def get_invoices(self, shop_id: int, page: int = 0, size: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches seller invoices for a given shop.
        GET /api/seller/shop/{shopId}/invoice?page={page}&size={size}
        """
        url = f"/api/seller/shop/{shop_id}/invoice"
        try:
            resp = await self.client.get(url, params={"page": page, "size": size})
            if resp.status_code != 200:
                raise UzumApiError(f"Ошибка получения накладных: {resp.status_code} {resp.text}", resp.status_code)
            
            items = resp.json()
            if not isinstance(items, list):
                return []
            
            invoices = []
            for item in items:
                # Determine timeSlot info if exists
                ts_res = item.get("timeSlotReservation")
                has_slot = ts_res is not None and ts_res.get("timeSlots")
                slot_info = None
                if has_slot and ts_res.get("timeSlots"):
                    first_slot = ts_res["timeSlots"][0]
                    t_from_dt = datetime.fromtimestamp(first_slot["timeFrom"] / 1000, tz=UZ_TZ)
                    t_to_dt = datetime.fromtimestamp(first_slot["timeTo"] / 1000, tz=UZ_TZ)
                    slot_info = {
                        "from": t_from_dt.strftime("%d.%m.%Y %H:%M"),
                        "to": t_to_dt.strftime("%H:%M"),
                        "raw_from": first_slot["timeFrom"],
                        "raw_to": first_slot["timeTo"]
                    }

                stock_data = item.get("stock") or {}
                stock_id = stock_data.get("id") or 34 # Default to 34 (Fullfilment Markazi)

                invoices.append({
                    "id": item.get("id"),
                    "invoice_number": str(item.get("invoiceNumber", "")),
                    "status": item.get("status") or item.get("invoiceStatus", {}).get("text", "CREATED"),
                    "status_code": item.get("invoiceStatus", {}).get("value", "CREATED"),
                    "date_created": item.get("dateCreated"),
                    "stock_id": stock_id,
                    "stock_title": stock_data.get("title", "Fullfilment Markazi"),
                    "total_items": item.get("totalToStock", 0),
                    "has_slot": bool(has_slot),
                    "slot_info": slot_info,
                    "raw": item
                })
            return invoices
        except httpx.RequestError as e:
            raise UzumApiError(f"Сетевая ошибка при загрузке накладных: {e}")

    async def get_available_slots(self, shop_id: int, invoice_ids: List[int], pool_source: str = "FULLFILMENT", time_from_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Queries available timeslots for specified invoices.
        POST /api/seller/shop/{shopId}/v2/invoice/time-slot/get
        """
        url = f"/api/seller/shop/{shop_id}/v2/invoice/time-slot/get"
        if time_from_ms is None:
            # Uzum requires timeFrom starting from tomorrow (UTC+5) for booking requests
            now = datetime.now(UZ_TZ)
            tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            time_from_ms = int(tomorrow_start.timestamp() * 1000)

        payload = {
            "invoiceIds": invoice_ids,
            "poolSource": pool_source,
            "timeFrom": time_from_ms
        }
        try:
            resp = await self.client.post(url, json=payload)
            if resp.status_code != 200:
                raise UzumApiError(f"Ошибка проверки слотов: {resp.status_code} {resp.text}", resp.status_code)
            
            data = resp.json()
            payload_data = data.get("payload", {})
            raw_slots = payload_data.get("timeSlots", [])
            
            slots = []
            for s in raw_slots:
                time_from_ms = s.get("timeFrom")
                time_to_ms = s.get("timeTo")
                dt_from = datetime.fromtimestamp(time_from_ms / 1000, tz=UZ_TZ)
                dt_to = datetime.fromtimestamp(time_to_ms / 1000, tz=UZ_TZ)
                
                slots.append({
                    "timeFrom": time_from_ms,
                    "timeTo": time_to_ms,
                    "date_str": dt_from.strftime("%Y-%m-%d"),
                    "date_display": dt_from.strftime("%d.%m.%Y"),
                    "time_str": dt_from.strftime("%H:%M"),
                    "time_range_display": f"{dt_from.strftime('%H:%M')} - {dt_to.strftime('%H:%M')}",
                    "datetime_from": dt_from,
                    "datetime_to": dt_to
                })
            return slots
        except httpx.RequestError as e:
            raise UzumApiError(f"Сетевая ошибка при запросе слотов: {e}")

    async def set_time_slot(self, shop_id: int, invoice_ids: List[int], stock_id: int, time_from_ms: int, pool_source: str = "FULLFILMENT") -> Tuple[bool, str, Any]:
        """
        Attempts to book the chosen timeslot.
        POST /api/seller/shop/{shopId}/v2/invoice/time-slot/set
        """
        url = f"/api/seller/shop/{shop_id}/v2/invoice/time-slot/set"
        payload = {
            "timeFrom": time_from_ms,
            "invoiceIds": invoice_ids,
            "stockId": stock_id,
            "poolSource": pool_source
        }
        try:
            resp = await self.client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return True, "Слот успешно забронирован!", data
            else:
                error_msg = resp.text
                try:
                    err_json = resp.json()
                    error_msg = err_json.get("message") or err_json.get("error") or str(err_json)
                except Exception:
                    pass
                return False, f"Ошибка бронирования ({resp.status_code}): {error_msg}", None
        except httpx.RequestError as e:
            return False, f"Сетевой сбой при отправке бронирования: {e}", None
