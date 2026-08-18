import { useEffect, useState } from "react";
import { fetchBins, type Bin } from "./api";
import BinCard from "./components/BinCard";
import StatusSummary from "./components/StatusSummary";
import DecisionLog from "./components/DecisionLog";
import Logo from "./components/Logo";
import "./App.css";

function App() {
  const [bins, setBins] = useState<Bin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBins()
      .then(setBins)
      .catch(() => setError("Could not load bin data"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading...</p>;
  if (error) return <p className="error">{error}</p>;

  return (
    <div className="app">
      <header className="app-header">
        <Logo />
      </header>
      <main>
        <section className="section-plain">
          <h2>Status</h2>
          <StatusSummary bins={bins} />
        </section>

        {bins.length === 0 ? (
          <div className="empty-state">
            <h3>No bins reporting yet</h3>
            <p>
              A bin shows up here automatically the moment its device sends
              its first reading — bin ID comes from the device's own config,
              not from the dashboard. Nothing to set up here; just power on
              the device.
            </p>
          </div>
        ) : (
          <div className="bin-grid">
            {bins.map((bin) => (
              <BinCard key={bin.bin_id} bin={bin} />
            ))}
          </div>
        )}

        <section className="queue-section">
          <h2>Decision Log</h2>
          <DecisionLog />
        </section>
      </main>
    </div>
  );
}

export default App;