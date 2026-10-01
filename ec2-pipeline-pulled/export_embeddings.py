"""
Builds the two scatter-plot datasets for the dashboard's new "Where are the
tumor cells?" view:

  1. Flex UMAP (dashboard/public/flex-umap.json) - a 2D embedding of ALL 8,686
     Flex cells (feature-space clustering, same recipe as flex_module0.py/
     annotate_clusters.py, but UMAP itself wasn't computed back then so this
     computes it fresh with a fixed random_state). Colored by the real
     annotation (cell_type + CNV-based malignancy call) AND by what
     endpoint1_model itself predicts for each cell, so mismatches are visible.

  2. Xenium spatial map (dashboard/public/xenium-spatial.json) - NOT a UMAP.
     Xenium cells already have real physical tissue coordinates
     (adata.obsm["spatial"]), which is strictly more informative than an
     abstract embedding for "where in the tissue is the tumor" - so this uses
     the actual x/y coordinates of the cropped xenium_region.h5ad, colored by
     the gene-only model's call AND by endpoint3's spatial-aware call, so you
     can toggle between them and see exactly where spatial context changes
     the map.

Both files use a compact encoding (class name list + integer codes, not
repeated strings) to keep JSON size reasonable at these cell counts.

No retraining - endpoint1_model/endpoint3_model are loaded and only used to
predict. This IS an exploratory visualization, not a held-out evaluation -
Flex points include cells the model trained on, labeled clearly as such in
the output's `note` field.

Run with: python export_embeddings.py
Needs: scanpy (full scanpy now, not just anndata - UMAP needs its neighbor
graph machinery), umap-learn, joblib, numpy, pandas, scikit-learn
    pip install scanpy umap-learn
"""
import json

import numpy as np
import pandas as pd
import joblib
import scanpy as sc

MALIGNANT = "malignant_epithelial"
NORMAL_EPI = "normal_epithelial"


def bucket_malignancy(labels: np.ndarray) -> np.ndarray:
    out = np.where(
        labels == MALIGNANT, "malignant",
        np.where(labels == NORMAL_EPI, "normal_epithelial", "other (stroma/immune/endothelial)"),
    )
    return out


def encode(labels: np.ndarray):
    """Compact categorical encoding: (sorted unique class names, int codes)."""
    classes = sorted(set(labels.tolist()))
    index = {c: i for i, c in enumerate(classes)}
    codes = [index[l] for l in labels]
    return classes, codes


def export_flex_umap():
    adata = sc.read_h5ad("flex_final.h5ad")
    clf = joblib.load("endpoint1_model.joblib")
    le = joblib.load("endpoint1_label_encoder.joblib")
    feature_genes = joblib.load("endpoint1_feature_genes.joblib")

    adata.obs["final_label"] = adata.obs["cell_type"].astype(str)
    is_epithelial = adata.obs["cell_type"].isin(
        ["Epithelial_basal", "Epithelial_differentiated", "Epithelial_glandular"]
    )
    adata.obs.loc[is_epithelial, "final_label"] = adata.obs.loc[is_epithelial, "malignancy_status"]

    print("Computing UMAP on all", adata.n_obs, "Flex cells (HVG -> PCA -> neighbors -> UMAP)...")
    sc.pp.highly_variable_genes(adata, n_top_genes=2000)
    sc.pp.pca(adata, n_comps=50, use_highly_variable=True, random_state=42)
    sc.pp.neighbors(adata, n_neighbors=15, random_state=42)
    sc.tl.umap(adata, random_state=42)
    coords = adata.obsm["X_umap"]

    X_panel = adata[:, feature_genes].X
    if not isinstance(X_panel, np.ndarray):
        X_panel = X_panel.toarray()
    predicted = le.inverse_transform(clf.predict(X_panel))

    true_labels = adata.obs["final_label"].values
    malignancy_true = bucket_malignancy(true_labels)
    malignancy_pred = bucket_malignancy(predicted)

    cell_type_classes, cell_type_true_codes = encode(true_labels)
    _, cell_type_pred_codes = encode(predicted)
    # predicted codes must use the SAME class list as true, not its own
    idx_map = {c: i for i, c in enumerate(cell_type_classes)}
    cell_type_pred_codes = [idx_map[l] for l in predicted]

    malignancy_classes, malignancy_true_codes = encode(malignancy_true)
    midx_map = {c: i for i, c in enumerate(malignancy_classes)}
    malignancy_pred_codes = [midx_map[l] for l in malignancy_pred]

    output = {
        "note": "Exploratory UMAP of ALL Flex cells (not a held-out evaluation - "
        "includes cells endpoint1_model trained on). 'True' = the real CNV/marker-gene "
        "annotation from the pipeline; 'Predicted' = endpoint1_model's own call on the "
        "same cells, for spotting where the model's calls diverge from the annotation.",
        "n_cells": int(adata.n_obs),
        "cell_type_classes": cell_type_classes,
        "malignancy_classes": malignancy_classes,
        "points": [
            {
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
                "ct": cell_type_true_codes[i],
                "ctPred": cell_type_pred_codes[i],
                "m": malignancy_true_codes[i],
                "mPred": malignancy_pred_codes[i],
            }
            for i in range(adata.n_obs)
        ],
    }
    with open("../dashboard/public/flex-umap.json", "w") as f:
        json.dump(output, f)
    print(f"Saved ../dashboard/public/flex-umap.json ({adata.n_obs} cells)")


