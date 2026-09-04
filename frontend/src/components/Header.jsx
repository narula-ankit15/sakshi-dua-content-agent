export default function Header() {
  return (
    <header className="app-header">
      <div className="app-header__left">
        <button className="app-header__back" aria-label="Back">
          &#8249;
        </button>
        <h1 className="app-header__title">Workshop Content</h1>
      </div>
      <div className="app-header__right">
        <span className="app-header__instance">
          Demo Instance <span className="app-header__caret">&#9662;</span>
        </span>
      </div>
    </header>
  );
}
