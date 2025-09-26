import "../styles/header.css";

function formatToday() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}.${m}.${day}`; // e.g., 2025.08.25
}

export default function Header() {
  const today = formatToday();

  return (
    <header className="header">
      <div className="header__title">Public Health Info AI</div>

      <label className="header__search" aria-label="Search">
        {/* search icon */}
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M21 21l-4.3-4.3M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15z"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <input type="search" placeholder="Search" />
      </label>

      <div className="header__date">{today}</div>

      <div className="header__avatar" title="Profile" aria-label="Profile" />
    </header>
  );
}
