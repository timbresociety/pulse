import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

function initials(name = "P") {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export default function Leaderboard() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.leaderboard().then(setRows).catch(() => setError("Could not load the standings."));
  }, []);

  const you = useMemo(() => rows.find((row) => row.is_you), [rows]);
  const leaders = rows.slice(0, 3);

  return (
    <main className="screen stack-screen">
      <header className="page-hero">
        <div>
          <div className="label">Standings</div>
          <h1>Community reads</h1>
        </div>
        <div className="hero-stat">
          <strong>#{you?.rank || "-"}</strong>
          <span>your rank</span>
        </div>
      </header>

      <section className="podium-grid">
        {leaders.map((row) => (
          <article key={row.rank} className={`podium-card ${row.is_you ? "you" : ""}`}>
            <div className="podium-avatar" aria-hidden="true">{initials(row.display_name)}</div>
            <span>#{row.rank}</span>
            <strong>{row.display_name}</strong>
            <small>{row.pulse_score} score</small>
          </article>
        ))}
      </section>

      <section className="community-panel">
        <div className="community-mark" aria-hidden="true"><span /><span /></div>
        <div>
          <span>Live standings</span>
          <strong>Scores settle with markets</strong>
        </div>
        <p>Only accounts with a chosen username appear here.</p>
      </section>

      {error && <div className="notice">{error}</div>}
      <section className="leaderboard-list">
        <div className="section-heading">
          <span>Overall standings</span>
          <strong>{rows.length} members</strong>
        </div>
        {rows.map((row) => (
          <div key={row.rank} className={`leader-row ${row.is_you ? "you" : ""}`}>
            <span className="rank">#{row.rank}</span>
            <span className="leader-avatar" aria-hidden="true">{initials(row.display_name)}</span>
            <span className="caller">
              <strong>{row.display_name}</strong>
              {row.is_you && <small>You</small>}
            </span>
            <b>{row.pulse_score}</b>
          </div>
        ))}
      </section>
    </main>
  );
}
