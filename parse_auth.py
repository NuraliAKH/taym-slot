import json
import re

with open('seller.uzum.uz.har', 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, e in enumerate(data['log']['entries']):
    req = e['request']
    url = req['url']
    if 'auth' in url or 'token' in url or 'login' in url:
        print(f"[{i}] {req['method']} {url}")
        if 'postData' in req:
            print(f"  PostData: {req['postData'].get('text', '')}")
        print(f"  Status: {e['response']['status']}")
        print(f"  Resp: {e['response']['content'].get('text', '')[:300]}")
        print("-" * 50)
