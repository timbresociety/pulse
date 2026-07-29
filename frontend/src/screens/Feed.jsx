import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

function money(cents = 0) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(cents / 100);
}

function compactMoney(cents = 0) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(cents / 100);
}

function number(value = 0) {
  return new Intl.NumberFormat("en-US").format(value);
}

function duration(seconds = 0) {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function equalAllocations(options) {
  if (!options.length) return {};
  const base = Math.floor(10000 / options.length);
  let remaining = 10000 - base * options.length;
  return Object.fromEntries(options.map((option) => {
    const value = base + (remaining > 0 ? 1 : 0);
    remaining -= remaining > 0 ? 1 : 0;
    return [option.id, value];
  }));
}

function splitAllocations(options, leaderId, leaderPercent) {
  if (!options.length) return {};
  if (!leaderId) return equalAllocations(options);

  const leaderBps = Math.round(leaderPercent * 100);
  const others = options.filter((option) => option.id !== leaderId);
  const base = Math.floor((10000 - leaderBps) / Math.max(1, others.length));
  let remainder = 10000 - leaderBps - (base * others.length);

  return Object.fromEntries(options.map((option) => {
    if (option.id === leaderId) return [option.id, leaderBps];
    const value = base + (remainder > 0 ? 1 : 0);
    remainder -= remainder > 0 ? 1 : 0;
    return [option.id, value];
  }));
}

function categoryColor(slug = "") {
  const colors = {
    internet: "#64f3c5",
    music: "#ff8dcb",
    "film-tv": "#8fb2ff",
    fashion: "#e8a8ff",
    gaming: "#a6ff7c",
    sports: "#ffd36a",
    "food-drink": "#ff9d75",
    "anime-manga": "#9e9bff",
    "brands-products": "#65d9ff",
    "books-writing": "#d8b98c",
    people: "#ff9696",
    places: "#76e3c4",
  };
  return colors[slug] || "#64f3c5";
}

function feeFor(stakeCents) {
  return Math.floor((stakeCents * 200 + 5000) / 10000);
}

function splitTone(share, minimum) {
  if (share <= minimum + 4) return "Neck and neck";
  if (share <= 42) return "Slight edge";
  if (share <= 58) return "Clear lead";
  return "Runaway";
}

export default function Feed() {
  const { user, setUser } = useAuth();
  const [markets, setMarkets] = useState([]);
  const [index, setIndex] = useState(0);
  const [view, setView] = useState("deck");
  const [activeStep, setActiveStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [voteId, setVoteId] = useState("");
  const [forecast, setForecast] = useState({});
  const [crowdLeaderId, setCrowdLeaderId] = useState("");
  const [leaderShare, setLeaderShare] = useState(38);
  const [splitConfirmed, setSplitConfirmed] = useState(false);
  const [stake, setStake] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [receipt, setReceipt] = useState(null);

  const market = markets[index];
  const nextMarket = markets[index + 1];
  const minimumLeaderShare = market ? Math.ceil(100 / market.options.length) : 25;
  const forecastTotal = useMemo(
    () => Object.values(forecast).reduce((sum, value) => sum + (Number(value) || 0), 0),
    [forecast],
  );
  const stakeCents = Math.max(0, Math.round((Number(stake) || 0) * 100));
  const validForecast = Boolean(
    market
      && crowdLeaderId
      && Object.keys(forecast).length === market.options.length
      && forecastTotal === 10000,
  );
  const canSubmit = Boolean(
    voteId && validForecast && splitConfirmed && stakeCents > 0 && stakeCents <= user.balance_cents,
  );
  const payoutCeiling = market && stakeCents
    ? Math.max(0, Math.round((market.pool_volume_cents + stakeCents) * 0.98))
    : 0;
  const activeColor = categoryColor(market?.category?.slug);

  async function loadFeed() {
    setLoading(true);
    setError("");
    try {
      const data = await api.feed(50);
      setMarkets(data);
      setIndex(0);
      setView("deck");
      setReceipt(null);
    } catch (event) {
      setError(event.message || "Could not load Pulse markets.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFeed();
  }, []);

  function resetParticipation(next = market) {
    setVoteId("");
    setForecast(next ? equalAllocations(next.options) : {});
    setCrowdLeaderId("");
    setLeaderShare(next ? Math.max(32, Math.ceil(100 / next.options.length) + 10) : 38);
    setSplitConfirmed(false);
    setStake("");
    setActiveStep(1);
  }

  useEffect(() => {
    if (market) resetParticipation(market);
    // The market id is the boundary for a fresh participation draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market?.id]);

  async function advance() {
    setReceipt(null);
    setView("deck");
    if (index + 1 < markets.length) {
      setIndex((current) => current + 1);
    } else {
      await loadFeed();
    }
  }

  function openMarket() {
    setView("market");
    setActiveStep(1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function skip() {
    if (!market) return;
    advance();
  }

  function chooseVote(optionId) {
    setVoteId(optionId);
    setSplitConfirmed(false);
    if (!crowdLeaderId) {
      const initialShare = Math.max(32, minimumLeaderShare + 10);
      setCrowdLeaderId(optionId);
      setLeaderShare(initialShare);
      setForecast(splitAllocations(market.options, optionId, initialShare));
    }
  }

  function chooseCrowdLeader(optionId) {
    setCrowdLeaderId(optionId);
    setForecast(splitAllocations(market.options, optionId, leaderShare));
    setSplitConfirmed(false);
  }

  function changeLeaderShare(value) {
    const share = Number(value);
    setLeaderShare(share);
    const leaderId = crowdLeaderId || voteId || market.options[0]?.id;
    setCrowdLeaderId(leaderId);
    setForecast(splitAllocations(market.options, leaderId, share));
    setSplitConfirmed(false);
  }

  function goToStep(step) {
    if (step === 1 || (step === 2 && voteId) || (step === 3 && splitConfirmed)) {
      setActiveStep(step);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function confirmSplit() {
    if (!validForecast) return;
    setSplitConfirmed(true);
    setActiveStep(3);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submit() {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const ticket = await api.lock(market.id, voteId, forecast, stakeCents);
      setUser({ ...user, balance_cents: ticket.new_balance_cents });
      setReceipt({
        question: market.question,
        vote: market.options.find((option) => option.id === voteId)?.label,
        stake: ticket.stake_cents,
        delay: ticket.reveal_seconds,
      });
    } catch (event) {
      setError(event.message || "Could not lock this participation.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={`screen feed-screen pulse-deck-feed ${view === "market" ? "market-is-open" : ""}`}>
      <header className="feed-header deck-header">
        <div className="deck-brand">
          <div className="pulse-wordmark compact-wordmark" aria-label="Pulse">Pulse<span>.</span></div>
          <p>Read the room.</p>
        </div>
        <div className="deck-balance" aria-label={`${money(user.balance_cents)} test credits`}>
          <span>Credits</span>
          <strong>{money(user.balance_cents)}</strong>
          <small>{number(user.pulse_score)} Pulse</small>
        </div>
      </header>

      {error && <div className="notice">{error}</div>}
      {loading && <div className="empty">Shuffling your market deck…</div>}
      {!loading && !market && (
        <div className="empty">
          <strong>You have played every market in these channels.</strong>
          <button className="primary-btn" onClick={loadFeed}>Refresh deck</button>
        </div>
      )}

      {market && view === "deck" && (
        <section className="discovery-deck" style={{ "--market-accent": activeColor }}>
          <div className="deck-count">
            <span>For you</span>
            <strong>{index + 1} of {markets.length}</strong>
          </div>

          <div className="card-stack">
            {nextMarket && (
              <article
                className="discovery-card discovery-card--behind"
                style={{ "--market-accent": categoryColor(nextMarket.category.slug) }}
                aria-hidden="true"
              >
                <span>{nextMarket.category.name}</span>
              </article>
            )}

            <article className="discovery-card discovery-card--front">
              <button className="discovery-card__tap" onClick={openMarket}>
                <span className="discovery-card__category">{market.category.name}</span>
                <span className="discovery-card__signal" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                  <i />
                  <i />
                </span>
                <span className="discovery-card__question">{market.question}</span>
                {market.context && <span className="discovery-card__context">{market.context}</span>}
                <span className="discovery-card__options">
                  {market.options.slice(0, 4).map((option) => (
                    <i key={option.id}>{option.label}</i>
                  ))}
                  {market.options.length > 4 && <i>+{market.options.length - 4} more</i>}
                </span>
                <span className="discovery-card__stats">
                  <span><b>{number(market.participant_count)}</b> playing</span>
                  <span><b>{compactMoney(market.pool_volume_cents)}</b> pool</span>
                  <span><b>{duration(market.reveal_seconds)}</b> reveal</span>
                </span>
                <span className="discovery-card__cta">Tap to play <b>→</b></span>
              </button>
            </article>
          </div>

          <div className="deck-actions" aria-label="Market actions">
            <button className="deck-action deck-action--skip" onClick={skip} aria-label="Skip this market">
              <span>×</span>
            </button>
            <div><strong>Pass</strong><small>or play this card</small></div>
            <button className="deck-action deck-action--play" onClick={openMarket} aria-label="Play this market">
              <span>→</span>
            </button>
          </div>
        </section>
      )}

      {market && view === "market" && !receipt && (
        <article className="play-market" style={{ "--market-accent": activeColor }}>
          <header className="play-market__topline">
            <button className="market-back" onClick={() => setView("deck")}>← Deck</button>
            <span>{market.category.name}</span>
            <button className="market-skip-compact" onClick={skip}>Skip</button>
          </header>

          <div className="play-market__question">
            <div>
              <span>{number(market.participant_count)} playing</span>
              <span>{duration(market.reveal_seconds)} reveal</span>
            </div>
            <h1>{market.question}</h1>
            {market.context && <p>{market.context}</p>}
          </div>

          <nav className="market-progress" aria-label="Participation progress">
            {[
              [1, "Vote"],
              [2, "Split"],
              [3, "Stake"],
            ].map(([step, label]) => {
              const available = step === 1 || (step === 2 && voteId) || (step === 3 && splitConfirmed);
              const complete = step === 1 ? voteId : step === 2 ? splitConfirmed : stakeCents > 0;
              return (
                <button
                  key={step}
                  className={`${activeStep === step ? "active" : ""} ${complete ? "complete" : ""}`}
                  disabled={!available}
                  onClick={() => goToStep(step)}
                  aria-current={activeStep === step ? "step" : undefined}
                >
                  <i>{complete && activeStep !== step ? "✓" : step}</i>
                  <span>{label}</span>
                </button>
              );
            })}
          </nav>

          {activeStep === 1 && (
            <section className="market-step vote-step">
              <div className="market-step__heading">
                <span>Step 1 of 3</span>
                <h2>What’s true for you?</h2>
                <p>There is no correct answer here. Pick your honest vote.</p>
              </div>
              <div className="market-vote-grid">
                {market.options.map((option, optionIndex) => (
                  <button
                    key={option.id}
                    className={voteId === option.id ? "selected" : ""}
                    aria-pressed={voteId === option.id}
                    onClick={() => chooseVote(option.id)}
                  >
                    <i>{String.fromCharCode(65 + optionIndex)}</i>
                    <span>{option.label}</span>
                    <b>{voteId === option.id ? "✓" : "○"}</b>
                  </button>
                ))}
              </div>
              <div className="market-step__actions">
                <button className="primary-btn full" disabled={!voteId} onClick={() => goToStep(2)}>
                  {voteId ? "Next: guess the crowd →" : "Choose your answer"}
                </button>
              </div>
            </section>
          )}

          {activeStep === 2 && (
            <section className="market-step split-step">
              <div className="market-step__heading">
                <span>Step 2 of 3</span>
                <h2>How will the crowd split?</h2>
                <p>Tap the bar you think wins, then drag to show how far ahead it lands.</p>
              </div>

              <div
                className="split-chart"
                style={{ "--option-count": market.options.length }}
                role="radiogroup"
                aria-label="Predicted crowd split"
              >
                {market.options.map((option) => {
                  const percent = (forecast[option.id] || 0) / 100;
                  const selected = crowdLeaderId === option.id;
                  return (
                    <button
                      key={option.id}
                      className={selected ? "selected" : ""}
                      onClick={() => chooseCrowdLeader(option.id)}
                      role="radio"
                      aria-checked={selected}
                      aria-label={`${option.label}, ${Math.round(percent)} percent${selected ? ", predicted winner" : ""}`}
                      title={option.label}
                    >
                      <strong>{Math.round(percent)}%</strong>
                      <i style={{ "--bar-height": `${Math.max(7, percent)}%` }} />
                      <span>{option.label}</span>
                    </button>
                  );
                })}
              </div>

              <div className="split-control">
                <div>
                  <span>Winning share</span>
                  <strong>{splitTone(leaderShare, minimumLeaderShare)} · {leaderShare}%</strong>
                </div>
                <input
                  type="range"
                  min={minimumLeaderShare}
                  max="75"
                  step="1"
                  value={leaderShare}
                  onChange={(event) => changeLeaderShare(event.target.value)}
                  aria-label="Predicted winning share"
                />
                <div className="split-control__labels"><span>Close race</span><span>Runaway</span></div>
              </div>

              <div className="split-readout">
                <span>Your split totals</span>
                <strong>{Math.round(forecastTotal / 100)}%</strong>
              </div>

              <div className="market-step__actions market-step__actions--split">
                <button className="ghost-btn" onClick={() => goToStep(1)}>Back</button>
                <button className="primary-btn" disabled={!validForecast} onClick={confirmSplit}>
                  Next: choose stake →
                </button>
              </div>
            </section>
          )}

          {activeStep === 3 && (
            <section className="market-step stake-step">
              <div className="market-step__heading">
                <span>Step 3 of 3</span>
                <h2>How strong is your read?</h2>
                <p>Stake test credits. A more accurate crowd split earns more of the pool.</p>
              </div>

              <div className="stake-balance">
                <span>Available</span>
                <strong>{money(user.balance_cents)}</strong>
              </div>

              <label className="stake-entry">
                <span>$</span>
                <input
                  type="number"
                  min="0.01"
                  max={(user.balance_cents / 100).toFixed(2)}
                  step="0.01"
                  inputMode="decimal"
                  placeholder="0"
                  value={stake}
                  onChange={(event) => setStake(event.target.value)}
                  aria-label="Stake in test credits"
                />
                <small>test credits</small>
              </label>

              <div className="stake-presets stake-presets--new">
                {[10, 25, 50, 100].map((amount) => (
                  <button
                    key={amount}
                    className={stakeCents === amount * 100 ? "selected" : ""}
                    disabled={amount * 100 > user.balance_cents}
                    onClick={() => setStake(String(amount))}
                  >${amount}</button>
                ))}
              </div>

              <section className={`payout-preview ${stakeCents ? "has-stake" : ""}`}>
                <div className="payout-preview__title">
                  <span>Possible payout</span>
                  <small>Test credits</small>
                </div>
                <div className="payout-range">
                  <div>
                    <span>Minimum</span>
                    <strong>{money(0)}</strong>
                    <small>If your split misses</small>
                  </div>
                  <i aria-hidden="true"><b /></i>
                  <div>
                    <span>Maximum</span>
                    <strong>{stakeCents ? money(payoutCeiling) : "—"}</strong>
                    <small>Available pool ceiling</small>
                  </div>
                </div>
                <p>
                  {stakeCents
                    ? `${money(feeFor(stakeCents))} fee · ${money(user.balance_cents - stakeCents)} left after locking.`
                    : "Enter a stake to see the payout range."}
                </p>
              </section>

              <div className="lock-recap">
                <div><span>Your vote</span><strong>{market.options.find((option) => option.id === voteId)?.label}</strong></div>
                <div><span>Crowd winner</span><strong>{market.options.find((option) => option.id === crowdLeaderId)?.label} · {leaderShare}%</strong></div>
              </div>

              {stakeCents > user.balance_cents && (
                <small className="form-error">Your stake is higher than your available credits.</small>
              )}

              <div className="market-step__actions market-step__actions--split">
                <button className="ghost-btn" onClick={() => goToStep(2)}>Back</button>
                <button className="primary-btn" disabled={!canSubmit || submitting} onClick={submit}>
                  {submitting ? "Locking…" : stakeCents ? `Lock ${money(stakeCents)} →` : "Enter a stake"}
                </button>
              </div>
              <small className="stake-disclaimer">No real money. Your vote, split, and stake lock together.</small>
            </section>
          )}

          {market.simulation_seed && (
            <details className="debug-panel">
              <summary>DEBUG simulation</summary>
              <code>{market.simulation_seed}</code>
              <pre>{JSON.stringify(market.latent_distribution_bps, null, 2)}</pre>
            </details>
          )}
        </article>
      )}

      {receipt && (
        <section className="lock-receipt market-lock-receipt">
          <span className="receipt-check">✓</span>
          <div className="label">Market locked</div>
          <h1>Your read is in.</h1>
          <p>{receipt.question}</p>
          <div className="receipt-grid">
            <div><span>Your vote</span><strong>{receipt.vote}</strong></div>
            <div><span>Stake</span><strong>{money(receipt.stake)}</strong></div>
            <div><span>Reveal in</span><strong>{duration(receipt.delay)}</strong></div>
          </div>
          <button className="primary-btn full" onClick={advance}>Back to the deck →</button>
        </section>
      )}
    </main>
  );
}
