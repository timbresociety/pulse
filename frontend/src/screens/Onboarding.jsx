import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const slides = [
  {
    eyebrow: "First, choose categories",
    title: "Pick topics you know.",
    copy: "Choose categories you understand, then enter a market when you have an opinion about the question.",
    visual: "card",
  },
  {
    eyebrow: "Then, answer",
    title: "Choose the answer that fits you best.",
    copy: "Read the question and pick the option closest to your own answer.",
    visual: "vote",
  },
  {
    eyebrow: "Next, guess the split",
    title: "Guess how everyone else will vote.",
    copy: "Set the percentage you expect for each answer. The bars always add up to 100%.",
    visual: "split",
  },
  {
    eyebrow: "Finally, choose an amount",
    title: "Use test credits and wait for the result.",
    copy: "Choose an amount you are comfortable with. Then wait for the market to close. An accurate guess can win more test credits.",
    visual: "stake",
  },
];

function IntroVisual({ type }) {
  if (type === "vote") {
    return (
      <div className="intro-demo intro-demo--vote" aria-hidden="true">
        <small>Your answer</small>
        <div>
          <span><i>A</i> Inspiring</span>
          <span className="picked"><i>B</i> Entertaining <b>✓</b></span>
          <span><i>C</i> Useful</span>
          <span><i>D</i> Repetitive</span>
        </div>
        <strong>Choose what feels true</strong>
      </div>
    );
  }

  if (type === "split") {
    const split = [
      { label: "A", percent: 18 },
      { label: "B", percent: 46, active: true },
      { label: "C", percent: 21, locked: true },
      { label: "D", percent: 15 },
    ];

    return (
      <div className="intro-demo intro-demo--split" aria-hidden="true">
        <small>Your crowd guess</small>
        <div className="intro-split-chart">
          {split.map((option) => (
            <div
              key={option.label}
              className={`intro-split-column${option.active ? " active" : ""}${option.locked ? " locked" : ""}`}
            >
              <span className="intro-split-plot" style={{ "--intro-bar": `${option.percent}%` }}>
                <strong>{option.percent}%</strong>
                <i />
              </span>
              <span className="intro-split-label">{option.label}</span>
              <span className="intro-split-lock"><i /></span>
            </div>
          ))}
        </div>
        <div className="intro-split-status">
          <i>↕</i>
          <span>
            <b>Drag any bar</b>
            <small>The others rebalance to total 100%</small>
          </span>
          <strong>Auto-balanced</strong>
        </div>
      </div>
    );
  }

  if (type === "stake") {
    return (
      <div className="intro-demo intro-demo--stake" aria-hidden="true">
        <small>Your stake</small>
        <div className="intro-mini-input"><b>$</b><strong>25</strong><span>credits</span></div>
        <div className="intro-mini-payout">
          <div className="intro-mini-payout-title">
            <span>Maximum possible payout</span>
            <small>Test credits</small>
          </div>
          <div className="intro-mini-payout-value">
            <b>$1.2K</b>
            <small>Available pool ceiling</small>
          </div>
        </div>
        <strong>Review the payout before you confirm</strong>
      </div>
    );
  }

  return (
    <div className="intro-demo intro-demo--card" aria-hidden="true">
      <i className="intro-card-back" />
      <div className="intro-card-front">
        <small>INTERNET</small>
        <span className="intro-pulse-mark"><i /><i /><i /></span>
        <strong>How does your main social feed feel right now?</strong>
        <span>Tap to play <b>→</b></span>
      </div>
    </div>
  );
}

export default function Onboarding({ onComplete }) {
  const navigate = useNavigate();
  const [index, setIndex] = useState(0);
  const slide = slides[index];
  const last = index === slides.length - 1;

  function finish() {
    onComplete();
    navigate("/categories");
  }

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "ArrowRight") {
        if (last) finish();
        else setIndex((current) => Math.min(slides.length - 1, current + 1));
      }
      if (event.key === "ArrowLeft") {
        setIndex((current) => Math.max(0, current - 1));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  return (
    <main className="screen intro-screen">
      <header className="intro-header">
        <div className="pulse-wordmark compact-wordmark" aria-label="Pulse">Pulse<span>.</span></div>
        {!last && <button onClick={finish}>Skip intro</button>}
      </header>

      <section className="intro-carousel" aria-live="polite">
        <div className="intro-visual-wrap" key={`visual-${slide.visual}`}>
          <IntroVisual type={slide.visual} />
        </div>

        <div className="intro-copy" key={`copy-${index}`}>
          <span>{slide.eyebrow}</span>
          <h1>{slide.title}</h1>
          <p>{slide.copy}</p>
        </div>
      </section>

      <footer className="intro-footer">
        <div className="intro-dots" aria-label={`Slide ${index + 1} of ${slides.length}`}>
          {slides.map((item, slideIndex) => (
            <button
              key={item.title}
              className={slideIndex === index ? "active" : ""}
              onClick={() => setIndex(slideIndex)}
              aria-label={`Go to slide ${slideIndex + 1}`}
              aria-current={slideIndex === index ? "step" : undefined}
            />
          ))}
        </div>

        <div className="intro-actions">
          {index > 0 && <button className="ghost-btn" onClick={() => setIndex(index - 1)}>Back</button>}
          <button
            className="primary-btn"
            onClick={() => (last ? finish() : setIndex(index + 1))}
          >
            {last ? "Choose my categories →" : "Next →"}
          </button>
        </div>
        <small>Test credits only · No real money</small>
      </footer>
    </main>
  );
}
