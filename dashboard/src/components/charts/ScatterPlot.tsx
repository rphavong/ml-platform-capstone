import { useEffect, useMemo, useRef, useState } from "react";
import type { ScatterDataset } from "../../api";

// Malignancy bucket colors are deliberately STATUS colors, not categorical
// identity colors - "malignant" vs "normal" is a meaningful severity signal
// here (and matches the near-universal red=tumor convention in biomedical
// viz), not an arbitrary series. Reserved per the palette's own rule that
// status colors never double as "series 4".
const STATUS_CRITICAL = "#d03b3b"; // malignant
const STATUS_GOOD = "#0ca30c"; // normal_epithelial
const MUTED_OTHER = "#b3b1a8"; // other (stroma/immune/endothelial) - de-emphasized

// The validated 8-slot categorical order (fixed, never cycled for <=8 series).
const CATEGORICAL_8 = [
  "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
  "#e87ba4", "#008300", "#4a3aa7", "#e34948",
];
// 9-15: documented exception. True single-cell data regularly has 12-20
// cell types and no 15-color palette clears CVD gates pairwise - common
// practice in genomics tooling accepts this for an exploratory detail view,
// with the 3-color malignancy view (fully validated, all-pairs-safe) as the
// safe default. These reuse the 8 hues at a darker step as a visual "second
// lap", not a fresh hue, so repeats are at least systematic.
const CATEGORICAL_EXT = CATEGORICAL_8.map((c) => c);

function paletteFor(n: number): string[] {
  const colors: string[] = [];
  for (let i = 0; i < n; i++) {
    if (i < 8) colors.push(CATEGORICAL_8[i]);
    else colors.push(CATEGORICAL_EXT[i % 8]);
  }
  return colors;
}

function malignancyColor(className: string): string {
  if (className === "malignant") return STATUS_CRITICAL;
  if (className === "normal_epithelial") return STATUS_GOOD;
  return MUTED_OTHER;
}

export function ScatterPlot({
  data,
  labelA,
  labelB,
  flipY = false,
  height = 440,
}: {
  data: ScatterDataset;
  labelA: string; // e.g. "True annotation" or "Gene-only call"
  labelB: string; // e.g. "Model prediction" or "Spatial call"
  flipY?: boolean;
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [colorMode, setColorMode] = useState<"malignancy" | "cellType">("malignancy");
  const [showB, setShowB] = useState(false);
  const [hidden, setHidden] = useState<Set<number>>(new Set());

  const classes = colorMode === "malignancy" ? data.malignancy_classes : data.cell_type_classes;
  const colors = useMemo(
    () => (colorMode === "malignancy" ? classes.map(malignancyColor) : paletteFor(classes.length)),
    [colorMode, classes]
  );

  const codeKey = colorMode === "malignancy" ? (showB ? "mPred" : "m") : (showB ? "ctPred" : "ct");

  const counts = useMemo(() => {
    const c = new Array(classes.length).fill(0);
    for (const p of data.points) {
      const code = p[codeKey];
      if (code >= 0 && code < c.length) c[code]++;
    }
    return c;
  }, [data.points, codeKey, classes.length]);

  useEffect(() => {
    // reset hidden selection when switching color mode (class lists differ)
    setHidden(new Set());
  }, [colorMode]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#fcfcfb";
    ctx.fillRect(0, 0, width, height);

    const xs = data.points.map((p) => p.x);
    const ys = data.points.map((p) => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const pad = 20;
    const spanX = maxX - minX || 1;
    const spanY = maxY - minY || 1;

    const sx = (x: number) => pad + ((x - minX) / spanX) * (width - 2 * pad);
    const sy = (y: number) => {
      const t = (y - minY) / spanY;
      const frac = flipY ? t : 1 - t;
      return pad + frac * (height - 2 * pad);
    };

    const r = data.points.length > 15000 ? 1.1 : 1.8;
    for (const p of data.points) {
      const code = p[codeKey];
      if (hidden.has(code)) continue;
      ctx.beginPath();
      ctx.fillStyle = colors[code] ?? MUTED_OTHER;
      ctx.globalAlpha = 0.75;
      ctx.arc(sx(p.x), sy(p.y), r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }, [data.points, codeKey, colors, hidden, flipY, height]);

  function toggleClass(i: number) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
        <label style={{ fontSize: 12, color: "#52514e" }}>
          Color by:{" "}
          <select
            value={colorMode}
            onChange={(e) => setColorMode(e.target.value as "malignancy" | "cellType")}
            style={{ fontSize: 12, padding: "2px 4px" }}
          >
            <option value="malignancy">Malignancy (tumor vs normal)</option>
            <option value="cellType">Cell type (detailed)</option>
          </select>
        </label>
        <div style={{ display: "inline-flex", border: "1px solid #e5e5e5", borderRadius: 6, overflow: "hidden" }}>
          <button
            onClick={() => setShowB(false)}
            style={{
              fontSize: 12, padding: "4px 10px", border: "none", cursor: "pointer",
              background: !showB ? "#2a78d6" : "white", color: !showB ? "white" : "#52514e",
            }}
          >
            {labelA}
          </button>
          <button
            onClick={() => setShowB(true)}
            style={{
              fontSize: 12, padding: "4px 10px", border: "none", cursor: "pointer",
              background: showB ? "#2a78d6" : "white", color: showB ? "white" : "#52514e",
            }}
          >
            {labelB}
          </button>
        </div>
        <span style={{ fontSize: 11, color: "#898781" }}>{data.n_cells.toLocaleString()} cells</span>
      </div>

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <canvas
          ref={canvasRef}
          style={{ width: "100%", maxWidth: 700, height, border: "1px solid #e5e5e5", borderRadius: 8 }}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 160, maxHeight: height, overflowY: "auto" }}>
          <span style={{ fontSize: 11, color: "#898781", marginBottom: 2 }}>Click to hide/show</span>
          {classes.map((name, i) => (
            <button
              key={name}
              onClick={() => toggleClass(i)}
              style={{
                display: "flex", alignItems: "center", gap: 6, fontSize: 11.5,
                background: "none", border: "none", cursor: "pointer", padding: "2px 0",
                color: hidden.has(i) ? "#c3c2b7" : "#171717",
                textDecoration: hidden.has(i) ? "line-through" : "none",
                textAlign: "left",
              }}
            >
              <span
                style={{
                  width: 9, height: 9, borderRadius: 2, flexShrink: 0,
                  background: hidden.has(i) ? "#e1e0d9" : colors[i],
                  display: "inline-block",
                }}
              />
              {name} ({counts[i].toLocaleString()})
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
