import joblib
import json

def build_schema(model_dir, feature_genes_file, label_encoder_file, extra_features_file=None):
    feature_genes = joblib.load(f"{model_dir}/{feature_genes_file}")
    le = joblib.load(f"{model_dir}/{label_encoder_file}")
    schema = {
        "n_gene_features": len(feature_genes),
        "gene_order": feature_genes,
        "output_classes": list(le.classes_),
        "preprocessing": "normalize_total(target_sum=1e4) then log1p, applied BEFORE feature extraction",
    }
    if extra_features_file:
        extra = joblib.load(f"{model_dir}/{extra_features_file}")
        schema["n_spatial_features"] = len(extra)
        schema["spatial_feature_order"] = extra
    return schema

schema1 = build_schema("model_artifacts/endpoint1_flex", "endpoint1_feature_genes.joblib", "endpoint1_label_encoder.joblib")
with open("model_artifacts/endpoint1_flex/schema.json", "w") as f:
    json.dump(schema1, f, indent=2)

schema2 = build_schema("model_artifacts/endpoint2_xenium", "endpoint1_feature_genes.joblib", "endpoint1_label_encoder.joblib")
with open("model_artifacts/endpoint2_xenium/schema.json", "w") as f:
    json.dump(schema2, f, indent=2)

schema3 = build_schema("model_artifacts/endpoint3_spatial", "endpoint3_feature_genes.joblib", "endpoint3_label_encoder.joblib", "endpoint3_spatial_features.joblib")
with open("model_artifacts/endpoint3_spatial/schema.json", "w") as f:
    json.dump(schema3, f, indent=2)

print("Schemas written for all 3 endpoints")
