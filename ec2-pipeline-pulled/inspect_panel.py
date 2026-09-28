import json

with open("gene_panel.json") as f:
    panel = json.load(f)

print("Top-level keys:", list(panel.keys()))

# Print the structure of whatever the main content looks like, one level deep
for key in panel.keys():
    val = panel[key]
    if isinstance(val, list):
        print(f"\n'{key}' is a list of {len(val)} items. First item:")
        print(val[0])
    elif isinstance(val, dict):
        print(f"\n'{key}' is a dict with keys: {list(val.keys())}")
    else:
        print(f"\n'{key}': {val}")
