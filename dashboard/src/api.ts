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
