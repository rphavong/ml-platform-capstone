import { useState } from "react";

// Palette slots used here (fixed order, validated adjacent-pair CVD-safe):
// slot 1 blue = "confident / baseline / increase", slot 2 orange = "hard / subset",
// slot 8 red = "decrease" (paired with blue as the diverging blue<->red pair).
const BLUE = "#2a78d6";
const ORANGE = "#eb6834";
const RED = "#e34948";
const INK_SECONDARY = "#52514e";
const INK_MUTED = "#898781";
const GRIDLINE = "#e1e0d9";
const SURFACE = "#fcfcfb";

function fmtPct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

// --- 1. Confidence histogram ------------------------------------------------
// Shows the distribution of the gene-only model's own top-class confidence
// across the held-out test cells, with a reference line at the median - the
// exact threshold that defines "hard cells" elsewhere on this page.
export function ConfidenceHistogram({
  binEdges,
  counts,
  median,
}: {
  binEdges: number[];
  counts: number[];
  median: number;
}) {
  const width = 640;
  const height = 220;
  const padL = 44;
  const padR = 16;
  const padT = 16;
  const padB = 32;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const maxCount = Math.max(...counts, 1);
  const minEdge = binEdges[0];
  const maxEdge = binEdges[binEdges.length - 1];
  const span = maxEdge - minEdge || 1;

  const barGap = 2;
  const barW = Math.max(1, plotW / counts.length - barGap);

  const [hover, setHover] = useState<number | null>(null);
  const medianX = padL + ((median - minEdge) / span) * plotW;

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 6 }}>
        <LegendSwatch color={BLUE} label="Confident (≥ median)" />
        <LegendSwatch color={ORANGE} label="Hard cells (< median)" />
      </div>
      <svg width={width} height={height} role="img" aria-label="Histogram of model confidence scores">
        <rect x={0} y={0} width={width} height={height} fill={SURFACE} />
        {/* gridlines */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const y = padT + plotH * (1 - f);
          return (
            <line key={f} x1={padL} x2={width - padR} y1={y} y2={y} stroke={GRIDLINE} strokeWidth={1} />
          );
        })}
        {/* bars */}
        {counts.map((c, i) => {
          const binCenter = (binEdges[i] + binEdges[i + 1]) / 2;
          const color = binCenter < median ? ORANGE : BLUE;
          const x = padL + (i * plotW) / counts.length;
          const h = (c / maxCount) * plotH;
          const y = padT + plotH - h;
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={barW}
              height={Math.max(h, 0)}
              fill={color}
              rx={2}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              opacity={hover === null || hover === i ? 1 : 0.55}
            >
              <title>{`${binEdges[i].toFixed(2)}–${binEdges[i + 1].toFixed(2)}: ${c} cells`}</title>
            </rect>
          );
        })}
        {/* median reference line */}
        <line x1={medianX} x2={medianX} y1={padT} y2={padT + plotH} stroke={INK_SECONDARY} strokeWidth={1.5} />
        <text x={medianX + 4} y={padT + 10} fontSize={11} fill={INK_SECONDARY}>
          median {median.toFixed(3)}
        </text>
        {/* x-axis labels */}
        <text x={padL} y={height - 10} fontSize={11} fill={INK_MUTED}>
          {minEdge.toFixed(2)}
        </text>
        <text x={width - padR} y={height - 10} fontSize={11} fill={INK_MUTED} textAnchor="end">
          {maxEdge.toFixed(2)}
        </text>
        <text x={(padL + width - padR) / 2} y={height - 10} fontSize={11} fill={INK_MUTED} textAnchor="middle">
          confidence (top predicted class probability)
        </text>
      </svg>
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: INK_SECONDARY }}>
      <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: "inline-block" }} />
      {label}
    </span>
  );
}

