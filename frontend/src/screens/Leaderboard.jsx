import { useEffect, useState } from "react";
import { api } from "../api";

export default function Leaderboard() {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    api.leaderboard().then(setRows);
  }, []);

  return (
    <div className="screen">
      <div className="brand" style={{ marginBottom: 4 }}>Leaderboard</div>
      <div className="muted" style={{ marginBottom: 16 }}>Ranked by coins</div>
      <div className="card" style={{ padding: 6 }}>
        {rows.map((r) => (
          <div key={r.rank} className={`lb-row ${r.is_you ? "you" : ""}`}>
            <span className="lb-rank">{r.rank}</span>
            <span className="lb-name">
              {r.display_name} {r.is_you && <span className="muted">(you)</span>}
            </span>
            <span className="lb-score">🪙 {r.coins}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
