import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Login from "./screens/Login.jsx";
import Categories from "./screens/Categories.jsx";
import Feed from "./screens/Feed.jsx";
import Leaderboard from "./screens/Leaderboard.jsx";
import Profile from "./screens/Profile.jsx";

function BottomNav() {
  return (
    <nav className="bottomnav">
      <NavLink to="/feed" className={({ isActive }) => (isActive ? "active" : "")}>Feed</NavLink>
      <NavLink to="/leaderboard" className={({ isActive }) => (isActive ? "active" : "")}>Leaderboard</NavLink>
      <NavLink to="/profile" className={({ isActive }) => (isActive ? "active" : "")}>Profile</NavLink>
    </nav>
  );
}

export default function App() {
  const { user, loading } = useAuth();

  if (loading) return <div className="app"><div className="empty">Loading…</div></div>;
  if (!user) return <div className="app"><Login /></div>;

  // Force category selection before play.
  const hasCategories = user.categories && user.categories.length > 0;

  return (
    <div className="app">
      <Routes>
        <Route path="/categories" element={<Categories />} />
        <Route path="/feed" element={hasCategories ? <Feed /> : <Navigate to="/categories" />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="*" element={<Navigate to={hasCategories ? "/feed" : "/categories"} />} />
      </Routes>
      {hasCategories && <BottomNav />}
    </div>
  );
}
