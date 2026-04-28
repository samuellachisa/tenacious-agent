import json
import csv
import random
from collections import defaultdict
import os

def load_data():
    try:
        with open("data/crunchbase_sample.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def size_band(num_employees_str):
    if not num_employees_str: return "Unknown"
    # Expected format: "51-200", "11-50", or raw numbers. Handle standard ranges.
    if isinstance(num_employees_str, str):
        if "10001" in num_employees_str or "1001" in num_employees_str or "501" in num_employees_str: return "500+"
        if "251-500" in num_employees_str or "201-500" in num_employees_str: return "201-500"
        if "51-250" in num_employees_str or "51-200" in num_employees_str: return "51-200"
        if "11-50" in num_employees_str: return "11-50"
        if "1-10" in num_employees_str: return "1-10"
        return num_employees_str # fallback
    return "Unknown"

def get_primary_sector(industries):
    if not industries: return "Unknown"
    if isinstance(industries, list):
        item = industries[0]
        if isinstance(item, dict):
            return item.get("value", item.get("name", str(item)))
        return str(item)
    if isinstance(industries, str):
        return industries.split(',')[0].strip()
    return "Unknown"

def extract_funding(company):
    # Try to extract the latest funding amount or total funding
    funds = company.get("funds_total", {})
    if isinstance(funds, dict):
        amt = funds.get("value", 0)
        return float(amt) if amt else 0.0
    
    # Try funding rounds
    rounds = company.get("funding_rounds_list", [])
    if rounds and isinstance(rounds, list):
        latest = rounds[0]
        if isinstance(latest, dict):
            money = latest.get("money_raised", {})
            if isinstance(money, dict):
                amt = money.get("value", 0)
                return float(amt) if amt else 0.0
    return 0.0

def mock_ai_maturity(company):
    # Parse real description and about
    desc = company.get("about", "") or ""
    full_desc = company.get("full_description", "") or ""
    combined = (str(desc) + " " + str(full_desc)).lower()
    
    score = 0
    if "ai" in combined or "machine learning" in combined or "data" in combined or "artificial intelligence" in combined:
        score += 1
    # Adding some probabilistic signal injection for the mock since we don't scrape live jobs here
    if random.random() > 0.7:  
        score += 1
    if random.random() > 0.9:  
        score += 1
    return min(score, 3)

def generate_market_space():
    print("Generating market space map from Crunchbase sample...")
    companies = load_data()
    
    if not companies or not isinstance(companies, list):
        print("Failed to load Crunchbase data.")
        return

    cells = defaultdict(lambda: {"count": 0, "total_funding": 0, "total_velocity": 0, "total_bench_match": 0})
    
    for c in companies:
        sector = get_primary_sector(c.get("industries", ""))
        size = size_band(c.get("num_employees", ""))
        readiness = mock_ai_maturity(c)
        funding = extract_funding(c)
        
        key = (sector, size, readiness)
        
        cells[key]["count"] += 1
        cells[key]["total_funding"] += funding
        
        # Simulate hiring velocity and bench-match score
        hiring_vel = random.uniform(0.5, 3.5) if readiness > 0 else random.uniform(-0.5, 1.5)
        bench_match = random.randint(1, 10) + (readiness * 2) 
        
        cells[key]["total_velocity"] += hiring_vel
        cells[key]["total_bench_match"] += min(bench_match, 10)

    # Output to CSV
    output_path = "data/market_space.csv"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Sector", "Company Size Band", "AI Readiness Band", "Cell Population", "Avg Funding", "Avg Hiring Velocity", "Avg Bench-Match Score"])
        
        # Sort by count descending to surface biggest cells
        sorted_cells = sorted(cells.items(), key=lambda x: x[1]["count"], reverse=True)
        
        for (sector, size, readiness), metrics in sorted_cells:
            count = metrics["count"]
            avg_funding = metrics["total_funding"] / count
            avg_velocity = metrics["total_velocity"] / count
            avg_bench_match = metrics["total_bench_match"] / count
            
            writer.writerow([
                sector, 
                size, 
                readiness, 
                count, 
                round(avg_funding, 2), 
                round(avg_velocity, 2), 
                round(avg_bench_match, 2)
            ])
            
    print(f"Market space successfully clustered into {len(cells)} cells and saved to {output_path}")

if __name__ == "__main__":
    generate_market_space()
