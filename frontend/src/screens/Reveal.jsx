import { createPortal } from "react-dom";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { breakEvenAccuracy, hasFieldBenchmarks, numeric } from "../revealMath.js";

function money(cents = 0, signed = false) {
  const formatted = new Intl.NumberFormat(undefined, {
    style: "currency", currency: "USD", maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(Math.abs(cents) / 100);
  return signed ? `${cents >= 0 ? "+" : "−"}${formatted}` : formatted;
}

function analysisGrade(score) {
  if (score >= 92) return { label: "Brilliant read", tone: "brilliant" };
  if (score >= 82) return { label: "Great read", tone: "great" };
  if (score >= 68) return { label: "Solid read", tone: "solid" };
  if (score >= 50) return { label: "Inaccuracy", tone: "inaccuracy" };
  return { label: "Miss", tone: "miss" };
}

function pointDifference(value) {
  const absolute = Math.abs(value / 100).toFixed(1);
  if (value > 0) return `+${absolute}`;
  if (value < 0) return `−${absolute}`;
  return "0.0";
}

export default function Reveal({ data, onClose, onNext }) {
  const navigate = useNavigate();
  const [reducedMotion, setReducedMotion] = useState(false);
  const [result, setResult] = useState(data);
  const win = result.pnl_cents >= 0;

  useEffect(() => {
    setReducedMotion(Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches));
  }, []);

  useEffect(() => {
    setResult(data);
  }, [data]);

  useEffect(() => {
    if (hasFieldBenchmarks(result) || !data.prediction_id) return undefined;
    let current = true;
    api.reveal(data.prediction_id)
      .then((next) => {
        if (current) setResult(next);
      })
      .catch(() => {
        // Older servers may not provide comparison benchmarks. The reveal
        // remains complete without displaying placeholder zeroes.
      });
    return () => { current = false; };
    // Refresh an older reveal payload once, keyed to the prediction.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.prediction_id]);

  const analysis = useMemo(() => result.actual_distribution.map((actual) => {
    const forecast = result.forecast.find((item) => item.option_id === actual.option_id);
    const forecastBps = forecast?.bps || 0;
    return {
      ...actual,
      forecastBps,
      differenceBps: forecastBps - actual.bps,
    };
  }), [result.actual_distribution, result.forecast]);
  const meanMiss = analysis.length
    ? analysis.reduce((sum, item) => sum + Math.abs(item.differenceBps), 0) / analysis.length / 100
    : 0;
  const grade = analysisGrade(result.accuracy_score);
  const beatPercent = Math.round(result.accuracy_percentile * 100);
  const benchmarksAvailable = hasFieldBenchmarks(result);
  const breakEvenScore = breakEvenAccuracy(result);
  const breakEvenGap = breakEvenScore === null ? null : result.accuracy_score - breakEvenScore;
  const breakEvenPossible = breakEvenScore !== null && breakEvenScore <= 100;

  const content = (
    <div className={`overlay reveal-overlay ${reducedMotion ? "skip-motion" : ""}`} onClick={onClose}>
      <section className={`v0-reveal analysis-reveal ${win ? "win" : "loss"}`} onClick={(event) => event.stopPropagation()}>
        <div className="reveal-pulse" aria-hidden="true"><i /><i /><i /></div>
        <div className="reveal-topline">
          <div><span>Pulse analysis</span><strong>{result.category_name}</strong></div>
          <button className="text-btn" onClick={onClose} aria-label="Close reveal">Close</button>
        </div>

        <h1>{result.question}</h1>

        <section className={`analysis-summary analysis-summary--${grade.tone}`}>
          <div className="analysis-grade">
            <span>Read review</span>
            <strong>{grade.label}</strong>
            <small>{result.accuracy_score.toFixed(1)} accuracy</small>
          </div>
          <div>
            <span>Average miss</span>
            <strong>{meanMiss.toFixed(1)} pts</strong>
            <small>per answer</small>
          </div>
          <div>
            <span>Field position</span>
            <strong>#{result.forecast_rank} of {result.total_participants}</strong>
            <small>Ahead of {beatPercent}% of players</small>
          </div>
        </section>

        <section className="field-review">
          <div className="analysis-section-heading">
            <div><span>Against the field</span><strong>Your forecast ranked #{result.forecast_rank} of {result.total_participants}</strong></div>
            <b>{beatPercent}% ahead</b>
          </div>
          {benchmarksAvailable ? (
            <div className="field-benchmarks">
              <div className="you">
                <span>Your accuracy</span>
                <strong>{result.accuracy_score.toFixed(1)}</strong>
              </div>
              <div>
                <span>Median accuracy</span>
                <strong>{numeric(result.crowd_median_accuracy_score).toFixed(1)}</strong>
              </div>
              <div>
                <span>Top 25% threshold</span>
                <strong>{numeric(result.crowd_top_quartile_accuracy_score).toFixed(1)}</strong>
              </div>
              <div>
                <span>Top 10% threshold</span>
                <strong>{numeric(result.crowd_top_ten_accuracy_score).toFixed(1)}</strong>
              </div>
            </div>
          ) : (
            <p className="field-rank-explanation">
              You finished ahead of {beatPercent}% of the field. Higher accuracy earns more influence in the payout calculation.
            </p>
          )}
        </section>

        <section className="split-analysis-board">
          <div className="analysis-section-heading">
            <div>
              <span>Split review</span>
              <strong>Actual crowd vs your prediction</strong>
            </div>
            <small>Every bar uses the same 0–100% scale</small>
          </div>
          <div className="split-vote-note">
            <span>Your answer</span>
            <strong>{result.vote.label}</strong>
          </div>

          <div className="split-analysis-list">
            {analysis.map((item) => {
              const direction = item.differenceBps > 0 ? "over" : item.differenceBps < 0 ? "under" : "exact";
              const explanation = direction === "over"
                ? `You put ${(item.differenceBps / 100).toFixed(1)} points too much here`
                : direction === "under"
                  ? `You put ${(Math.abs(item.differenceBps) / 100).toFixed(1)} points too little here`
                  : "You matched the crowd exactly";
              return (
                <div className={`split-analysis-row ${direction}`} key={item.option_id}>
                  <div className="split-analysis-label">
                    <strong>{item.label}</strong>
                    <span>{explanation}</span>
                    <b>{pointDifference(item.differenceBps)} pts</b>
                  </div>
                  <div className="split-comparison-bars">
                    <div className="actual">
                      <span>Actual</span>
                      <i><b style={{ width: `${item.bps / 100}%` }} /></i>
                      <strong>{(item.bps / 100).toFixed(1)}%</strong>
                    </div>
                    <div className="forecast">
                      <span>You</span>
                      <i><b style={{ width: `${item.forecastBps / 100}%` }} /></i>
                      <strong>{(item.forecastBps / 100).toFixed(1)}%</strong>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="payout-analysis">
          <div className="analysis-section-heading">
            <div><span>Payout review</span><strong>Why you received {money(result.payout_cents)}</strong></div>
            <b className={win ? "positive" : "negative"}>{money(result.pnl_cents, true)}</b>
          </div>

          <div className="payout-facts">
            <div>
              <span>Your stake</span>
              <strong>{money(result.stake_cents)}</strong>
            </div>
            <div>
              <span>Your accuracy</span>
              <strong>{result.accuracy_score.toFixed(1)}</strong>
            </div>
            <div>
              <span>Break-even accuracy</span>
              <strong>{breakEvenScore === null ? "—" : breakEvenScore.toFixed(1)}</strong>
            </div>
            <div>
              <span>Your payout</span>
              <strong>{money(result.payout_cents)}</strong>
            </div>
          </div>

          <p className="payout-explanation">
            Accuracy is capped at 100. It sets your share relative to every other player’s accuracy and stake—it is not a cash multiplier.
          </p>

          <div className={`break-even-callout ${win ? "cleared" : "missed"}`}>
            <span aria-hidden="true">{win ? "✓" : "↗"}</span>
            <p>
              <strong>{breakEvenPossible
                ? `About ${breakEvenScore.toFixed(1)} accuracy would have returned your full stake`
                : breakEvenScore === null
                  ? "Your break-even target could not be calculated for this saved reveal"
                  : "A perfect read would not have returned your full stake"}
              </strong>
              <small>{breakEvenPossible
                ? win
                  ? `Your ${result.accuracy_score.toFixed(1)} score cleared that target by ${Math.abs(breakEvenGap).toFixed(1)} points, producing a ${money(result.pnl_cents, true)} result.`
                  : `Your ${result.accuracy_score.toFixed(1)} score was ${Math.abs(breakEvenGap).toFixed(1)} points short, so ${money(result.payout_cents)} came back from your ${money(result.stake_cents)} stake.`
                : breakEvenScore === null
                  ? `You received ${money(result.payout_cents)} back from a ${money(result.stake_cents)} stake.`
                  : "This stake was too large relative to the remaining pool and field performance."}
              </small>
            </p>
          </div>
        </section>

        <div className="analysis-outcome">
          <div>
            <span>Result</span>
            <strong className={win ? "positive" : "negative"}>{money(result.pnl_cents, true)}</strong>
          </div>
          <div>
            <span>Payout</span>
            <strong>{money(result.payout_cents)}</strong>
          </div>
          <div>
            <span>Pulse</span>
            <strong>{result.pulse_delta >= 0 ? "+" : ""}{result.pulse_delta}</strong>
          </div>
        </div>

        <div className="reveal-actions">
          <button className="primary-btn" onClick={() => { onNext?.(); navigate("/feed"); }}>
            Back to market deck →
          </button>
        </div>
      </section>
    </div>
  );

  return createPortal(content, document.body);
}
