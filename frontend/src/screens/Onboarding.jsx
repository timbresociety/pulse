import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const slides = [
  {
    eyebrow: "Welcome to Pulse",
    title: "A question. Your truth. The crowd.",
    copy: "Pulse is a game about reading people. Every card starts with one simple question.",
    visual: "card",
  },
  {
    eyebrow: "First, vote",
    title: "Say what’s true for you.",
    copy: "Choose your honest answer before you see how anyone else voted.",
    visual: "vote",
  },
  {
    eyebrow: "Then, read the room",
    title: "Draw how the crowd will split.",
    copy: "Pick the answer you think wins. Drag the graph from a close race to a runaway.",
    visual: "split",
  },
  {
    eyebrow: "Finally, stake",
    title: "Back your read with test credits.",
    copy: "See the possible payout before you lock. More accurate crowd guesses earn more of the pool.",
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
    return (
      <div className="intro-demo intro-demo--split" aria-hidden="true">
        <small>Your crowd guess</small>
        <div className="intro-mini-chart">
          <span><b>18%</b><i style={{ "--intro-bar": "38%" }} /></span>
          <span className="winner"><b>46%</b><i style={{ "--intro-bar": "88%" }} /></span>
          <span><b>21%</b><i style={{ "--intro-bar": "44%" }} /></span>
          <span><b>15%</b><i style={{ "--intro-bar": "30%" }} /></span>
        </div>
        <div className="intro-mini-range"><i /><b /></div>
        <div className="intro-mini-labels"><span>Close</span><span>Runaway</span></div>
      </div>
    );
  }

  if (type === "stake") {
    return (
      <div className="intro-demo intro-demo--stake" aria-hidden="true">
        <small>Your stake</small>
        <div className="intro-mini-input"><b>$</b><strong>25</strong><span>credits</span></div>
        <div className="intro-mini-payout">
          <span><small>Maximum possible payout</small><b>$1.2K</b></span>
        </div>
        <strong>See the upside before you lock</strong>
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
            {last ? "Choose my channels →" : "Next →"}
          </button>
        </div>
        <small>Test credits only · No real money</small>
      </footer>
    </main>
  );
}
