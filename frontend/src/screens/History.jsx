import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Reveal from "./Reveal.jsx";

function formatNumber(value = 0) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

function formatDuration(seconds = 0) {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

function timeLeft(row) {
  const lockedAt = new Date(row.locked_at).getTime();
  const revealAt = lockedAt + row.reveal_seconds * 1000;
  return Math.max(0, Math.round((revealAt - Date.now()) / 1000));
}

function resultCopy(row) {
  if (!row.outcome) return "Hidden until epoch close";
  if (row.outcome === "win") return "You read the room";
  return "Missed the top call";
}

function statusCopy(row, canReveal) {
  if (row.outcome === "win") return "Won";
  if (row.outcome === "lose") return "Settled";
  return canReveal ? "Ready" : "Hidden";
}

function payoutCopy(row) {
  if (!row.outcome) return "--";
  return row.coins_won > 0 ? `+${formatNumber(row.coins_won)}` : "0";
}

export default function History() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reveal, setReveal] = useState(null);
  const [revealingId, setRevealingId] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    try {
      setRows(await api.history(100));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const summary = useMemo(() => {
    const settled = rows.filter((row) => row.outcome);
    const wins = settled.filter((row) => row.outcome === "win");
    return {
      entered: rows.length,
      pending: rows.length - settled.length,
      wins: wins.length,
      coins: settled.reduce((sum, row) => sum + (row.coins_won || 0), 0),
    };
  }, [rows]);

  async function revealReady(row) {
    setError("");
    setRevealingId(row.id);
    try {
      const data = await api.reveal(row.id);
      setReveal(data);
      await load();
    } catch {
      setError("Could not open this reveal yet.");
    } finally {
      setRevealingId(null);
    }
  }

  return (
    <main className="screen stack-screen">
      <header className="page-hero">
        <div>
          <div className="label">Reveal queue</div>
          <h1>Your calls</h1>
        </div>
        <div className="hero-stat">
          <strong>{summary.pending}</strong>
          <span>hidden</span>
        </div>
      </header>

      <section className="metric-band">
        <div>
          <span>Tickets</span>
          <strong>{summary.entered}</strong>
        </div>
        <div>
          <span>Wins</span>
          <strong>{summary.wins}</strong>
        </div>
        <div>
          <span>Paid out</span>
          <strong>{formatNumber(summary.coins)}</strong>
        </div>
      </section>

      {error && <div className="notice">{error}</div>}
      {loading && <div className="empty">Loading call tickets...</div>}
      {!loading && rows.length === 0 && (
        <div className="empty">
          <strong>No calls yet.</strong>
          <span>Lock a market from the feed and it will appear here.</span>
        </div>
      )}

      <section className="ticket-list">
        {rows.map((row) => {
          const pending = !row.outcome;
          const resolved = !pending;
          const left = timeLeft(row);
          const canReveal = pending && left <= 0;
          const canOpen = canReveal || resolved;
          const isBusy = revealingId === row.id;
          return (
            <article
              key={row.id}
              className={`ticket-card ${row.outcome || "pending"} ${resolved ? "resolved" : ""} ${canReveal ? "ready" : ""}`}
            >
              <div className="ticket-topline">
                <span>{row.category_name}</span>
                <b>{pending && !canReveal ? formatDuration(left) : statusCopy(row, canReveal)}</b>
              </div>
              <div className="ticket-object" aria-hidden="true">
                <span />
                <span />
              </div>
              <h2>{row.prompt}</h2>
              <div className="ticket-call">
                <span>Your call</span>
                <strong>{row.picked_name || "Canonical match pending"}</strong>
              </div>
              <div className={`ticket-payout ${resolved ? "settled" : canReveal ? "ready" : "pending"}`}>
                <span>{resolved ? "Payout" : canReveal ? "Reveal available" : "Payout locked"}</span>
                <strong>{resolved ? payoutCopy(row) : canReveal ? "Open" : "Hidden"}</strong>
                <small>
                  {resolved
                    ? row.coins_won > 0
                      ? `${row.payout_multiplier}x on a ${row.entry_cost} entry`
                      : "No coin payout"
                    : canReveal
                      ? "Settlement is ready"
                      : "Shows after reveal"}
                </small>
              </div>
              <div className="ticket-economy">
                <div>
                  <small>Entry</small>
                  <strong>{row.entry_cost}</strong>
                </div>
                <div>
                  <small>Pool</small>
                  <strong>{formatNumber(row.pool_size)}</strong>
                </div>
                <div>
                  <small>Result</small>
                  <strong>{resultCopy(row)}</strong>
                </div>
              </div>
              {canOpen && (
                <button className="primary-btn full" disabled={isBusy} onClick={() => revealReady(row)}>
                  {isBusy ? "Opening..." : resolved ? "Open reveal" : "Reveal now"}
                </button>
              )}
            </article>
          );
        })}
      </section>

      {reveal && <Reveal data={reveal} onClose={() => setReveal(null)} />}
    </main>
  );
}
