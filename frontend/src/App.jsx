import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Login from "./screens/Login.jsx";
import Onboarding from "./screens/Onboarding.jsx";
import Categories from "./screens/Categories.jsx";
import Feed from "./screens/Feed.jsx";
import History from "./screens/History.jsx";
import Leaderboard from "./screens/Leaderboard.jsx";
import Profile from "./screens/Profile.jsx";
import Wallet from "./screens/Wallet.jsx";

function BottomNav() {
  const items = [
    ["/feed", "◉", "Feed"],
    ["/reveals", "◷", "History"],
    ["/wallet", "$", "Wallet"],
    ["/social", "♢", "Social"],
    ["/profile", "●", "Profile"],
  ];

  return (
    <nav className="bottomnav">
      {items.map(([to, glyph, label]) => (
        <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
          <span className="nav-glyph">{glyph}</span>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  const [, refreshIntroState] = useState(0);

  if (loading) return <div className="app"><div className="empty">Loading Pulse...</div></div>;
  if (!user) return <div className="app"><Login /></div>;

  const hasCategories = user.categories && user.categories.length > 0;
  const introKey = `pulse_intro_v1:${user.id}`;
  const introSeen = hasCategories || localStorage.getItem(introKey) === "seen";

  function completeIntro() {
    localStorage.setItem(introKey, "seen");
    refreshIntroState((value) => value + 1);
  }

  return (
    <div className="app">
      <Routes>
        <Route
          path="/welcome"
          element={
            introSeen
              ? <Navigate to={hasCategories ? "/feed" : "/categories"} />
              : <Onboarding onComplete={completeIntro} />
          }
        />
        <Route
          path="/categories"
          element={introSeen ? <Categories /> : <Navigate to="/welcome" />}
        />
        <Route
          path="/feed"
          element={hasCategories ? <Feed /> : <Navigate to={introSeen ? "/categories" : "/welcome"} />}
        />
        <Route path="/reveals" element={<History />} />
        <Route path="/history" element={<Navigate to="/reveals" />} />
        <Route path="/wallet" element={<Wallet />} />
        <Route path="/social" element={<Leaderboard />} />
        <Route path="/leaderboard" element={<Navigate to="/social" />} />
        <Route path="/profile" element={<Profile />} />
        <Route
          path="*"
          element={<Navigate to={hasCategories ? "/feed" : introSeen ? "/categories" : "/welcome"} />}
        />
      </Routes>
      {hasCategories && <BottomNav />}
    </div>
  );
}
