import json
import re

with open('seller.uzum.uz.har', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("Checking entries in HAR...")
for i, e in enumerate(data['log']['entries']):
    req = e['request']
    url = req['url']
    if 'api-seller.uzum.uz' in url or 'auth' in url:
        for h in req['headers']:
            if 'token' in h['name'].lower() or 'auth' in h['name'].lower() or 'cookie' in h['name'].lower():
                print(f"Req #{i} {req['method']} {url} -> Header {h['name']}: {h['value'][:100]}")
        if 'postData' in req:
            text = req['postData'].get('text', '')
            if 'token' in text or 'jwt' in text or 'phone' in text:
                print(f"Req #{i} {req['method']} {url} -> Body: {text[:200]}")
