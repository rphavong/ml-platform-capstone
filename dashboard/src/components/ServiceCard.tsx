import { Fragment, useEffect, useState } from "react";
import {
  fetchHealth,
  fetchReady,
  runTestPrediction,
  type ServiceConfig,
  type FetchState,
  type HealthResponse,
  type ReadyResponse,
  type PredictResponse,
} from "../api";

const POLL_INTERVAL_MS = 10_000;

function StatusDot({ state }: { state: FetchState<unknown> }) {
  const color =
    state.status === "ok" ? "#22c55e" : state.status === "error" ? "#ef4444" : "#a3a3a3";
  const label = state.status === "ok" ? "healthy" : state.status === "error" ? "unreachable" : "checking...";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
        }}
      />
      <span style={{ fontSize: 13, color: "#525252" }}>{label}</span>
    </span>
  );
}

export function ServiceCard({ service }: { service: ServiceConfig }) {
  const [health, setHealth] = useState<FetchState<HealthResponse>>({ status: "loading" });
  const [ready, setReady] = useState<FetchState<ReadyResponse>>({ status: "loading" });
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const [prediction, setPrediction] = useState<FetchState<PredictResponse> | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      const [h, r] = await Promise.all([fetchHealth(service), fetchReady(service)]);
      if (cancelled) return;
      setHealth(h);
      setReady(r);
      setLastChecked(new Date());
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [service]);

  async function handleRunTest() {
    setRunning(true);
    setPrediction(null);
    try {
      // The known-good sample payload for this service, already shaped exactly as
      // /predict expects (top-level "cells" key) - see the dashboard README for how
      // to generate these 3 files from the same test_payload.json used throughout
      // this project's manual validation.
      const res = await fetch(`/test-payloads/${service.id}.json`);
      if (!res.ok) {
        setPrediction({
          status: "error",
          message: `Sample payload not found at public/test-payloads/${service.id}.json - see dashboard README.`,
        });
        return;
      }
      const payload = await res.json();
      const result = await runTestPrediction(service, payload);
      setPrediction(result);
    } finally {
      setRunning(false);
    }
  }

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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>{service.name}</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#737373" }}>{service.description}</p>
        </div>
        <StatusDot state={health} />
      </div>

      <div style={{ marginTop: 16, fontSize: 13 }}>
        <div style={{ color: "#525252", marginBottom: 4 }}>Readiness</div>
        {ready.status === "ok" && (
          <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "auto 1fr", gap: "2px 10px" }}>
            {Object.entries(ready.data).map(([key, value]) => (
              <Fragment key={key}>
                <dt style={{ color: "#a3a3a3" }}>{key}</dt>
                <dd style={{ margin: 0, fontFamily: "monospace" }}>{String(value)}</dd>
              </Fragment>
            ))}
          </dl>
        )}
        {ready.status === "error" && (
          <div style={{ color: "#ef4444", fontSize: 12 }}>{ready.message}</div>
        )}
        {ready.status === "loading" && <div style={{ color: "#a3a3a3" }}>checking...</div>}
      </div>

      <div style={{ marginTop: 16 }}>
        <button
          onClick={handleRunTest}
          disabled={running || health.status !== "ok"}
          style={{
            padding: "8px 14px",
            borderRadius: 8,
            border: "1px solid #d4d4d4",
            background: running ? "#f5f5f5" : "#171717",
            color: running ? "#a3a3a3" : "white",
            cursor: running || health.status !== "ok" ? "not-allowed" : "pointer",
            fontSize: 13,
          }}
        >
          {running ? "Running against SageMaker..." : "Run test prediction"}
        </button>

        {prediction?.status === "ok" && (
          <div style={{ marginTop: 12, fontSize: 12 }}>
            <div style={{ color: "#525252", marginBottom: 4 }}>
              {prediction.data.predicted_labels.length} predictions returned
            </div>
            <div
              style={{
                maxHeight: 140,
                overflowY: "auto",
                fontFamily: "monospace",
                background: "#fafafa",
                border: "1px solid #f0f0f0",
                borderRadius: 6,
                padding: 8,
              }}
            >
              {prediction.data.predicted_labels.map((label, i) => (
                <div key={i}>
                  {label} — {(prediction.data.confidence_scores[i] * 100).toFixed(1)}%
                </div>
              ))}
            </div>
          </div>
        )}
        {prediction?.status === "error" && (
          <div style={{ marginTop: 12, fontSize: 12, color: "#ef4444" }}>{prediction.message}</div>
        )}
      </div>

      {lastChecked && (
        <div style={{ marginTop: 14, fontSize: 11, color: "#a3a3a3" }}>
          Last checked {lastChecked.toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
