"""
Consolidates the 3 held-out evaluations (endpoint1/2 shared model on Flex,
endpoint3 spatial model on Xenium, and the gene-only-vs-spatial hard-case
comparison) into one JSON file the React dashboard reads directly, so the
instructor can see real held-out model-quality evidence in the UI instead of
just "is the endpoint reachable" health checks.

No retraining anywhere in this script - everything reloads already-saved
model/encoder/feature artifacts and re-predicts.

Writes: ../dashboard/public/model-eval.json  (committed to git - this is real
evidence, not a per-environment fixture like the gitignored test-payloads/)

Run with: python export_model_eval.py
Needs: anndata (or scanpy), squidpy, pandas, joblib, numpy, scikit-learn
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import joblib
import squidpy as sq
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

try:
    import anndata as ad
    read_h5ad = ad.read_h5ad
except ImportError:
    import scanpy as sc
    read_h5ad = sc.read_h5ad


def eval_endpoint1():
    adata = read_h5ad("flex_final.h5ad")
    clf = joblib.load("endpoint1_model.joblib")
    le = joblib.load("endpoint1_label_encoder.joblib")
    feature_genes = joblib.load("endpoint1_feature_genes.joblib")

    adata.obs["final_label"] = adata.obs["cell_type"].astype(str)
    is_epithelial = adata.obs["cell_type"].isin(
        ["Epithelial_basal", "Epithelial_differentiated", "Epithelial_glandular"]
    )
    adata.obs.loc[is_epithelial, "final_label"] = adata.obs.loc[is_epithelial, "malignancy_status"]

    adata_panel = adata[:, feature_genes].copy()
    X = adata_panel.X
    if not isinstance(X, np.ndarray):
        X = X.toarray()
    y = le.transform(adata_panel.obs["final_label"].values)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    y_pred = clf.predict(X_test)
    report = classification_report(
        y_test, y_pred, target_names=le.classes_, output_dict=True, zero_division=0
    )
    return {
        "description": "Endpoint 1 (Flex) / Endpoint 2 (Xenium) shared classifier - one "
        "XGBoost model trained on real Flex single-cell data, restricted to genes shared "
        "with the Xenium panel. This evaluation uses ONLY Flex cells (8,686 total, a "
        "completely different dataset from endpoint3's 32,497-cell Xenium region below) - "
        "Flex is the only place this project has independent ground truth to evaluate "
        "against. There is no equivalent independent accuracy number for Xenium; see "
        "spatial_vs_gene_only below for the honest way to assess Xenium behavior.",
        "data_source": "10x Genomics Flex single-cell (flex_final.h5ad)",
        "total_cells": int(len(y)),
        "held_out_cells": int(len(y_test)),
        "accuracy": report["accuracy"],
        "macro_avg": report["macro avg"],
        "weighted_avg": report["weighted avg"],
        "per_class": {
            k: v for k, v in report.items()
            if k not in ("accuracy", "macro avg", "weighted avg")
        },
    }


def eval_endpoint3_and_comparison():
    adata = read_h5ad("xenium_region.h5ad")
    sq.gr.spatial_neighbors(adata, n_neighs=10, coord_type="generic")
    conn = adata.obsp["spatial_connectivities"]
    label_dummies = pd.get_dummies(adata.obs["predicted_label"])
    neighbor_composition = conn.dot(label_dummies.values)
    neighbor_counts = np.asarray(conn.sum(axis=1)).flatten()
    neighbor_counts[neighbor_counts == 0] = 1
    neighbor_fractions = neighbor_composition / neighbor_counts[:, None]
    comp_df = pd.DataFrame(
        neighbor_fractions,
        columns=[f"nbr_frac_{c}" for c in label_dummies.columns],
        index=adata.obs_names,
    )
    adata.obs = adata.obs.join(comp_df)

    clf1 = joblib.load("endpoint1_model.joblib")
    le1 = joblib.load("endpoint1_label_encoder.joblib")
    clf3 = joblib.load("endpoint3_model.joblib")
    le3 = joblib.load("endpoint3_label_encoder.joblib")
    feature_genes = joblib.load("endpoint3_feature_genes.joblib")

    X_genes = adata[:, feature_genes].X
    if not isinstance(X_genes, np.ndarray):
        X_genes = X_genes.toarray()
    X_combined = np.hstack([X_genes, comp_df.values])
    y = le3.transform(adata.obs["predicted_label"].values)
    idx = np.arange(len(y))

    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X_combined, y, idx, test_size=0.2, random_state=42, stratify=y
    )

    y_pred = clf3.predict(X_test)
    report = classification_report(
        y_test, y_pred, target_names=le3.classes_, output_dict=True, zero_division=0
    )
    endpoint3 = {
        "description": "Endpoint 3 (Spatial) classifier - a separately-trained XGBoost "
        "model using gene expression plus engineered neighborhood-composition features "
        "(fraction of each cell's 10 nearest physical neighbors predicted as each class).",
        "data_source": "10x Genomics Xenium spatial region (xenium_region.h5ad)",
        "total_cells": int(len(y)),
        "held_out_cells": int(len(y_test)),
        "accuracy": report["accuracy"],
        "macro_avg": report["macro avg"],
        "weighted_avg": report["weighted avg"],
        "per_class": {
            k: v for k, v in report.items()
            if k not in ("accuracy", "macro avg", "weighted avg")
        },
        "caveat": "Evaluated against `predicted_label`, which is itself the gene-only "
        "model's own earlier call (see spatial_vs_gene_only below for why this accuracy "
        "number alone is not independent evidence of value - the hard-case comparison is).",
    }

    # Gene-only vs spatial comparison on the identical held-out cells
    X_genes_test = X_genes[idx_test]
    obs_test = adata.obs.iloc[idx_test]

    gene_only_pred = le1.inverse_transform(clf1.predict(X_genes_test))
    spatial_pred = le3.inverse_transform(y_pred)
    stored_label = obs_test["predicted_label"].values
    stored_confidence = obs_test["prediction_confidence"].values

    sanity_agreement = float((gene_only_pred == stored_label).mean())
    overall_agreement = float((gene_only_pred == spatial_pred).mean())

    median_conf = float(np.median(stored_confidence))
    hard_mask = stored_confidence < median_conf
    n_hard = int(hard_mask.sum())
    hard_agreement = float((gene_only_pred[hard_mask] == spatial_pred[hard_mask]).mean())
    n_changed_on_hard = int((gene_only_pred[hard_mask] != spatial_pred[hard_mask]).sum())

    hist_counts, hist_edges = np.histogram(stored_confidence, bins=20)
    confidence_histogram = {
        "bin_edges": hist_edges.tolist(),
        "counts": hist_counts.tolist(),
    }

    comparison = {
        "description": "Same held-out Xenium cells scored by BOTH models - does adding "
        "spatial neighborhood context actually change the call, and does it do so more "
        "on cells the gene-only model itself was least confident about?",
        "test_cells": int(len(idx_test)),
        "sanity_check_agreement": sanity_agreement,
        "sanity_check_note": "Gene-only model re-predicting now vs. the label it produced "
        "earlier on these same genes (pre-crop) - expected ~100%, confirms that label is "
        "not independent ground truth.",
        "overall_agreement": overall_agreement,
        "overall_changed_count": int(len(idx_test) - round(overall_agreement * len(idx_test))),
        "hard_case_threshold_confidence": median_conf,
        "hard_case_count": n_hard,
        "hard_case_agreement": hard_agreement,
        "hard_case_changed_count": n_changed_on_hard,
        "hard_case_changed_pct": n_changed_on_hard / n_hard if n_hard else 0.0,
        "gene_only_hard_case_distribution": pd.Series(gene_only_pred[hard_mask]).value_counts().to_dict(),
        "spatial_hard_case_distribution": pd.Series(spatial_pred[hard_mask]).value_counts().to_dict(),
        "confidence_histogram": confidence_histogram,
    }

    return endpoint3, comparison


def main():
    endpoint1 = eval_endpoint1()
    endpoint3, comparison = eval_endpoint3_and_comparison()

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "All numbers below are measured on held-out data the relevant model "
        "never trained on (stratified 80/20 split, random_state=42). No retraining was "
        "performed to generate this file - it reloads the already-deployed model "
        "artifacts and re-predicts.",
        "endpoint1_endpoint2": endpoint1,
        "endpoint3": endpoint3,
        "spatial_vs_gene_only": comparison,
    }

    out_path = "../dashboard/public/model-eval.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Saved {out_path}")
    print(f"endpoint1/2 accuracy: {endpoint1['accuracy']:.1%}")
    print(f"endpoint3 accuracy:   {endpoint3['accuracy']:.1%}")
    print(
        f"spatial vs gene-only: {comparison['overall_agreement']:.1%} agreement overall, "
        f"{comparison['hard_case_agreement']:.1%} on the {comparison['hard_case_count']} hardest cells"
    )


if __name__ == "__main__":
    main()
