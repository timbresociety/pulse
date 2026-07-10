import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Login from "./screens/Login.jsx";
import Categories from "./screens/Categories.jsx";
import Feed from "./screens/Feed.jsx";
import History from "./screens/History.jsx";
import Leaderboard from "./screens/Leaderboard.jsx";
import Profile from "./screens/Profile.jsx";
import Wallet from "./screens/Wallet.jsx";
import Username from "./screens/Username.jsx";
import AdminCreateMarket from "./screens/AdminCreateMarket.jsx";

function BottomNav({ isAdmin }) {
  const items = [
    ["/feed", "F", "Feed"],
    ["/reveals", "R", "Reveals"],
    ["/wallet", "W", "Wallet"],
    ["/social", "S", "Social"],
    ["/profile", "P", "Profile"],
  ];
  if (isAdmin) items.splice(4, 0, ["/create", "+", "Create"]);

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

  if (loading) return <div className="app"><div className="empty">Loading Psyblr...</div></div>;
  if (!user) return <div className="app"><Login /></div>;
  if (!user.username) {
    return (
      <div className="app">
        <Routes>
          <Route path="/welcome" element={<Username />} />
          <Route path="*" element={<Navigate to="/welcome" replace />} />
        </Routes>
      </div>
    );
  }

  const hasCategories = user.categories && user.categories.length > 0;

  return (
    <div className="app">
      <Routes>
        <Route path="/categories" element={<Categories />} />
        <Route path="/feed" element={hasCategories ? <Feed /> : <Navigate to="/categories" />} />
        <Route path="/reveals" element={<History />} />
        <Route path="/history" element={<Navigate to="/reveals" />} />
        <Route path="/wallet" element={<Wallet />} />
        <Route path="/social" element={<Leaderboard />} />
        <Route path="/leaderboard" element={<Navigate to="/social" />} />
        <Route path="/profile" element={<Profile />} />
        {user.is_admin && <Route path="/create" element={<AdminCreateMarket />} />}
        <Route path="*" element={<Navigate to={hasCategories ? "/feed" : "/categories"} />} />
      </Routes>
      {hasCategories && <BottomNav isAdmin={user.is_admin} />}
    </div>
  );
}
