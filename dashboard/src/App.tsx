import { SERVICES } from "./api";
import { ServiceCard } from "./components/ServiceCard";

export default function App() {
  return (
    <div style={{ minHeight: "100vh", background: "#fafafa", padding: "32px 24px" }}>
      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        <header style={{ marginBottom: 28 }}>
          <h1 style={{ margin: 0, fontSize: 24 }}>ML Platform Ops Dashboard</h1>
          <p style={{ margin: "6px 0 0", color: "#737373", fontSize: 14 }}>
            Cervical cancer detection platform — 3 SageMaker-routed proxy services on
            Kubernetes. Status polls every 10s.
          </p>
        </header>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 20,
          }}
        >
          {SERVICES.map((service) => (
            <ServiceCard key={service.id} service={service} />
          ))}
        </div>
      </div>
    </div>
  );
}
