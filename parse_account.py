import json

with open('seller.uzum.uz.har', 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, e in enumerate(data['log']['entries']):
    if 'api/seller/account' in e['request']['url']:
        print(f"Entry {i} {e['request']['url']}:")
        print(e['response']['content'].get('text', ''))
        break
