import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api";

function initials(name = "P") {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

export default function Leaderboard() {
  const [leaderboard, setLeaderboard] = useState({ rows: [], total_players: 0, user_rank: 0 });
  const [error, setError] = useState("");

  useEffect(() => {
    api.leaderboard()
      .then((data) => setLeaderboard(data))
      .catch((event) => setError(event.message || "Could not load the standings."));
  }, []);

  const rows = leaderboard.rows || [];
  const you = useMemo(() => rows.find((row) => row.is_you), [rows]);
  const userRank = leaderboard.user_rank || you?.rank;
  const population = leaderboard.total_players
    ? leaderboard.total_players.toLocaleString()
    : "5,000+";

  return (
    <main className="screen stack-screen social-screen">
      <header className="page-hero">
        <div><div className="label">Social</div><h1>Pulse leaderboard</h1><p>Ranked by crowd-reading skill, never by bankroll.</p></div>
        <div className="hero-stat"><strong>#{userRank || "–"}</strong><span>of {population} players</span></div>
      </header>

      <section className="social-highlight">
        <div className="social-orbit" aria-hidden="true"><span>P</span><i /><i /><i /></div>
        <div><span>{population} players ranked</span><strong>Pulse Score</strong><p>Every market can move you up the ladder. Stake size does not.</p></div>
      </section>

      {error && <div className="notice">{error}</div>}
      <section className="v0-leaderboard">
        <div className="leaderboard-head"><span>Rank · {population} players</span><span>Pulse</span></div>
        {rows.map((row, index) => {
          const previousRank = rows[index - 1]?.rank;
          const skippedPlayers = previousRank ? row.rank - previousRank - 1 : 0;
          return (
            <Fragment key={`${row.rank}-${row.display_name}`}>
              {skippedPlayers > 0 && (
                <div className="leaderboard-gap" aria-label={`${skippedPlayers.toLocaleString()} players between these ranks`}>
                  <i /><span>{skippedPlayers.toLocaleString()} players</span><i />
                </div>
              )}
              <article className={row.is_you ? "you" : ""}>
                <span className="rank">#{row.rank}</span>
                <span className="leader-avatar">{row.avatar_url ? <img src={row.avatar_url} alt="" /> : initials(row.display_name)}</span>
                <div className="leader-identity"><strong>{row.display_name}</strong>{row.is_you && <em>You</em>}<small>{row.markets_played} markets · {row.current_streak} streak</small></div>
                <div className="leader-performance"><strong>{row.pulse_score}</strong><small>{row.average_accuracy.toFixed(1)}% accuracy · {Math.round(row.win_rate * 100)}% wins</small></div>
              </article>
            </Fragment>
          );
        })}
      </section>
    </main>
  );
}
