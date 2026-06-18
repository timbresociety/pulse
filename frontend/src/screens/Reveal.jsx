export default function Reveal({ data, onClose }) {
  const win = data.outcome === "win";
  const pct = Math.round((data.shown_share || 0) * 100);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="reveal" onClick={(e) => e.stopPropagation()}>
        <div className={`verdict ${win ? "win" : "lose"}`}>
          {win ? "You read the room!" : "You missed the crowd"}
        </div>

        <div className="muted">
          {win ? "Your pick was the top call" : "Top call was"}
        </div>
        <div style={{ fontWeight: 800, fontSize: 18, margin: "4px 0 2px" }}>
          {win ? data.your_pick : data.winning_object || "—"}
        </div>
        <div className="muted">{pct}% picked this</div>

        {win ? (
          <div className="big-coins win">+{data.coins_won} 🪙</div>
        ) : (
          <div style={{ margin: "16px 0" }} className="muted">
            Your call: {data.your_pick}
          </div>
        )}

        <div className="muted" style={{ marginBottom: 16 }}>
          {data.pulse_delta > 0 ? `+${data.pulse_delta} pulse` : "no pulse change"}
          {"  •  "}🪙 {data.new_coins} · ⚡ {data.new_pulse}
        </div>

        <button className="btn btn-primary" onClick={onClose}>Next →</button>
      </div>
    </div>
  );
}
