import { createPortal } from "react-dom";

function formatNumber(value = 0) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

export default function Reveal({ data, onClose }) {
  const win = data.outcome === "win";
  const pct = Math.round((data.shown_share || 0) * 1000) / 10;

  const content = (
    <div className={`overlay ${win ? "win" : "lose"}`} onClick={onClose}>
      <section className={`reveal-card ${win ? "win" : "lose"}`} onClick={(event) => event.stopPropagation()}>
        <div className="reveal-burst" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </div>
        <div className="reveal-prize" aria-hidden="true">
          <span />
          <span />
        </div>
        <div className="label">Psyblr reveal</div>
        <h1>{win ? "Room read." : "Room swerved."}</h1>

        <div className="reveal-focus">
          <span>Top call</span>
          <strong>{data.winning_object || data.your_pick || "Unresolved"}</strong>
          <small>{pct}% hidden share</small>
          <div className="share-meter" aria-hidden="true">
            <span style={{ width: `${Math.min(100, Math.max(3, pct))}%` }} />
          </div>
        </div>

        <div className="reveal-grid">
          <div>
            <span>Your call</span>
            <strong>{data.your_pick || "Unknown"}</strong>
          </div>
          <div>
            <span>Pool</span>
            <strong>{formatNumber(data.pool_size)}</strong>
          </div>
          <div>
            <span>Payout</span>
            <strong>{win ? `${data.payout_multiplier}x` : "0x"}</strong>
          </div>
          <div>
            <span>Score</span>
            <strong>{data.pulse_delta > 0 ? `+${data.pulse_delta}` : data.pulse_delta}</strong>
          </div>
        </div>

        {!win && data.taste_signal && (
          <div className="taste-signal">
            <strong>Taste signal</strong>
            <span>{data.taste_signal}</span>
          </div>
        )}

        <div className={`coin-win ${win ? "hot" : "cold"}`}>
          {win ? `+${formatNumber(data.coins_won)} coins` : "0 coin payout"}
        </div>

        <button className="primary-btn full" onClick={onClose}>Claim screen</button>
      </section>
    </div>
  );

  return createPortal(content, document.body);
}
