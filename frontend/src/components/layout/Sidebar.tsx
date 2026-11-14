import { NavLink } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { navItems } from './navItems';
import { useEditorStore } from '../../store/useEditorStore';

export default function Sidebar() {
  const sidebarCollapsed = useEditorStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);

  return (
    <aside
      className={`sidebar${sidebarCollapsed ? ' sidebar--collapsed' : ''}`}
      aria-label="Main Navigation"
    >
      <div className="sidebar__brand">
        <div className="sidebar__brand-mark" title="MYNEST">
          M
        </div>
        <div className="sidebar__brand-text">
          <span className="sidebar__brand-name">MYNEST</span>
          <span className="sidebar__brand-sub">Design Studio</span>
        </div>
        <button
          type="button"
          className="sidebar__toggle"
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={sidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'}
        >
          {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <nav className="sidebar__nav">
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) => (isActive ? 'nav-item nav-item--active' : 'nav-item')}
            title={sidebarCollapsed ? label : undefined}
          >
            <Icon className="nav-item__icon" size={18} />
            <span className="nav-item__label">{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__user" title={sidebarCollapsed ? 'MyNest Team · Interior Design' : undefined}>
        <div className="avatar">MT</div>
        <div className="sidebar__user-meta">
          <span className="sidebar__user-name">MyNest Team</span>
          <span className="sidebar__user-role">Interior Design</span>
        </div>
      </div>
    </aside>
  );
}
