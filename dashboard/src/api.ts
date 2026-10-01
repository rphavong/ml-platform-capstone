// Module 8: talks directly to the 3 K8s-hosted proxy services (no backend in between,
// per the "direct calls" decision) - so these base URLs assume each service is
// reachable at localhost via `kubectl port-forward`, same ports used throughout this
// project's manual testing (8001/8002/8003).

export interface ServiceConfig {
  id: string;
  name: string;
  description: string;
  baseUrl: string;
}

export const SERVICES: ServiceConfig[] = [
  {
    id: "endpoint1-flex",
    name: "Endpoint 1 - Flex",
    description: "Cell type & malignancy classifier (10x Flex single-cell)",
    baseUrl: "http://localhost:8001",
  },
  {
    id: "endpoint2-xenium",
    name: "Endpoint 2 - Xenium",
    description: "Cell type & malignancy classifier (10x Xenium spatial)",
    baseUrl: "http://localhost:8002",
  },
  {
    id: "endpoint3-spatial",
    name: "Endpoint 3 - Spatial",
    description: "Spatial neighborhood classifier (Xenium coordinates)",
    baseUrl: "http://localhost:8003",
  },
];

export type FetchState<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "error"; message: string };

// A short timeout matters here specifically because this polls every few seconds - a
// hung request (service down, port-forward dropped) shouldn't pile up and make the
// whole dashboard feel frozen. AbortController is the standard way to bound a fetch()
// call that has no built-in timeout of its own.
async function fetchJson<T>(url: string, timeoutMs = 4000): Promise<FetchState<T>> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      // A non-2xx response (e.g. /ready returning 503 while the schema is still
      // loading) is still useful information - surface the real body, not just
      // "something went wrong".
      const body = await res.text();
      return { status: "error", message: `HTTP ${res.status}: ${body}` };
    }
    const data = (await res.json()) as T;
    return { status: "ok", data };
  } catch (err) {
    const message =
      err instanceof DOMException && err.name === "AbortError"
        ? `Timed out after ${timeoutMs}ms - is \`kubectl port-forward\` still running for this service?`
        : err instanceof Error
          ? err.message
          : String(err);
    return { status: "error", message };
  } finally {
    clearTimeout(timeout);
  }
}

export interface HealthResponse {
  status: string;
}

// /ready's shape differs slightly per service (endpoint1/2 report n_features_expected,
// endpoint3 reports gene + spatial feature counts and min_cells_per_request) - rather
// than model that with 3 overlapping interfaces, this stays a loose record and the UI
// just renders whatever keys come back.
export type ReadyResponse = Record<string, string | number>;

export function fetchHealth(service: ServiceConfig) {
  return fetchJson<HealthResponse>(`${service.baseUrl}/health`);
}

export function fetchReady(service: ServiceConfig) {
  return fetchJson<ReadyResponse>(`${service.baseUrl}/ready`);
}

export interface PredictResponse {
  predicted_labels: string[];
  confidence_scores: number[];
}

// Runs the bundled test_payload.json (already shipped with each service for exactly
// this purpose) against the live /predict endpoint - a one-click smoke test rather
// than a real data-entry form, per the earlier scoping discussion.
export async function runTestPrediction(
  service: ServiceConfig,
  payload: unknown,
): Promise<FetchState<PredictResponse>> {
  const controller = new AbortController();
  const timeoutMs = 25000; // real SageMaker round trip, not a health check - needs more headroom
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${service.baseUrl}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const body = await res.json();
    if (!res.ok) {
      const detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
      return { status: "error", message: `HTTP ${res.status}: ${detail}` };
    }
    return { status: "ok", data: body as PredictResponse };
  } catch (err) {
    const message =
      err instanceof DOMException && err.name === "AbortError"
        ? `Timed out after ${timeoutMs}ms waiting for SageMaker`
        : err instanceof Error
          ? err.message
          : String(err);
    return { status: "error", message };
  } finally {
    clearTimeout(timeout);
  }
}

// Module eval evidence: a static, pre-computed summary of held-out model quality
// (see ec2-pipeline-pulled/export_model_eval.py), shipped at build time as
// public/model-eval.json - not a live endpoint, since these are offline
// train/test-split evaluations, not something to recompute per page load.

export interface ClassMetrics {
  precision: number;
  recall: number;
  "f1-score": number;
  support: number;
}

export interface EndpointEval {
  description: string;
  data_source: string;
  total_cells: number;
  held_out_cells: number;
  accuracy: number;
  macro_avg: ClassMetrics;
  weighted_avg: ClassMetrics;
  per_class: Record<string, ClassMetrics>;
  caveat?: string;
}

export interface SpatialComparison {
  description: string;
  test_cells: number;
  sanity_check_agreement: number;
  sanity_check_note: string;
  overall_agreement: number;
  overall_changed_count: number;
  hard_case_threshold_confidence: number;
  hard_case_count: number;
  hard_case_agreement: number;
  hard_case_changed_count: number;
  hard_case_changed_pct: number;
  gene_only_hard_case_distribution: Record<string, number>;
  spatial_hard_case_distribution: Record<string, number>;
  confidence_histogram: { bin_edges: number[]; counts: number[] };
}

export interface ModelEval {
  generated_at: string;
  note: string;
  endpoint1_endpoint2: EndpointEval;
  endpoint3: EndpointEval;
  spatial_vs_gene_only: SpatialComparison;
}

export async function fetchModelEval(): Promise<FetchState<ModelEval>> {
  return fetchJson<ModelEval>("/model-eval.json");
}

// Cell-level scatter datasets (Flex UMAP, Xenium physical spatial map) - see
// ec2-pipeline-pulled/export_embeddings.py. Compact encoding: class name
// lists + integer codes per point, two label fields each (true/predicted or
// gene-only/spatial) so the UI can toggle which one colors the plot.

export interface ScatterPoint {
  x: number;
  y: number;
  ct: number;
  ctPred: number;
  m: number;
  mPred: number;
}

export interface ScatterDataset {
  note: string;
  n_cells: number;
  cell_type_classes: string[];
  malignancy_classes: string[];
  points: ScatterPoint[];
}

export function fetchFlexUmap() {
  return fetchJson<ScatterDataset>("/flex-umap.json");
}

export function fetchXeniumSpatial() {
  return fetchJson<ScatterDataset>("/xenium-spatial.json");
}
