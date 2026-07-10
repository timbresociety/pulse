import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

function initials(user) {
  return (user.display_name || user.email || "P").slice(0, 2).toUpperCase();
}

function formatPercent(value = 0) {
  return `${Math.round(value * 100)}%`;
}

export default function Profile() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    api.profileStats().then(setStats).catch(() => setStats(null));
    api.history(50).then(setHistory).catch(() => setHistory([]));
  }, []);

  const topCalls = useMemo(() => {
    const seen = new Set();
    return history
      .map((row) => row.picked_name)
      .filter(Boolean)
      .filter((name) => {
        if (seen.has(name)) return false;
        seen.add(name);
        return true;
      })
      .slice(0, 5);
  }, [history]);

  return (
    <main className="screen stack-screen">
      <header className="profile-header">
        <div className="profile-mark">
          <span>{initials(user)}</span>
        </div>
        <div>
          <div className="label">Profile</div>
          <h1>{user.display_name || "Psyblr reader"}</h1>
          <p>{user.email}</p>
        </div>
      </header>

      <section className="profile-score">
        <div>
          <span>Overall score</span>
          <strong>{user.pulse_score}</strong>
          <i style={{ width: `${Math.min(100, Math.max(8, user.pulse_score / 8))}%` }} aria-hidden="true" />
        </div>
        <div>
          <span>Coins</span>
          <strong>{user.coins}</strong>
          <i style={{ width: `${Math.min(100, Math.max(8, user.coins))}%` }} aria-hidden="true" />
        </div>
      </section>

      <section className="signal-grid">
        <div>
          <span>Win rate</span>
          <strong>{formatPercent(stats?.win_rate || 0)}</strong>
        </div>
        <div>
          <span>Current streak</span>
          <strong>{stats?.current_streak || 0}</strong>
        </div>
        <div>
          <span>Biggest win</span>
          <strong>{stats?.biggest_multiplier || 0}x</strong>
        </div>
        <div>
          <span>Contrarian wins</span>
          <strong>{stats?.contrarian_wins || 0}</strong>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-heading">
          <span>Selected channels</span>
          <strong>{stats?.best_category || "Build your map"}</strong>
        </div>
        <div className="channel-score-list">
          {(user.categories || []).map((category) => (
            <div key={category.id} className="channel-score">
              <span>{category.name}</span>
              <strong>Following</strong>
            </div>
          ))}
        </div>
        <button className="ghost-btn full" onClick={() => nav("/categories")}>
          Edit channels
        </button>
      </section>

      <section className="panel-section">
        <div className="section-heading">
          <span>Top calls</span>
          <strong>Canonical taste graph</strong>
        </div>
        {topCalls.length === 0 ? (
          <p>Your locked calls will become your public taste map.</p>
        ) : (
          <div className="top-call-list">
            {topCalls.map((call) => <span key={call}>{call}</span>)}
          </div>
        )}
      </section>

      <section className="panel-section">
        <div className="section-heading">
          <span>Pattern</span>
          <strong>{(stats?.contrarian_wins || 0) > 2 ? "Contrarian reader" : "Consensus reader"}</strong>
        </div>
        <p>
          Your score grows when your locked call matches the settled market result.
        </p>
      </section>

      <button className="ghost-btn full" onClick={logout}>Log out</button>
    </main>
  );
}
