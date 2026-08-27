import json
from datetime import datetime

with open('seller.uzum.uz.har', 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, e in enumerate(data['log']['entries']):
    req = e['request']
    url = req['url']
    if 'shop/81989' in url:
        print(f"[{i}] {req['method']} {url}")
        if 'postData' in req:
            print(f"   Payload: {req['postData'].get('text')}")
        resp_text = e['response']['content'].get('text', '')
        # print parsed json summary
        try:
            resp_json = json.loads(resp_text)
            if isinstance(resp_json, dict) and 'payload' in resp_json:
                payload = resp_json['payload']
                if isinstance(payload, dict) and 'timeSlots' in payload:
                    slots = payload['timeSlots']
                    print(f"   Slots count: {len(slots)}")
                    for s in slots[:5]:
                        t_from = datetime.fromtimestamp(s['timeFrom']/1000).strftime('%Y-%m-%d %H:%M:%S')
                        t_to = datetime.fromtimestamp(s['timeTo']/1000).strftime('%Y-%m-%d %H:%M:%S')
                        print(f"     Slot: {t_from} -> {t_to} (raw: {s['timeFrom']})")
                elif isinstance(payload, list):
                    print(f"   Response payload list len: {len(payload)}")
                    for item in payload:
                        print(f"     Invoice {item.get('id')} / {item.get('invoiceNumber')} - Status: {item.get('status')} - Reservation: {item.get('timeSlotReservation')}")
                else:
                    print(f"   Response payload keys: {list(payload.keys()) if isinstance(payload, dict) else payload}")
            elif isinstance(resp_json, list):
                print(f"   Response list len: {len(resp_json)}")
                for item in resp_json[:3]:
                    if isinstance(item, dict):
                        print(f"     Invoice ID: {item.get('id')} Number: {item.get('invoiceNumber')} Status: {item.get('status')} TimeSlot: {item.get('timeSlotReservation')}")
            else:
                print(f"   Response keys: {list(resp_json.keys()) if isinstance(resp_json, dict) else resp_json}")
        except Exception as ex:
            print(f"   Response raw preview: {resp_text[:150]}")
        print()
