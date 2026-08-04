// dashboard/src/App.tsx
import { useEffect, useState } from "react";
import { fetchBins, type Bin } from "./api";
import BinCard from "./components/BinCard";
import PickupQueue from "./components/PickupQueue";
import DecisionLog from "./components/DecisionLog";
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
        <h1>Smart Bin Dashboard</h1>
      </header>
      <main>
        <section className="section-plain">
          <h2>Pickup Queue</h2>
          <PickupQueue bins={bins} />
        </section>
        <div className="bin-grid">
          {bins.map((bin) => (
            <BinCard key={bin.bin_id} bin={bin} />
          ))}
        </div>

        <section className="queue-section">
          <h2>Decision Log</h2>
          <DecisionLog />
        </section>
      </main>
    </div>
  );
}

export default App;