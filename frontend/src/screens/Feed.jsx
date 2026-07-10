import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

function formatNumber(value = 0) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

function formatDuration(totalSeconds = 0) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
  }
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

function formatObjectType(value = "object") {
  return value.replaceAll("_", " ");
}

function settlementLabel(type) {
  return type === "top_3_split" ? "Top 3 split" : "Top call wins";
}

const howItWorksCards = [
  {
    kicker: "Step 1",
    title: "Find the room",
    body: "Each market asks what the crowd will converge on before the timer closes.",
  },
  {
    kicker: "Step 2",
    title: "Lock your call",
    body: "Search for an answer, spend coins, and lock it before the room settles.",
  },
  {
    kicker: "Step 3",
    title: "Reveal the read",
    body: "When the reveal opens, winning calls earn coins and build your score.",
  },
];

export default function Feed() {
  const { user, setUser } = useAuth();
  const [markets, setMarkets] = useState([]);
  const [idx, setIdx] = useState(0);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searching, setSearching] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [drag, setDrag] = useState({ active: false, startX: 0, currentX: 0 });
  const [nudged, setNudged] = useState(false);
  const [burst, setBurst] = useState("");
  const [howOpen, setHowOpen] = useState(false);
  const [howStep, setHowStep] = useState(0);
  const searchTimer = useRef(null);
  const searchSerial = useRef(0);
  const receiptTimer = useRef(null);
  const burstTimer = useRef(null);

  const market = markets[idx];
  const dragOffset = drag.active ? drag.currentX - drag.startX : 0;
  const intent = dragOffset > 72 ? "lock" : dragOffset < -72 ? "skip" : "";
  const typedAnswer = query.trim();
  const canLock = Boolean(picked || typedAnswer.length > 1);
  const showResults = !picked && (candidates.length > 0 || searching || typedAnswer.length > 1);
  const activity = market ? Math.min(100, (market.total_call_count || 0) * 8) : 0;

  async function loadFeed() {
    setLoading(true);
    setError("");
    try {
      const data = await api.feed(30);
      setMarkets(data);
      setIdx(0);
    } catch {
      setError("Could not load active markets.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFeed();
    return () => {
      window.clearTimeout(receiptTimer.current);
      window.clearTimeout(burstTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!howOpen) return undefined;

    function handleHowKeys(event) {
      if (event.key === "Escape") {
        setHowOpen(false);
      }
      if (event.key === "ArrowLeft") {
        setHowStep((current) => (current + howItWorksCards.length - 1) % howItWorksCards.length);
      }
      if (event.key === "ArrowRight") {
        setHowStep((current) => (current + 1) % howItWorksCards.length);
      }
    }

    window.addEventListener("keydown", handleHowKeys);
    return () => window.removeEventListener("keydown", handleHowKeys);
  }, [howOpen]);

  useEffect(() => {
    const trimmedQuery = query.trim();

    if (!market || trimmedQuery.length < 2 || picked) {
      searchSerial.current += 1;
      setCandidates([]);
      setSearching(false);
      return;
    }

    window.clearTimeout(searchTimer.current);
    const requestId = searchSerial.current + 1;
    searchSerial.current = requestId;
    setCandidates([]);
    setSearching(true);
    searchTimer.current = window.setTimeout(async () => {
      try {
        const results = await api.search(trimmedQuery, market.id, 20);
        if (requestId === searchSerial.current) {
          setCandidates(results);
        }
      } catch {
        if (requestId === searchSerial.current) {
          setCandidates([]);
        }
      } finally {
        if (requestId === searchSerial.current) {
          setSearching(false);
        }
      }
    }, 160);

    return () => window.clearTimeout(searchTimer.current);
  }, [query, market, picked]);

  function resetComposer() {
    setQuery("");
    setPicked(null);
    setCandidates([]);
    setSearching(false);
    setDrag({ active: false, startX: 0, currentX: 0 });
  }

  async function advance() {
    resetComposer();
    if (idx + 1 >= markets.length) await loadFeed();
    else setIdx((current) => current + 1);
  }

  async function skip() {
    if (!market) return;
    flashBurst("skip");
    await advance();
  }

  function pulseNudge() {
    setNudged(true);
    window.setTimeout(() => setNudged(false), 460);
  }

  function flashBurst(type) {
    setBurst(type);
    window.clearTimeout(burstTimer.current);
    burstTimer.current = window.setTimeout(() => setBurst(""), 760);
  }

  async function lock() {
    if (!market) return;
    if (!canLock) {
      pulseNudge();
      return;
    }

    setError("");
    try {
      const callText = picked ? picked.canonical_name : typedAnswer;
      const ticket = await api.lock(
        market.id,
        picked ? picked.id : null,
        picked ? null : typedAnswer,
      );
      setUser({
        ...user,
        coins: ticket.new_coins,
        ranked_calls_remaining: ticket.ranked_calls_remaining,
      });
      setReceipt({
        call: ticket.canonical_name || callText,
        market: market.prompt,
        reveal: ticket.reveal_seconds,
        ranked: ticket.is_ranked,
        pool: ticket.pool_size,
      });
      flashBurst("lock");
      window.clearTimeout(receiptTimer.current);
      receiptTimer.current = window.setTimeout(() => setReceipt(null), 2400);
      await advance();
    } catch (event) {
      setError(event?.status === 402 ? "You need more coins to enter this market." : "No relevant match for this market yet.");
    }
  }

  function startDrag(event) {
    if (event.button > 0) return;
    if (event.target.closest("input, button, .result-card, .call-chip")) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setDrag({ active: true, startX: event.clientX, currentX: event.clientX });
  }

  function moveDrag(event) {
    if (!drag.active) return;
    setDrag((current) => ({ ...current, currentX: event.clientX }));
  }

  async function endDrag(event) {
    if (!drag.active) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    const offset = drag.currentX - drag.startX;
    setDrag({ active: false, startX: 0, currentX: 0 });
    if (offset < -118) await skip();
    if (offset > 118) await lock();
  }

  return (
    <main className="screen feed-screen">
      {burst && (
        <div className={`screen-burst ${burst}`} aria-hidden="true">
          <span />
          <span />
          <span />
          <b>{burst === "lock" ? "Locked" : "Skipped"}</b>
        </div>
      )}

      <header className="feed-header">
        <div>
          <div className="psyblr-wordmark compact-wordmark" aria-label="Psyblr">
            <span className="chrome-text">Psy</span><span className="accent-word">blr</span>
          </div>
          <div className="label">Culture markets</div>
          <h1>Read the room.</h1>
        </div>
        <div className="feed-actions">
          <button
            className="how-trigger"
            type="button"
            aria-label="How Psyblr works"
            onClick={() => {
              setHowStep(0);
              setHowOpen(true);
            }}
          >
            how it works?
          </button>
          <div className="balance-stack">
            <span className="coin-stack-icon" aria-hidden="true" />
            <span className="balance-amount">{formatNumber(user.coins)}</span>
            <span className="balance-unit">coins</span>
            <small>{user.ranked_calls_remaining ?? 10} ranked calls left</small>
          </div>
        </div>
      </header>

      {receipt && (
        <div className="ticket-receipt">
          <div>
            <span>Call ticket locked</span>
            <strong>{receipt.call}</strong>
          </div>
          <small>{receipt.ranked ? "Ranked call" : "Casual pool"} reveals in {formatDuration(receipt.reveal)}</small>
        </div>
      )}

      {error && <div className="notice">{error}</div>}
      {loading && <div className="empty">Loading active markets...</div>}

      {!loading && !market && (
        <div className="empty">
          <strong>No active markets in your channels.</strong>
          <button className="primary-btn" onClick={loadFeed}>Refresh feed</button>
        </div>
      )}

      {market && (
        <div className="market-deck">
          <article
            className={`pulse-card live-card ${nudged ? "shake" : ""}`}
            style={{ transform: `translateX(${dragOffset}px) rotate(${dragOffset / 24}deg)` }}
            onPointerDown={startDrag}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          >
            <div className={`intent-badge intent-lock ${intent === "lock" ? "visible" : ""}`}>Lock</div>
            <div className={`intent-badge intent-skip ${intent === "skip" ? "visible" : ""}`}>Skip</div>

            <div className="market-topline">
              <span>{market.category_name} market</span>
              <b>{formatDuration(market.closes_in_seconds)}</b>
            </div>

            <div className="market-art" aria-hidden="true">
              <div className="chaos-cube">
                <span />
                <span />
                <span />
              </div>
              <div className="hype-stack">
                <span>Live calls</span>
                <div className="hype-rail">
                  <span style={{ width: `${activity}%` }} />
                </div>
              </div>
            </div>

            <h2>{market.prompt}</h2>

            <div className="pool-panel">
              <div>
                <span>Pool</span>
                <strong>{formatNumber(market.pool_size)}</strong>
              </div>
              <div>
                <span>Locked calls</span>
                <strong>{formatNumber(market.total_call_count)}</strong>
              </div>
              <div>
                <span>Net pool</span>
                <strong>{formatNumber(market.potential_payout_max)}</strong>
              </div>
            </div>

            <div className="call-composer">
              <div className="composer-label">
                <span>Your call</span>
                <b>{settlementLabel(market.settlement_type)}</b>
              </div>

              <input
                className="call-input"
                placeholder={`Search any ${formatObjectType(market.object_type)}`}
                value={query}
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={showResults}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setPicked(null);
                }}
              />

              {picked && (
                <button className="call-chip" onClick={() => setPicked(null)}>
                  <span>{picked.canonical_name}</span>
                  <small>Change</small>
                </button>
              )}

              {showResults && (
                <div className="result-list" role="listbox">
                  {candidates.map((candidate) => (
                    <button
                      key={candidate.id}
                      className="result-card"
                      role="option"
                      onClick={() => {
                        setPicked(candidate);
                        setQuery(candidate.canonical_name);
                        setCandidates([]);
                      }}
                    >
                      <span>{candidate.canonical_name}</span>
                      <small>{formatObjectType(candidate.object_type)}</small>
                    </button>
                  ))}
                  {searching && candidates.length === 0 && (
                    <div className="result-card result-status">
                      <span>Finding matches...</span>
                      <small>{formatObjectType(market.object_type)}</small>
                    </div>
                  )}
                </div>
              )}

              {!showResults && !picked && !searching && query.trim().length > 1 && candidates.length === 0 && (
                <div className="resolver-empty">
                  <strong>No relevant match yet.</strong>
                  <span>{formatObjectType(market.object_type)}</span>
                </div>
              )}
            </div>

            <footer className="swipe-actions">
              <button className="ghost-btn" onClick={skip}>Pass</button>
              <button className="primary-btn" disabled={!canLock} onClick={lock}>
                {picked ? "Lock call" : "Find & lock"}
              </button>
            </footer>
          </article>
        </div>
      )}

      {howOpen && (
        <div
          className="how-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="how-title"
          onClick={() => setHowOpen(false)}
        >
          <div className="how-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="how-topline">
              <div>
                <span>How it works</span>
                <strong id="how-title">Read the room</strong>
              </div>
              <button className="how-close" type="button" aria-label="Close how it works" onClick={() => setHowOpen(false)}>
                &times;
              </button>
            </div>

            <div className="how-carousel" aria-live="polite">
              <div className="how-track" style={{ transform: `translateX(-${howStep * 100}%)` }}>
                {howItWorksCards.map((card) => (
                  <article className="how-card" key={card.title}>
                    <span>{card.kicker}</span>
                    <h2>{card.title}</h2>
                    <p>{card.body}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="how-controls">
              <button
                type="button"
                aria-label="Previous how it works card"
                onClick={() => setHowStep((current) => (current + howItWorksCards.length - 1) % howItWorksCards.length)}
              >
                &lsaquo;
              </button>
              <div className="how-dots" aria-hidden="true">
                {howItWorksCards.map((card, cardIdx) => (
                  <span key={card.title} className={cardIdx === howStep ? "active" : ""} />
                ))}
              </div>
              <button
                type="button"
                aria-label="Next how it works card"
                onClick={() => setHowStep((current) => (current + 1) % howItWorksCards.length)}
              >
                &rsaquo;
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
