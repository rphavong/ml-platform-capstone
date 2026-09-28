import json

with open("gene_panel.json") as f:
    panel = json.load(f)

targets = panel["payload"]["targets"]
print("Number of targets:", len(targets))
print("\nFirst target entry (full structure):")
print(json.dumps(targets[0], indent=2))

print("\n'panel' section:")
print(json.dumps(panel["payload"]["panel"], indent=2))
