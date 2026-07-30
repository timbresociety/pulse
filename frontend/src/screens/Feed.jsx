import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";
import { equalAllocations, rebalanceAllocations } from "../forecast.js";
import { formatPayout, maximumPayoutCents, platformFeeCents } from "../payout.js";

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

export default function Feed() {
  const { user, setUser } = useAuth();
  const [markets, setMarkets] = useState(() => api.peek("feed:50") || []);
  const [index, setIndex] = useState(0);
  const [view, setView] = useState("deck");
  const [activeStep, setActiveStep] = useState(1);
  const [loading, setLoading] = useState(() => !api.peek("feed:50"));
  const [error, setError] = useState("");
  const [voteId, setVoteId] = useState("");
  const [forecast, setForecast] = useState({});
  const [activeSplitId, setActiveSplitId] = useState("");
  const [draggingSplitId, setDraggingSplitId] = useState("");
  const [lockedSplitIds, setLockedSplitIds] = useState([]);
  const draggingSplitRef = useRef("");
  const [splitConfirmed, setSplitConfirmed] = useState(false);
  const [stake, setStake] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const market = markets[index];
  const nextMarket = markets[index + 1];
  const forecastTotal = useMemo(
    () => Object.values(forecast).reduce((sum, value) => sum + (Number(value) || 0), 0),
    [forecast],
  );
  const leadingOptions = useMemo(() => {
    if (!market?.options.length) return [];
    const highest = Math.max(...market.options.map((option) => Number(forecast[option.id]) || 0));
    return market.options.filter((option) => (Number(forecast[option.id]) || 0) === highest);
  }, [forecast, market]);
  const leadingShare = leadingOptions.length ? (forecast[leadingOptions[0].id] || 0) / 100 : 0;
  const leadingSummary = leadingOptions.length > 1
    ? `${leadingOptions.length}-way tie · ${leadingShare}%`
    : `${leadingOptions[0]?.label || "—"} · ${leadingShare}%`;
  const stakeCents = Math.max(0, Math.round((Number(stake) || 0) * 100));
  const validForecast = Boolean(
    market
      && Object.keys(forecast).length === market.options.length
      && forecastTotal === 10000,
  );
  const canSubmit = Boolean(
    voteId && validForecast && splitConfirmed && stakeCents > 0 && stakeCents <= user.balance_cents,
  );
  const maximumPayout = market && stakeCents
    ? maximumPayoutCents({
      poolVolumeCents: market.pool_volume_cents,
      netPoolVolumeCents: market.net_pool_volume_cents,
      stakeCents,
    })
    : 0;
  const activeColor = categoryColor(market?.category?.slug);

  async function loadFeed(force = false) {
    setLoading(true);
    setError("");
    try {
      const data = await api.feed(50, { force });
      setMarkets(data);
      setIndex(0);
      setView("deck");
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
    setActiveSplitId("");
    setDraggingSplitId("");
    setLockedSplitIds([]);
    draggingSplitRef.current = "";
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
    setView("deck");
    if (index + 1 < markets.length) {
      setIndex((current) => current + 1);
    } else {
      await loadFeed(true);
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
  }

  function changeSplitOption(optionId, nextPercent) {
    if (lockedSplitIds.includes(optionId)) return;
    setActiveSplitId(optionId);
    setForecast((current) => rebalanceAllocations(
      market.options,
      current,
      optionId,
      nextPercent,
      lockedSplitIds,
    ));
    setSplitConfirmed(false);
  }

  function toggleSplitLock(optionId) {
    if (draggingSplitRef.current === optionId) clearSplitDrag();
    setActiveSplitId(optionId);
    setLockedSplitIds((current) => (
      current.includes(optionId)
        ? current.filter((id) => id !== optionId)
        : [...current, optionId]
    ));
  }

  function splitPercentFromPointer(event) {
    const plot = event.currentTarget.querySelector(".split-bar__plot");
    if (!plot) return 0;
    const bounds = plot.getBoundingClientRect();
    const position = (bounds.bottom - event.clientY) / Math.max(1, bounds.height);
    return Math.round(Math.min(1, Math.max(0, position)) * 100);
  }

  function beginSplitDrag(event, optionId) {
    if (lockedSplitIds.includes(optionId)) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    draggingSplitRef.current = optionId;
    setDraggingSplitId(optionId);
    changeSplitOption(optionId, splitPercentFromPointer(event));
  }

  function moveSplitDrag(event, optionId) {
    if (draggingSplitRef.current !== optionId) return;
    event.preventDefault();
    changeSplitOption(optionId, splitPercentFromPointer(event));
  }

  function clearSplitDrag() {
    draggingSplitRef.current = "";
    setDraggingSplitId("");
  }

  function endSplitDrag(event, optionId) {
    if (draggingSplitRef.current === optionId) {
      changeSplitOption(optionId, splitPercentFromPointer(event));
    }
    draggingSplitRef.current = "";
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDraggingSplitId("");
  }

  function changeSplitWithKeyboard(event, optionId, currentPercent) {
    if (lockedSplitIds.includes(optionId)) return;
    const changes = {
      ArrowUp: currentPercent + 1,
      ArrowRight: currentPercent + 1,
      ArrowDown: currentPercent - 1,
      ArrowLeft: currentPercent - 1,
      PageUp: currentPercent + 5,
      PageDown: currentPercent - 5,
      Home: 0,
      End: 100,
    };
    if (!(event.key in changes)) return;
    event.preventDefault();
    changeSplitOption(optionId, changes[event.key]);
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
      setUser((current) => ({ ...current, balance_cents: ticket.new_balance_cents }));
      await advance();
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
          <button className="primary-btn" onClick={() => loadFeed(true)}>Refresh deck</button>
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

      {market && view === "market" && (
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
                <p>Drag any bar up or down. Lock values you want to hold while the rest rebalance.</p>
              </div>

              <div
                className="split-chart"
                style={{ "--option-count": market.options.length }}
                aria-label="Predicted crowd split"
              >
                {market.options.map((option) => {
                  const percent = (forecast[option.id] || 0) / 100;
                  const active = activeSplitId === option.id;
                  const dragging = draggingSplitId === option.id;
                  const locked = lockedSplitIds.includes(option.id);
                  const lockedOtherTotal = market.options.reduce((sum, candidate) => (
                    candidate.id !== option.id && lockedSplitIds.includes(candidate.id)
                      ? sum + ((forecast[candidate.id] || 0) / 100)
                      : sum
                  ), 0);
                  return (
                    <div
                      key={option.id}
                      className={`split-column ${locked ? "is-locked" : ""}`}
                    >
                      <button
                        type="button"
                        className={`split-bar ${active ? "active" : ""} ${dragging ? "is-dragging" : ""}`}
                        onPointerDown={(event) => beginSplitDrag(event, option.id)}
                        onPointerMove={(event) => moveSplitDrag(event, option.id)}
                        onPointerUp={(event) => endSplitDrag(event, option.id)}
                        onPointerCancel={clearSplitDrag}
                        onLostPointerCapture={clearSplitDrag}
                        onKeyDown={(event) => changeSplitWithKeyboard(event, option.id, percent)}
                        role="slider"
                        aria-disabled={locked}
                        aria-valuemin={locked ? percent : 0}
                        aria-valuemax={locked ? percent : 100 - lockedOtherTotal}
                        aria-valuenow={percent}
                        aria-valuetext={`${percent} percent${locked ? ", locked" : "; remaining unlocked percentage automatically balanced"}`}
                        aria-label={`${option.label} predicted share`}
                        title={locked ? `${option.label} is locked` : option.label}
                      >
                        <span className="split-bar__plot" style={{ "--bar-height": `${percent}%` }}>
                          <strong>{percent}%</strong>
                          <i><b /></i>
                        </span>
                        <span className="split-bar__label">{option.label}</span>
                      </button>
                      <button
                        type="button"
                        className="split-bar__lock"
                        aria-pressed={locked}
                        aria-label={`${locked ? "Unlock" : "Lock"} ${option.label} at ${percent} percent`}
                        title={`${locked ? "Unlock" : "Lock"} ${option.label}`}
                        onClick={() => toggleSplitLock(option.id)}
                      >
                        <i aria-hidden="true" />
                        <span>{locked ? "Unlock" : "Lock"}</span>
                      </button>
                    </div>
                  );
                })}
              </div>

              <div className="split-auto-balance">
                <div>
                  <span aria-hidden="true">↕</span>
                  <p>
                    <strong>{activeSplitId
                      ? `${market.options.find((option) => option.id === activeSplitId)?.label}: ${forecast[activeSplitId] / 100}%${lockedSplitIds.includes(activeSplitId) ? " · Locked" : ""}`
                      : "Drag a bar to shape your forecast"}
                    </strong>
                    <small>{lockedSplitIds.includes(activeSplitId)
                      ? "This value stays fixed until you unlock it."
                      : lockedSplitIds.length
                        ? "Only unlocked bars share the remaining percentage."
                        : "Lock any value you want to keep fixed."}
                    </small>
                  </p>
                </div>
                <b className={lockedSplitIds.length ? "has-locks" : ""}>{lockedSplitIds.length
                  ? `${lockedSplitIds.length} locked`
                  : "Auto-balanced"}
                </b>
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
                  <span>Maximum possible payout</span>
                  <small>Test credits</small>
                </div>
                <div className="payout-maximum">
                  <strong title={stakeCents ? money(Math.floor(maximumPayout)) : undefined}>
                    {stakeCents ? formatPayout(maximumPayout) : "—"}
                  </strong>
                  <small>Available pool ceiling</small>
                </div>
                <p>
                  {stakeCents
                    ? `${money(platformFeeCents(stakeCents))} fee · ${money(user.balance_cents - stakeCents)} left after locking.`
                    : "Enter a stake to see the maximum possible payout."}
                </p>
              </section>

              <div className="lock-recap">
                <div><span>Your vote</span><strong>{market.options.find((option) => option.id === voteId)?.label}</strong></div>
                <div><span>Top crowd pick</span><strong>{leadingSummary}</strong></div>
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

    </main>
  );
}
