import json
import re

with open('seller.uzum.uz.har', 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, e in enumerate(data['log']['entries']):
    content = e['response']['content'].get('text', '')
    if 'check_token' in content:
        print(f"Found 'check_token' in entry #{i} {e['request']['url']}")
    if '4PgeDPAvPSEzgmV62Wgvwx-8UWE' in content:
        print(f"Found raw token in entry #{i} {e['request']['url']}")
