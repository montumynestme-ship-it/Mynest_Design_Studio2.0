import { NavLink } from 'react-router-dom';
import { navItems } from './navItems';

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__brand-mark">M</div>
        <div className="sidebar__brand-text">
          <span className="sidebar__brand-name">MYNEST</span>
          <span className="sidebar__brand-sub">Design Studio</span>
        </div>
      </div>

      <nav className="sidebar__nav">
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) => (isActive ? 'nav-item nav-item--active' : 'nav-item')}
          >
            <Icon className="nav-item__icon" size={18} />
            <span className="nav-item__label">{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__user">
        <div className="avatar">MT</div>
        <div className="sidebar__user-meta">
          <span className="sidebar__user-name">MyNest Team</span>
          <span className="sidebar__user-role">Interior Design</span>
        </div>
      </div>
    </aside>
  );
}
