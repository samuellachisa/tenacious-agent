import csv

with open('data/crunchbase-companies.csv', 'r', encoding='utf-8') as f:
    data = list(csv.DictReader(f))

print("Companies with open roles:")
for record in data[:10]:
    name = record.get('name', 'Unknown')
    roles = record.get('open_roles', '')
    if roles:
        print(f"  {name}: {roles}")
