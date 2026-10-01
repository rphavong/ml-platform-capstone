import { useEffect, useState } from "react";
import { fetchFlexUmap, fetchXeniumSpatial, type FetchState, type ScatterDataset } from "../api";
import { ScatterPlot } from "./charts/ScatterPlot";

function Panel({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        border: "1px solid #e5e5e5",
        borderRadius: 12,
        padding: 20,
        background: "white",
        boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
      }}
    >
      <h3 style={{ margin: 0, fontSize: 16 }}>{title}</h3>
      <p style={{ margin: "4px 0 12px", fontSize: 12.5, color: "#737373", maxWidth: 640 }}>{note}</p>
      {children}
    </div>
  );
}

function usePlot(fetcher: () => Promise<FetchState<ScatterDataset>>) {
  const [state, setState] = useState<FetchState<ScatterDataset>>({ status: "loading" });
  useEffect(() => {
    fetcher().then(setState);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return state;
}

export function CellMaps() {
  const flex = usePlot(fetchFlexUmap);
  const xenium = usePlot(fetchXeniumSpatial);

  return (
    <section style={{ marginTop: 36 }}>
      <h2 style={{ fontSize: 18, margin: "0 0 4px" }}>Where are the tumor cells?</h2>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: "#737373", maxWidth: 760 }}>
        Click any item in a legend to hide/show that cluster. Toggle "Color by" for a
        simplified tumor-vs-normal view or the full cell-type breakdown, and toggle
        between the two label sources to see where each model's own call lands.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        <Panel
          title="Flex — feature-space UMAP"
          note="Each point is one Flex cell, positioned by gene-expression similarity (not physical location - Flex is dissociated single-cell, there is no tissue coordinate). Exploratory view across all cells, not a held-out evaluation."
        >
          {flex.status === "loading" && <p style={{ fontSize: 13, color: "#737373" }}>Loading…</p>}
          {flex.status === "error" && (
            <p style={{ fontSize: 13, color: "#b91c1c" }}>
              Couldn't load flex-umap.json ({flex.message}). Generate it with{" "}
              <code>ec2-pipeline-pulled/export_embeddings.py</code>.
            </p>
          )}
          {flex.status === "ok" && (
            <ScatterPlot data={flex.data} labelA="True annotation" labelB="Model prediction" />
          )}
        </Panel>

        <Panel
          title="Xenium — actual tissue coordinates"
          note="Each point is one Xenium cell at its real physical position in the tissue section (not an embedding) - this is literally where in the sample each call was made, for the cropped spatial region endpoint3 was trained on."
        >
          {xenium.status === "loading" && <p style={{ fontSize: 13, color: "#737373" }}>Loading…</p>}
          {xenium.status === "error" && (
            <p style={{ fontSize: 13, color: "#b91c1c" }}>
              Couldn't load xenium-spatial.json ({xenium.message}). Generate it with{" "}
              <code>ec2-pipeline-pulled/export_embeddings.py</code>.
            </p>
          )}
          {xenium.status === "ok" && (
            <ScatterPlot data={xenium.data} labelA="Gene-only call" labelB="Spatial call" flipY />
          )}
        </Panel>
      </div>
    </section>
  );
}
