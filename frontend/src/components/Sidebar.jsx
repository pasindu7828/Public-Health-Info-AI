import { NavLink } from "react-router-dom";
import "../styles/sidebar.css";

const NAV_ITEMS = [
  { label: "Dashboard", path: "/dashboard" },
  { label: "Chat", path: "/chat" },
  { label: "Graph", path: "/generate" },
  { label: "Search", path: "/search" },
  { label: "Home", path: "/" },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__logo">
        <img src="/logo.png" alt="Health Bridge logo" />
      </div>

      <nav className="sidebar__nav">
        {NAV_ITEMS.map(({ label, path }) => (
          <NavLink
            key={label}
            to={path}
            className={({ isActive }) =>
              `sidebar__btn ${isActive ? "sidebar__btn--active" : ""}`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
