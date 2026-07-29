import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

function initials(name = "P") {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

export default function Leaderboard() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.leaderboard().then(setRows).catch((event) => setError(event.message || "Could not load the standings."));
  }, []);

  const you = useMemo(() => rows.find((row) => row.is_you), [rows]);

  return (
    <main className="screen stack-screen social-screen">
      <header className="page-hero">
        <div><div className="label">Social</div><h1>Pulse leaderboard</h1><p>Ranked by crowd-reading skill, never by bankroll.</p></div>
        <div className="hero-stat"><strong>#{you?.rank || "–"}</strong><span>your rank</span></div>
      </header>

      <section className="social-highlight">
        <div className="social-orbit" aria-hidden="true"><span>P</span><i /><i /><i /></div>
        <div><span>Primary signal</span><strong>Pulse Score</strong><p>Accuracy builds status. Stake size does not.</p></div>
      </section>

      {error && <div className="notice">{error}</div>}
      <section className="v0-leaderboard">
        <div className="leaderboard-head"><span>Rank · player</span><span>Pulse</span></div>
        {rows.map((row) => (
          <article key={`${row.rank}-${row.display_name}`} className={row.is_you ? "you" : ""}>
            <span className="rank">#{row.rank}</span>
            <span className="leader-avatar">{row.avatar_url ? <img src={row.avatar_url} alt="" /> : initials(row.display_name)}</span>
            <div className="leader-identity"><strong>{row.display_name}</strong>{row.is_you && <em>You</em>}<small>{row.markets_played} markets · {row.current_streak} streak</small></div>
            <div className="leader-performance"><strong>{row.pulse_score}</strong><small>{row.average_accuracy.toFixed(1)}% accuracy · {Math.round(row.win_rate * 100)}% wins</small></div>
          </article>
        ))}
      </section>
    </main>
  );
}