// --- 2. Agreement comparison bars --------------------------------------------
// Two bars, same metric (agreement rate), two subsets - the headline number.
export function AgreementBars({
  allCellsAgreement,
  hardCellsAgreement,
}: {
  allCellsAgreement: number;
  hardCellsAgreement: number;
}) {
  const width = 320;
  const height = 180;
  const padT = 20;
  const padB = 36;
  const plotH = height - padT - padB;
  const barW = 64;
  const gap = 56;
  const x1 = 56;
  const x2 = x1 + barW + gap;

  const bars = [
    { x: x1, v: allCellsAgreement, color: BLUE, label: "All cells" },
    { x: x2, v: hardCellsAgreement, color: ORANGE, label: "Hardest cells" },
  ];

  return (
    <svg width={width} height={height} role="img" aria-label="Agreement rate: all cells vs hardest cells">
      <rect x={0} y={0} width={width} height={height} fill={SURFACE} />
      <line x1={0} x2={width} y1={padT + plotH} y2={padT + plotH} stroke={GRIDLINE} strokeWidth={1} />
      {bars.map((b) => {
        const h = b.v * plotH;
        const y = padT + plotH - h;
        return (
          <g key={b.label}>
            <rect x={b.x} y={y} width={barW} height={h} fill={b.color} rx={4}>
              <title>{`${b.label}: ${fmtPct(b.v)} agreement`}</title>
            </rect>
            <text x={b.x + barW / 2} y={y - 8} fontSize={13} fontWeight={600} fill={INK_SECONDARY} textAnchor="middle">
              {fmtPct(b.v)}
            </text>
            <text x={b.x + barW / 2} y={height - 14} fontSize={11} fill={INK_MUTED} textAnchor="middle">
              {b.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// --- 3. Class-call shift on hard cells ---------------------------------------
// Diverging horizontal bars: for the hardest cells, how many MORE (blue) or
// FEWER (red) calls did the spatial model make for each class, vs gene-only.
export function ClassShiftChart({
  geneOnly,
  spatial,
}: {
  geneOnly: Record<string, number>;
  spatial: Record<string, number>;
}) {
  const classes = Array.from(new Set([...Object.keys(geneOnly), ...Object.keys(spatial)]));
  const deltas = classes
    .map((c) => ({ name: c, delta: (spatial[c] ?? 0) - (geneOnly[c] ?? 0) }))
    .filter((d) => d.delta !== 0)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 8);

  if (deltas.length === 0) {
    return <p style={{ fontSize: 12, color: INK_MUTED }}>No net change in class counts on the hard cells.</p>;
  }

  const width = 560;
  const rowH = 26;
  const padL = 150;
  const padR = 48;
  const height = deltas.length * rowH + 20;
  const maxAbs = Math.max(...deltas.map((d) => Math.abs(d.delta)));
  const plotW = width - padL - padR;
  const midX = padL + plotW / 2;
  const scale = plotW / 2 / (maxAbs || 1);

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", gap: 16, marginBottom: 6 }}>
        <LegendSwatch color={BLUE} label="More calls with spatial context" />
        <LegendSwatch color={RED} label="Fewer calls with spatial context" />
      </div>
      <svg width={width} height={height} role="img" aria-label="Class call shift on hardest cells, gene-only vs spatial">
        <rect x={0} y={0} width={width} height={height} fill={SURFACE} />
        <line x1={midX} x2={midX} y1={4} y2={height - 4} stroke={GRIDLINE} strokeWidth={1} />
        {deltas.map((d, i) => {
          const y = i * rowH + 4;
          const barW = Math.abs(d.delta) * scale;
          const positive = d.delta > 0;
          const x = positive ? midX : midX - barW;
          const color = positive ? BLUE : RED;
          return (
            <g key={d.name}>
              <text x={padL - 8} y={y + rowH / 2 + 4} fontSize={12} fill={INK_SECONDARY} textAnchor="end">
                {d.name}
              </text>
              <rect x={x} y={y} width={Math.max(barW, 1)} height={rowH - 8} fill={color} rx={3}>
                <title>{`${d.name}: ${d.delta > 0 ? "+" : ""}${d.delta} cells`}</title>
              </rect>
              <text
                x={positive ? x + barW + 6 : x - 6}
                y={y + rowH / 2 - 4}
                fontSize={11.5}
                fontWeight={600}
                fill={INK_SECONDARY}
                textAnchor={positive ? "start" : "end"}
              >
                {d.delta > 0 ? "+" : ""}
                {d.delta}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
