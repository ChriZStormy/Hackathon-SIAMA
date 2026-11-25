import React, { useEffect, useState } from "react";

interface HealthStatus {
  status: string;
  service: string;
  version: string;
  region: string;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: HealthStatus) => setHealth(data))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 960, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>SIAMA-Impute — Demo Web (Paso 1)</h1>
      <p>
        Visor base preparado para integración con <strong>Leaflet</strong> (mapa de estaciones en Guanajuato) y{" "}
        <strong>Recharts</strong> (series diarias con distinción explícita entre dato observado, estimado y abstenido).
      </p>

      <section style={{ padding: "1rem", border: "1px solid #ddd", borderRadius: 8, marginTop: "1rem" }}>
        <h2>Estado de conexión con API ({API_BASE})</h2>
        {health && (
          <pre style={{ background: "#f5f5f5", padding: "0.75rem", borderRadius: 6 }}>
            {JSON.stringify(health, null, 2)}
          </pre>
        )}
        {error && <p style={{ color: "#b91c1c" }}>API no disponible aún: {error}</p>}
      </section>
    </main>
  );
}
