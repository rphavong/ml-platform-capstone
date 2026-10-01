import { useEffect, useState } from "react";
import {
  fetchModelEval,
  type FetchState,
  type ModelEval,
  type EndpointEval,
  type ClassMetrics,
} from "../api";
import { ConfidenceHistogram, AgreementBars, ClassShiftChart } from "./charts/EvidenceCharts";

function pct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: "#fafafa",
        border: "1px solid #e5e5e5",
        borderRadius: 8,
        padding: "12px 16px",
        minWidth: 120,
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 600, color: "#171717" }}>{value}</div>
      <div style={{ fontSize: 12, color: "#737373", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function PerClassTable({ perClass }: { perClass: Record<string, ClassMetrics> }) {
  const [open, setOpen] = useState(false);
  const rows = Object.entries(perClass).sort((a, b) => b[1].support - a[1].support);
  return (
    <div style={{ marginTop: 12 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: "none",
          border: "none",
          color: "#2563eb",
          fontSize: 13,
          cursor: "pointer",
          padding: 0,
        }}
      >
        {open ? "Hide" : "Show"} per-class precision / recall / F1 ({rows.length} classes)
      </button>
      {open && (
        <table style={{ width: "100%", fontSize: 12.5, marginTop: 8, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#737373", borderBottom: "1px solid #e5e5e5" }}>
              <th style={{ padding: "4px 6px" }}>Class</th>
              <th style={{ padding: "4px 6px" }}>Precision</th>
              <th style={{ padding: "4px 6px" }}>Recall</th>
              <th style={{ padding: "4px 6px" }}>F1</th>
              <th style={{ padding: "4px 6px" }}>Support</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, m]) => (
              <tr key={name} style={{ borderBottom: "1px solid #f5f5f5" }}>
                <td style={{ padding: "4px 6px" }}>{name}</td>
                <td style={{ padding: "4px 6px" }}>{m.precision.toFixed(2)}</td>
                <td style={{ padding: "4px 6px" }}>{m.recall.toFixed(2)}</td>
                <td style={{ padding: "4px 6px" }}>{m["f1-score"].toFixed(2)}</td>
                <td style={{ padding: "4px 6px" }}>{m.support}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function EndpointEvalCard({
  title,
  evalData,
  cellsLabel,
}: {
  title: string;
  evalData: EndpointEval;
  cellsLabel: string;
}) {
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
      <p style={{ margin: "4px 0 12px", fontSize: 13, color: "#737373" }}>{evalData.description}</p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <StatTile label="Accuracy (held-out)" value={pct(evalData.accuracy)} />
        <StatTile label="Weighted F1" value={evalData.weighted_avg["f1-score"].toFixed(2)} />
        <StatTile label={cellsLabel} value={`${evalData.held_out_cells} / ${evalData.total_cells}`} />
      </div>
      {evalData.caveat && (
        <p style={{ fontSize: 12, color: "#92400e", background: "#fffbeb", padding: "8px 10px", borderRadius: 6, marginTop: 12 }}>
          ⚠ {evalData.caveat}
        </p>
      )}
      <PerClassTable perClass={evalData.per_class} />
    </div>
  );
}

export function ModelEvaluation() {
  const [data, setData] = useState<FetchState<ModelEval>>({ status: "loading" });

  useEffect(() => {
    fetchModelEval().then(setData);
  }, []);

  if (data.status === "loading") {
    return <p style={{ color: "#737373", fontSize: 13 }}>Loading model evaluation…</p>;
  }
  if (data.status === "error") {
    return (
      <p style={{ color: "#b91c1c", fontSize: 13 }}>
        Couldn't load model-eval.json ({data.message}). Generate it with{" "}
        <code>ec2-pipeline-pulled/export_model_eval.py</code>.
      </p>
    );
  }

  const { endpoint1_endpoint2, endpoint3, spatial_vs_gene_only: cmp } = data.data;

  return (
    <section style={{ marginTop: 36 }}>
      <h2 style={{ fontSize: 18, margin: "0 0 4px" }}>Model Quality (held-out evaluation)</h2>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: "#737373", maxWidth: 760 }}>
        {data.data.note}
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 20,
        }}
      >
        <EndpointEvalCard
          title="Endpoint 1 / 2 — shared classifier, evaluated on Flex"
          evalData={endpoint1_endpoint2}
          cellsLabel="Held-out FLEX cells (only Flex has ground truth)"
        />
        <EndpointEvalCard
          title="Endpoint 3 — spatial-aware classifier, evaluated on a Xenium region"
          evalData={endpoint3}
          cellsLabel="Held-out XENIUM-region cells (different, smaller dataset than endpoint1/2's)"
        />
      </div>

      <div
        style={{
          border: "1px solid #e5e5e5",
          borderRadius: 12,
          padding: 20,
          background: "white",
          boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
          marginTop: 20,
        }}
      >
        <h3 style={{ margin: 0, fontSize: 16 }}>Does spatial context actually help?</h3>
        <p style={{ margin: "4px 0 12px", fontSize: 13, color: "#737373" }}>{cmp.description}</p>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start" }}>
          <AgreementBars
            allCellsAgreement={cmp.overall_agreement}
            hardCellsAgreement={cmp.hard_case_agreement}
          />
          <StatTile
            label="Hard cells where spatial changed the call"
            value={`${cmp.hard_case_changed_count} / ${cmp.hard_case_count} (${pct(cmp.hard_case_changed_pct)})`}
          />
        </div>
        <div style={{ marginTop: 16 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: "#171717", margin: "0 0 2px" }}>
            Where "hard" comes from - confidence distribution across all {cmp.test_cells} test cells
          </p>
          <ConfidenceHistogram
            binEdges={cmp.confidence_histogram.bin_edges}
            counts={cmp.confidence_histogram.counts}
            median={cmp.hard_case_threshold_confidence}
          />
        </div>
        <div style={{ marginTop: 20 }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: "#171717", margin: "0 0 2px" }}>
            Which classes shift when spatial context is added (hard cells only, top 8 by magnitude)
          </p>
          <ClassShiftChart
            geneOnly={cmp.gene_only_hard_case_distribution}
            spatial={cmp.spatial_hard_case_distribution}
          />
        </div>
        <p style={{ fontSize: 12, color: "#737373", marginTop: 4 }}>
          "Hardest cells" = the bottom half of the gene-only model's own confidence scores -
          cells whose gene-expression pattern didn't clearly favor one class over the rest.
          Not a ground-truth difficulty measure (no independent Xenium truth exists); a measure
          of how decisive the model itself was.
        </p>
        <p style={{ fontSize: 13, color: "#171717", marginTop: 14, lineHeight: 1.5 }}>
          On the full held-out set, the spatial model agrees with the gene-only model{" "}
          {pct(cmp.overall_agreement)} of the time. Restricted to the {cmp.hard_case_count} cells
          the gene-only model was <em>least confident about</em> (confidence below its own median
          of {cmp.hard_case_threshold_confidence.toFixed(3)}), agreement drops to{" "}
          {pct(cmp.hard_case_agreement)} — spatial context changes nearly{" "}
          {pct(cmp.hard_case_changed_pct)} of the genuinely ambiguous calls, concentrating its
          disagreement exactly where gene expression alone is weakest.
        </p>
        <p style={{ fontSize: 12, color: "#737373", marginTop: 8 }}>
          Sanity check: re-predicting with the gene-only model matches its own earlier stored
          label {pct(cmp.sanity_check_agreement)} of the time — confirming that label is not
          independent ground truth, just this model's own prior call on the same genes.
        </p>
      </div>
    </section>
  );
}
