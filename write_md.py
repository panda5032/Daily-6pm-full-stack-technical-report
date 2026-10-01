import sys
out = "C:/Users/panda/Desktop/03_Projects/StockInvesting/stock_research_reports/_sections_2026-06-24/12_china.md"
data = sys.stdin.read()
with open(out, "w", encoding="utf-8") as f:
    f.write(data)
print("WROTE", out, len(data), "chars")