def export_xenium_spatial():
    adata = sc.read_h5ad("xenium_region.h5ad")

    import squidpy as sq
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

    clf3 = joblib.load("endpoint3_model.joblib")
    le3 = joblib.load("endpoint3_label_encoder.joblib")
    feature_genes = joblib.load("endpoint3_feature_genes.joblib")

    X_genes = adata[:, feature_genes].X
    if not isinstance(X_genes, np.ndarray):
        X_genes = X_genes.toarray()
    X_combined = np.hstack([X_genes, comp_df.values])
    spatial_pred = le3.inverse_transform(clf3.predict(X_combined))

    gene_only_labels = adata.obs["predicted_label"].values
    coords = adata.obsm["spatial"]

    malignancy_gene_only = bucket_malignancy(gene_only_labels)
    malignancy_spatial = bucket_malignancy(spatial_pred)

    cell_type_classes, gene_only_codes = encode(gene_only_labels)
    idx_map = {c: i for i, c in enumerate(cell_type_classes)}
    spatial_codes = [idx_map.get(l, -1) for l in spatial_pred]
    # any spatial-only class not seen in gene-only labels gets appended
    missing = sorted({l for l, c in zip(spatial_pred, spatial_codes) if c == -1})
    for m in missing:
        idx_map[m] = len(cell_type_classes)
        cell_type_classes.append(m)
    spatial_codes = [idx_map[l] for l in spatial_pred]

    malignancy_classes, gene_only_m_codes = encode(malignancy_gene_only)
    midx_map = {c: i for i, c in enumerate(malignancy_classes)}
    spatial_m_codes = [midx_map[l] for l in malignancy_spatial]

    output = {
        "note": "Physical tissue coordinates (not a UMAP) of the cropped Xenium "
        "spatial region - all cells, not just the held-out split. 'Gene-only' = "
        "endpoint1_model's call using expression alone; 'Spatial' = endpoint3_model's "
        "call using expression + neighborhood context, on the SAME cells.",
        "n_cells": int(adata.n_obs),
        "cell_type_classes": cell_type_classes,
        "malignancy_classes": malignancy_classes,
        "points": [
            {
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
                "ct": gene_only_codes[i],
                "ctPred": spatial_codes[i],
                "m": gene_only_m_codes[i],
                "mPred": spatial_m_codes[i],
            }
            for i in range(adata.n_obs)
        ],
    }
    with open("../dashboard/public/xenium-spatial.json", "w") as f:
        json.dump(output, f)
    print(f"Saved ../dashboard/public/xenium-spatial.json ({adata.n_obs} cells)")


if __name__ == "__main__":
    export_flex_umap()
    export_xenium_spatial()
