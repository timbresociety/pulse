import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";

function money(cents = 0) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(cents / 100);
}

function number(value = 0) {
  return new Intl.NumberFormat().format(value);
}

function duration(seconds = 0) {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function equalAllocations(options) {
  const base = Math.floor(10000 / options.length);
  let remaining = 10000 - base * options.length;
  return Object.fromEntries(options.map((option) => {
    const value = base + (remaining > 0 ? 1 : 0);
    remaining -= remaining > 0 ? 1 : 0;
    return [option.id, value];
  }));
}

const explainer = [
  ["01", "Answer", "Tap the option that is true for you."],
  ["02", "Shape", "Show how the crowd leans without doing percentage math."],
  ["03", "Lock", "Pick a test stake and commit once."],
];

const crowdShapes = [
  { id: "tight", label: "Tight race", hint: "Almost even", lift: 400 },
  { id: "lean", label: "Leaning", hint: "Small edge", lift: 1400 },
  { id: "clear", label: "Clear lead", hint: "Strong edge", lift: 2800 },
  { id: "landslide", label: "Landslide", hint: "Runs away", lift: 5000 },
];

function shapedAllocations(options, leaderId, shapeId) {
  if (!options.length) return {};
  if (!leaderId) return equalAllocations(options);

  const shape = crowdShapes.find((item) => item.id === shapeId) || crowdShapes[1];
  const equalShare = Math.floor(10000 / options.length);
  const leaderShare = Math.min(9000, equalShare + shape.lift);
  const others = options.filter((option) => option.id !== leaderId);
  const otherBase = Math.floor((10000 - leaderShare) / Math.max(1, others.length));
  let remainder = 10000 - leaderShare - (otherBase * others.length);

  return Object.fromEntries(options.map((option) => {
    if (option.id === leaderId) return [option.id, leaderShare];
    const value = otherBase + (remainder > 0 ? 1 : 0);
    remainder -= remainder > 0 ? 1 : 0;
    return [option.id, value];
  }));
}

export default function Feed() {
  const { user, setUser } = useAuth();
  const [markets, setMarkets] = useState([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [voteId, setVoteId] = useState("");
  const [forecast, setForecast] = useState({});
  const [crowdLeaderId, setCrowdLeaderId] = useState("");
  const [crowdShape, setCrowdShape] = useState("lean");
  const [stake, setStake] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [receipt, setReceipt] = useState(null);

  const market = markets[index];
  const forecastTotal = useMemo(
    () => Object.values(forecast).reduce((sum, value) => sum + (Number(value) || 0), 0),
    [forecast],
  );
  const stakeCents = Math.max(0, Math.round((Number(stake) || 0) * 100));
  const validForecast = market
    && Object.keys(forecast).length === market.options.length
    && forecastTotal === 10000;
  const canSubmit = voteId && validForecast && stakeCents > 0 && stakeCents <= user.balance_cents;

  async function loadFeed() {
    setLoading(true);
    setError("");
    try {
      const data = await api.feed(50);
      setMarkets(data);
      setIndex(0);
    } catch (event) {
      setError(event.message || "Could not load Pulse markets.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFeed();
  }, []);

  function resetParticipation(nextMarket = markets[index]) {
    setVoteId("");
    setForecast(nextMarket ? equalAllocations(nextMarket.options) : {});
    setCrowdLeaderId("");
    setCrowdShape("lean");
    setStake("");
  }

  useEffect(() => {
    if (market) resetParticipation(market);
    // Market identity is the reset boundary for an immutable participation draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market?.id]);

  async function advance() {
    setReceipt(null);
    if (index + 1 < markets.length) {
      setIndex((current) => current + 1);
    } else {
      await loadFeed();
    }
  }

  function skip() {
    if (!market) return;
    advance();
  }

  function chooseVote(optionId) {
    setVoteId(optionId);
    if (!crowdLeaderId) {
      setCrowdLeaderId(optionId);
      setForecast(shapedAllocations(market.options, optionId, crowdShape));
    }
  }

  function chooseCrowdLeader(optionId) {
    setCrowdLeaderId(optionId);
    setForecast(shapedAllocations(market.options, optionId, crowdShape));
  }

  function chooseCrowdShape(shapeId) {
    const leaderId = crowdLeaderId || voteId || market.options[0]?.id;
    setCrowdShape(shapeId);
    setCrowdLeaderId(leaderId);
    setForecast(shapedAllocations(market.options, leaderId, shapeId));
  }

  function nudgeAllocation(optionId, delta) {
    setForecast((current) => {
      const currentValue = current[optionId] || 0;
      const target = Math.max(0, Math.min(10000, currentValue + delta));
      const others = market.options.filter((option) => option.id !== optionId);
      if (!others.length) return { [optionId]: 10000 };

      const remaining = 10000 - target;
      const otherTotal = others.reduce((sum, option) => sum + (current[option.id] || 0), 0);
      const raw = others.map((option) => (
        otherTotal
          ? ((current[option.id] || 0) * remaining) / otherTotal
          : remaining / others.length
      ));
      const values = raw.map(Math.floor);
      let remainder = remaining - values.reduce((sum, value) => sum + value, 0);
      raw
        .map((value, idx) => [idx, value - values[idx]])
        .sort((a, b) => b[1] - a[1] || a[0] - b[0])
        .slice(0, remainder)
        .forEach(([idx]) => { values[idx] += 1; });

      return Object.fromEntries([
        [optionId, target],
        ...others.map((option, idx) => [option.id, values[idx]]),
      ]);
    });
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
    <main className="screen feed-screen">
      <header className="feed-header pulse-header">
        <div>
          <div className="pulse-wordmark compact-wordmark" aria-label="Pulse">Pulse<span>.</span></div>
          <p>Vote your truth. Predict the crowd.</p>
        </div>
        <div className="balance-pill">
          <span>Balance</span>
          <strong>{money(user.balance_cents)}</strong>
          <small>{user.pulse_score} Pulse</small>
        </div>
      </header>

      {error && <div className="notice">{error}</div>}
      {loading && <div className="empty">Loading the market deck…</div>}
      {!loading && !market && (
        <div className="empty">
          <strong>You have read every market in these channels.</strong>
          <button className="primary-btn" onClick={loadFeed}>Refresh deck</button>
        </div>
      )}

      {market && !receipt && (
        <div className="market-deck v0-deck">
          <article className="pulse-card v0-market-card market-compose-card">
            <div className="market-topline">
              <span>{market.category.name}</span>
              <button className="text-btn market-skip" onClick={skip}>Skip →</button>
            </div>

            <div className="market-question">
              <div className="market-question-meta">
                <b>{number(market.participant_count)} people</b>
                <b>{duration(market.reveal_seconds)} reveal</b>
              </div>
              <h1>{market.question}</h1>
              {market.context && <p>{market.context}</p>}
            </div>

            <section className={`composer-stage answer-stage ${voteId ? "complete" : ""}`}>
              <div className="stage-heading">
                <span className="stage-number">1</span>
                <div><strong>Your answer</strong><small>What is true for you?</small></div>
                {voteId && <i aria-label="Complete">✓</i>}
              </div>
              <div className="answer-grid">
                {market.options.map((option) => (
                  <button
                    key={option.id}
                    className={voteId === option.id ? "selected" : ""}
                    aria-pressed={voteId === option.id}
                    onClick={() => chooseVote(option.id)}
                  >
                    <span>{option.label}</span>
                    <i>{voteId === option.id ? "My answer" : "Choose"}</i>
                  </button>
                ))}
              </div>
            </section>

            <section className={`composer-stage crowd-stage ${crowdLeaderId ? "complete" : ""}`}>
              <div className="stage-heading">
                <span className="stage-number">2</span>
                <div><strong>Draw the crowd</strong><small>Who leads, and by how much?</small></div>
                {crowdLeaderId && <i aria-label="Complete">✓</i>}
              </div>

              <div className="crowd-field" aria-label="Your crowd forecast">
                {market.options.map((option, optionIndex) => (
                  <div
                    key={option.id}
                    className={crowdLeaderId === option.id ? "leader" : ""}
                    style={{
                      "--share": `${forecast[option.id] || 0}`,
                      "--option-index": optionIndex,
                      flexBasis: `${(forecast[option.id] || 0) / 100}%`,
                    }}
                  >
                    <strong>{((forecast[option.id] || 0) / 100).toFixed(0)}%</strong>
                    <span>{option.label}</span>
                  </div>
                ))}
              </div>

              <div className="crowd-leader-grid" aria-label="Predicted crowd leader">
                {market.options.map((option) => (
                  <button
                    key={option.id}
                    className={crowdLeaderId === option.id ? "selected" : ""}
                    aria-pressed={crowdLeaderId === option.id}
                    onClick={() => chooseCrowdLeader(option.id)}
                  >
                    <span>{option.label}</span>
                    <strong>{((forecast[option.id] || 0) / 100).toFixed(0)}%</strong>
                  </button>
                ))}
              </div>

              <div className="shape-picker" aria-label="Shape of the result">
                {crowdShapes.map((shape, shapeIndex) => (
                  <button
                    key={shape.id}
                    className={crowdShape === shape.id ? "selected" : ""}
                    aria-pressed={crowdShape === shape.id}
                    onClick={() => chooseCrowdShape(shape.id)}
                  >
                    <span className="shape-mark" aria-hidden="true">
                      <i style={{ "--bar": 32 + (shapeIndex * 13) }} />
                      <i style={{ "--bar": 68 - (shapeIndex * 13) }} />
                    </span>
                    <strong>{shape.label}</strong>
                    <small>{shape.hint}</small>
                  </button>
                ))}
              </div>

              <details className="precision-editor">
                <summary>Fine-tune the split</summary>
                <div className="precision-list">
                  {market.options.map((option) => (
                    <div key={option.id}>
                      <span>{option.label}</span>
                      <div>
                        <button
                          aria-label={`Reduce ${option.label} by 5 percent`}
                          onClick={() => nudgeAllocation(option.id, -500)}
                          disabled={(forecast[option.id] || 0) === 0}
                        >−</button>
                        <strong>{((forecast[option.id] || 0) / 100).toFixed(0)}%</strong>
                        <button
                          aria-label={`Increase ${option.label} by 5 percent`}
                          onClick={() => nudgeAllocation(option.id, 500)}
                          disabled={(forecast[option.id] || 0) === 10000}
                        >+</button>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            </section>

            <section className={`composer-stage commit-stage ${stakeCents > 0 ? "complete" : ""}`}>
              <div className="stage-heading">
                <span className="stage-number">3</span>
                <div><strong>Choose your stake</strong><small>Test credits only · {money(user.balance_cents)} available</small></div>
                {stakeCents > 0 && <i aria-label="Complete">✓</i>}
              </div>
              <div className="stake-presets">
                {[10, 25, 50, 100].map((amount) => (
                  <button
                    key={amount}
                    className={stakeCents === amount * 100 ? "selected" : ""}
                    disabled={amount * 100 > user.balance_cents}
                    onClick={() => setStake(String(amount))}
                  >${amount}</button>
                ))}
              </div>
              <label className="compact-stake-input">
                <span>$</span>
                <input
                  type="number"
                  min="0.01"
                  max={(user.balance_cents / 100).toFixed(2)}
                  step="0.01"
                  placeholder="Custom"
                  value={stake}
                  onChange={(event) => setStake(event.target.value)}
                  aria-label="Custom stake"
                />
              </label>
              <div className="commit-summary">
                <span>{voteId ? `You: ${market.options.find((option) => option.id === voteId)?.label}` : "Choose your answer"}</span>
                <span>{crowdLeaderId ? `Crowd: ${market.options.find((option) => option.id === crowdLeaderId)?.label} leads` : "Shape the crowd"}</span>
                <span>{stakeCents ? `${money(stakeCents)} stake · ${money(Math.round(stakeCents * 0.02))} fee` : "Choose a stake"}</span>
              </div>
              <button className="primary-btn lock-submit full" disabled={!canSubmit || submitting} onClick={submit}>
                {submitting ? "Locking…" : canSubmit ? `Lock for ${money(stakeCents)}` : "Complete the three choices"}
              </button>
              {stakeCents > user.balance_cents && <small className="form-error">Stake exceeds your available balance.</small>}
              <small className="lock-note">One tap locks your answer, crowd shape, and test stake.</small>
            </section>

            {market.simulation_seed && (
              <details className="debug-panel">
                <summary>DEBUG simulation</summary>
                <code>{market.simulation_seed}</code>
                <pre>{JSON.stringify(market.latent_distribution_bps, null, 2)}</pre>
              </details>
            )}
          </article>
        </div>
      )}

      {receipt && (
        <section className="lock-receipt">
          <span className="receipt-check">✓</span>
          <div className="label">Participation locked</div>
          <h1>{receipt.question}</h1>
          <div className="receipt-grid">
            <div><span>Your vote</span><strong>{receipt.vote}</strong></div>
            <div><span>Stake</span><strong>{money(receipt.stake)}</strong></div>
            <div><span>Reveal in</span><strong>{duration(receipt.delay)}</strong></div>
          </div>
          <p>Your payout is credited only when you reveal the result.</p>
          <button className="primary-btn full" onClick={advance}>Play Next Market</button>
        </section>
      )}

      <section className="how-loop">
        <div className="section-heading"><span>The Pulse loop</span><strong>No real money</strong></div>
        {explainer.map(([count, title, copy]) => (
          <div key={count}><b>{count}</b><span><strong>{title}</strong><small>{copy}</small></span></div>
        ))}
      </section>
    </main>
  );
}
