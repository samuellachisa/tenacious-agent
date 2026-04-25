import json

with open('data/crunchbase_sample.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("Companies with open roles:")
for record in data[:10]:
    name = record.get('name', 'Unknown')
    roles = record.get('open_roles', [])
    if roles:
        print(f"  {name}: {len(roles)} roles")
        print(f"    Sample roles: {roles[:3]}")
