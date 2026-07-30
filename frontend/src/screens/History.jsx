import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";
import Reveal from "./Reveal.jsx";

function money(cents = 0, signed = false) {
  const value = new Intl.NumberFormat(undefined, {
    style: "currency", currency: "USD", maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(Math.abs(cents) / 100);
  return signed ? `${cents >= 0 ? "+" : "−"}${value}` : value;
}

function countdown(revealAt, now) {
  const total = Math.max(0, Math.ceil((new Date(revealAt).getTime() - now) / 1000));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

function Section({ title, count, children }) {
  return (
    <section className="history-section">
      <div className="history-section-title"><h2>{title}</h2><span>{count}</span></div>
      {children}
    </section>
  );
}

export default function History() {
  const { setUser } = useAuth();
  const [rows, setRows] = useState(() => api.peek("history:200") || []);
  const [loading, setLoading] = useState(() => !api.peek("history:200"));
  const [modal, setModal] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [resultFilter, setResultFilter] = useState("all");
  const [category, setCategory] = useState("all");
  const [now, setNow] = useState(Date.now());

  async function load() {
    setLoading(true);
    try {
      setRows(await api.history(200));
    } catch (event) {
      setError(event.message || "Could not load history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const categories = useMemo(
    () => [...new Set(rows.map((row) => row.category_name))].sort(),
    [rows],
  );
  const filtered = rows.filter((row) => {
    if (category !== "all" && row.category_name !== category) return false;
    if (resultFilter === "wins") return row.status === "revealed" && row.pnl_cents >= 0;
    if (resultFilter === "losses") return row.status === "revealed" && row.pnl_cents < 0;
    return true;
  });
  const active = filtered.filter((row) => row.status !== "revealed" && new Date(row.reveal_at).getTime() > now);
  const ready = filtered.filter((row) => row.status !== "revealed" && new Date(row.reveal_at).getTime() <= now);
  const revealed = filtered.filter((row) => row.status === "revealed");

  async function openReveal(row) {
    setBusy(row.id);
    setError("");
    try {
      const data = await api.reveal(row.id);
      setModal(data);
      setUser((current) => ({
        ...current,
        balance_cents: data.new_balance_cents,
        pulse_score: data.new_pulse_score,
      }));
      setRows((current) => current.map((item) => (
        item.id === row.id
          ? {
            ...item,
            status: "revealed",
            actual_distribution: data.actual_distribution,
            accuracy_score: data.accuracy_score,
            accuracy_percentile: data.accuracy_percentile,
            forecast_rank: data.forecast_rank,
            total_participants: data.total_participants,
            payout_cents: data.payout_cents,
            pnl_cents: data.pnl_cents,
            pulse_delta: data.pulse_delta,
            revealed_at: data.revealed_at,
          }
          : item
      )));
    } catch (event) {
      setError(event.message || "This participation is not ready yet.");
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="screen stack-screen history-screen">
      <header className="page-hero">
        <div><div className="label">History</div><h1>Your market reads</h1></div>
        <div className="hero-stat"><strong>{ready.length}</strong><span>ready</span></div>
      </header>

      <div className="history-filters">
        <div className="filter-pills">
          {["all", "wins", "losses"].map((filter) => (
            <button key={filter} className={resultFilter === filter ? "active" : ""} onClick={() => setResultFilter(filter)}>
              {filter[0].toUpperCase() + filter.slice(1)}
            </button>
          ))}
        </div>
        <label>Category
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="all">All categories</option>
            {categories.map((name) => <option key={name}>{name}</option>)}
          </select>
        </label>
      </div>

      {error && <div className="notice">{error}</div>}
      {loading && <div className="empty">Loading your reads…</div>}
      {!loading && rows.length === 0 && <div className="empty"><strong>No markets played yet.</strong><span>Your first locked poll will appear here.</span></div>}

      <Section title="Active" count={active.length}>
        {active.map((row) => (
          <article className="history-card active-card" key={row.id}>
            <div className="ticket-topline"><span>{row.category_name}</span><b>Locked</b></div>
            <h3>{row.question}</h3>
            <div className="history-timer-hero" aria-live="off">
              <span>Market resolves in</span>
              <strong>{countdown(row.reveal_at, now)}</strong>
              <small>Your result will unlock automatically</small>
            </div>
            <div className="vote-chip"><span>Your vote</span><strong>{row.vote.label}</strong></div>
            <div className="history-economy">
              <div><span>Stake</span><strong>{money(row.stake_cents)}</strong></div>
              <div><span>Volume</span><strong>{money(row.pool_volume_cents)}</strong></div>
              <div><span>Players</span><strong>{row.participant_count + 1}</strong></div>
            </div>
          </article>
        ))}
        {!active.length && <p className="section-empty">No active participations.</p>}
      </Section>

      <Section title="Ready to Reveal" count={ready.length}>
        {ready.map((row) => (
          <article className="history-card ready-card" key={row.id}>
            <div className="ticket-topline"><span>{row.category_name}</span><b>Ready</b></div>
            <h3>{row.question}</h3>
            <div className="history-economy">
              <div><span>Stake</span><strong>{money(row.stake_cents)}</strong></div>
              <div><span>Participants</span><strong>{row.participant_count + 1}</strong></div>
              <div><span>Result</span><strong>Hidden</strong></div>
            </div>
            <button className="primary-btn full" disabled={busy === row.id} onClick={() => openReveal(row)}>
              {busy === row.id ? "Revealing…" : "Reveal Result"}
            </button>
          </article>
        ))}
        {!ready.length && <p className="section-empty">Nothing waiting to reveal.</p>}
      </Section>

      <Section title="Revealed" count={revealed.length}>
        {revealed.map((row) => (
          <article className={`history-card revealed-card revealed-card--compact ${row.pnl_cents >= 0 ? "win" : "loss"}`} key={row.id}>
            <div className="ticket-topline"><span>{row.category_name}</span><b>{row.pnl_cents >= 0 ? "Win" : "Loss"}</b></div>
            <h3>{row.question}</h3>
            <div className="compact-reveal-summary">
              <div>
                <span>Result</span>
                <strong className={row.pnl_cents >= 0 ? "positive" : "negative"}>{money(row.pnl_cents, true)}</strong>
              </div>
              <div>
                <span>Accuracy</span>
                <strong>{row.accuracy_score?.toFixed(1)}</strong>
              </div>
              <div>
                <span>Pulse</span>
                <strong>{row.pulse_delta >= 0 ? "+" : ""}{row.pulse_delta}</strong>
              </div>
            </div>
            <div className="compact-reveal-footer">
              <span>Vote: <strong>{row.vote.label}</strong> · Rank #{row.forecast_rank}/{row.total_participants}</span>
              <button className="text-btn" disabled={busy === row.id} onClick={() => openReveal(row)}>
                {busy === row.id ? "Opening…" : "View analysis →"}
              </button>
            </div>
          </article>
        ))}
        {!revealed.length && <p className="section-empty">No revealed results in this filter.</p>}
      </Section>

      {modal && <Reveal data={modal} onClose={() => setModal(null)} onNext={() => setModal(null)} />}
    </main>
  );
}
