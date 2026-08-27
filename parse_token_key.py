import json
import re

with open('seller.uzum.uz.har', 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, e in enumerate(data['log']['entries']):
    url = e['request']['url']
    if url.endswith('.js') or '/seller/js/' in url:
        content = e['response']['content'].get('text', '')
        if '/api/auth/seller/check_token' in content or 'check_token' in content:
            for m in re.finditer(r'.{0,200}check_token.{0,200}', content):
                print(f"Match in #{i}: {m.group(0)}")
