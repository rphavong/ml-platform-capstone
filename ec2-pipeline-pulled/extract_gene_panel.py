import json

with open("gene_panel.json") as f:
    panel = json.load(f)

targets = panel["payload"]["targets"]

# Keep only actual gene probes, drop negative controls / blanks / other probe types
gene_entries = [t for t in targets if t["type"]["descriptor"] == "gene"]
print("Gene-type entries:", len(gene_entries))

gene_names = sorted(set(t["type"]["data"]["name"] for t in gene_entries))
print("Unique gene symbols:", len(gene_names))

with open("xenium_panel_genes.txt", "w") as f:
    for g in gene_names:
        f.write(g + "\n")

print("Saved xenium_panel_genes.txt")
print("First 10:", gene_names[:10])
