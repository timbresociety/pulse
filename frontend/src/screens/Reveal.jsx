import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

function money(cents = 0, signed = false) {
  const formatted = new Intl.NumberFormat(undefined, {
    style: "currency", currency: "USD", maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(Math.abs(cents) / 100);
  return signed ? `${cents >= 0 ? "+" : "−"}${formatted}` : formatted;
}

export default function Reveal({ data, onClose, onNext }) {
  const navigate = useNavigate();
  const [skipped, setSkipped] = useState(false);
  const win = data.pnl_cents >= 0;

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) setSkipped(true);
  }, []);

  const content = (
    <div className={`overlay reveal-overlay ${skipped ? "skip-motion" : ""}`} onClick={onClose}>
      <section className={`v0-reveal ${win ? "win" : "loss"}`} onClick={(event) => event.stopPropagation()}>
        <div className="reveal-pulse" aria-hidden="true"><i /><i /><i /></div>
        <div className="reveal-topline">
          <div><span>Pulse reveal</span><strong>{data.category_name}</strong></div>
          <button className="text-btn" onClick={onClose} aria-label="Close reveal">Close</button>
        </div>
        <h1>{data.question}</h1>
        <div className="reveal-vote"><span>Your vote</span><strong>{data.vote.label}</strong></div>

        <div className="reveal-distributions">
          {data.actual_distribution.map((actual) => {
            const forecast = data.forecast.find((item) => item.option_id === actual.option_id);
            return (
              <div key={actual.option_id} className="reveal-distribution-row">
                <div><span>{actual.label}</span><strong>{(actual.bps / 100).toFixed(1)}%</strong></div>
                <div className="actual-track"><i style={{ width: `${actual.bps / 100}%` }} /></div>
                <small>Your forecast {(forecast.bps / 100).toFixed(1)}%</small>
              </div>
            );
          })}
        </div>

        <div className="accuracy-hero">
          <span>Accuracy score</span>
          <strong>{data.accuracy_score.toFixed(1)}</strong>
          <small>{Math.round(data.accuracy_percentile * 100)}th percentile · rank #{data.forecast_rank} of {data.total_participants}</small>
        </div>

        <section className="difference-panel">
          <div className="section-heading"><span>Largest forecast differences</span><strong>Forecast − actual</strong></div>
          {data.largest_differences.map((difference) => (
            <div key={difference.option_id}>
              <span>{difference.label}</span>
              <strong>{difference.difference_bps >= 0 ? "+" : ""}{(difference.difference_bps / 100).toFixed(1)} pts</strong>
            </div>
          ))}
        </section>

        <div className="settlement-grid reveal-settlement">
          <div><span>Stake</span><strong>{money(data.stake_cents)}</strong></div>
          <div><span>Fee</span><strong>{money(data.user_fee_cents)}</strong></div>
          <div><span>Payout</span><strong>{money(data.payout_cents)}</strong></div>
          <div><span>PnL</span><strong className={win ? "positive" : "negative"}>{money(data.pnl_cents, true)}</strong></div>
          <div><span>Pulse score</span><strong>{data.pulse_delta >= 0 ? "+" : ""}{data.pulse_delta}</strong></div>
        </div>

        <div className="reveal-actions">
          {!skipped && <button className="ghost-btn" onClick={() => setSkipped(true)}>Skip Animation</button>}
          <button className="primary-btn" onClick={() => { onNext?.(); navigate("/feed"); }}>Play Next Market</button>
        </div>
      </section>
    </div>
  );

  return createPortal(content, document.body);
}
