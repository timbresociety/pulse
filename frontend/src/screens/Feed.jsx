import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";
import Reveal from "./Reveal.jsx";

export default function Feed() {
  const { user, setUser } = useAuth();
  const [markets, setMarkets] = useState([]);
  const [idx, setIdx] = useState(0);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState(null);
  const [pending, setPending] = useState(null); // {predictionId, revealAt, market}
  const [countdown, setCountdown] = useState(0);
  const [reveal, setReveal] = useState(null);
  const searchTimer = useRef(null);

  const market = markets[idx];

  async function loadFeed() {
    const data = await api.feed(20);
    setMarkets(data);
    setIdx(0);
  }
  useEffect(() => {
    loadFeed();
  }, []);

  // Debounced search.
  useEffect(() => {
    if (!market || query.trim().length < 1) {
      setCandidates([]);
      return;
    }
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(async () => {
      try {
        setCandidates(await api.search(query.trim(), market.id));
      } catch {
        setCandidates([]);
      }
    }, 220);
    return () => clearTimeout(searchTimer.current);
  }, [query, market]);

  // Countdown to reveal.
  useEffect(() => {
    if (!pending) return;
    const tick = () => {
      const secs = Math.max(0, Math.round((pending.revealAt - Date.now()) / 1000));
      setCountdown(secs);
      if (secs <= 0) doReveal();
    };
    tick();
    const t = setInterval(tick, 250);
    return () => clearInterval(t);
  }, [pending]);

  function resetCard() {
    setQuery("");
    setCandidates([]);
    setPicked(null);
  }

  function skip() {
    resetCard();
    advance();
  }

  function advance() {
    if (idx + 1 >= markets.length) loadFeed();
    else setIdx(idx + 1);
  }

  async function lock() {
    if (!picked) return;
    const { id, reveal_seconds } = await api.lock(market.id, picked.id, null);
    setPending({ predictionId: id, revealAt: Date.now() + reveal_seconds * 1000, market });
  }

  async function doReveal() {
    if (!pending) return;
    const data = await api.reveal(pending.predictionId);
    setReveal(data);
    setUser({ ...user, coins: data.new_coins, pulse_score: data.new_pulse });
    setPending(null);
  }

  function closeReveal() {
    setReveal(null);
    resetCard();
    advance();
  }

  return (
    <>
      <div className="topbar">
        <div className="brand">Pulse</div>
        <div className="stats">
          <span className="pill">🪙 {user.coins}</span>
          <span className="pill">⚡ {user.pulse_score}</span>
        </div>
      </div>

      <div className="screen">
        {!market && <div className="empty">No more markets right now. Check back soon!</div>}

        {market && (
          <div className="card">
            <span className="cat-pill" style={{ background: market.category?.color || "var(--accent)" }}>
              {market.category_name}
            </span>
            <div className="prompt">{market.prompt}</div>

            {!pending ? (
              <>
                <input
                  className="input"
                  placeholder="Type your answer…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoFocus
                />
                {picked && (
                  <div className="candidate selected" style={{ marginTop: 10 }}>
                    Your call: {picked.canonical_name}
                  </div>
                )}
                {!picked &&
                  candidates.map((c) => (
                    <div key={c.id} className="candidate" onClick={() => { setPicked(c); setCandidates([]); }}>
                      {c.canonical_name}
                    </div>
                  ))}

                <div className="row-actions">
                  <button className="btn btn-ghost" onClick={skip}>Skip</button>
                  <button className="btn btn-primary" disabled={!picked} onClick={lock}>
                    Lock call →
                  </button>
                </div>
              </>
            ) : (
              <div className="center" style={{ padding: "20px 0" }}>
                <div className="muted">Call locked: {picked?.canonical_name}</div>
                <div className="countdown" style={{ fontSize: 28, marginTop: 10 }}>
                  Reveal in {countdown}s
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {reveal && <Reveal data={reveal} onClose={closeReveal} />}
    </>
  );
}
