import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

function initials(user) {
  return (user.display_name || user.email || "P").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function money(cents = 0, signed = false) {
  const formatted = new Intl.NumberFormat(undefined, {
    style: "currency", currency: "USD", maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(Math.abs(cents) / 100);
  return signed ? `${cents >= 0 ? "+" : "−"}${formatted}` : formatted;
}

export default function Profile() {
  const { user, dataVersion, logout } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(() => api.peek("profileStats"));
  const [loading, setLoading] = useState(() => !api.peek("profileStats"));

  useEffect(() => {
    api.profileStats()
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [dataVersion]);

  return (
    <main className="screen stack-screen profile-screen" aria-busy={loading}>
      <header className="v0-profile-header">
        <div className="profile-avatar">
          {user.avatar_url ? <img src={user.avatar_url} alt="" /> : initials(user)}
        </div>
        <div><div className="label">Profile</div><h1>{user.display_name || "Pulse reader"}</h1><p>{user.email}</p></div>
      </header>

      <section className="profile-primary-stats">
        <div><span>Pulse Score</span><strong>{user.pulse_score}</strong><small>Crowd-reading rank</small></div>
        <div><span>Fake balance</span><strong>{money(user.balance_cents)}</strong><small>Test credits only</small></div>
      </section>

      <section className="profile-stat-grid">
        <div><span>Markets played</span><strong>{stats ? stats.markets_played : "—"}</strong></div>
        <div><span>Win rate</span><strong>{stats ? `${Math.round(stats.win_rate * 100)}%` : "—"}</strong></div>
        <div><span>Avg accuracy</span><strong>{stats ? `${stats.average_accuracy.toFixed(1)}%` : "—"}</strong></div>
        <div><span>Total fake PnL</span><strong className={stats ? (stats.total_pnl_cents >= 0 ? "positive" : "negative") : ""}>{stats ? money(stats.total_pnl_cents, true) : "—"}</strong></div>
        <div><span>Total volume</span><strong>{stats ? money(stats.total_volume_cents) : "—"}</strong></div>
        <div><span>Biggest win</span><strong>{stats ? money(stats.biggest_win_cents) : "—"}</strong></div>
        <div><span>Current streak</span><strong>{stats ? stats.current_streak : "—"}</strong></div>
        <div><span>Longest streak</span><strong>{stats ? stats.longest_streak : "—"}</strong></div>
      </section>

      <section className="activity-panel">
        <div className="section-heading"><span>Market activity</span><strong>Past 12 weeks</strong></div>
        <div className="activity-calendar" aria-label="Markets played by day">
          {stats?.activity?.map((day) => (
            <i
              key={day.date}
              className={`level-${Math.min(4, day.markets_played)}`}
              title={`${day.date}: ${day.markets_played} markets`}
              aria-label={`${day.date}: ${day.markets_played} markets`}
            />
          ))}
        </div>
        {!stats && <p className="section-empty">Loading activity…</p>}
        <div className="activity-legend"><span>Less</span>{[0, 1, 2, 3, 4].map((level) => <i key={level} className={`level-${level}`} />)}<span>More</span></div>
      </section>

      <section className="panel-section profile-channels">
        <div className="section-heading"><span>Active channels</span><strong>{stats ? (stats.best_category || "No best read yet") : "Loading…"}</strong></div>
        <div className="top-call-list">{user.categories.map((category) => <span key={category.id}>{category.name}</span>)}</div>
        <button className="ghost-btn full" onClick={() => navigate("/categories")}>Edit categories</button>
      </section>

      <button className="ghost-btn full" onClick={logout}>Log out</button>
    </main>
  );
}
