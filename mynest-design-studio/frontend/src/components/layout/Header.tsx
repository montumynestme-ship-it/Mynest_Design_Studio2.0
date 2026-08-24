import { Bell } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { navItems } from './navItems';

export default function Header() {
  const { pathname } = useLocation();
  const current = navItems.find((item) => pathname.startsWith(item.path));
  const sectionName = current?.label ?? 'Dashboard';

  return (
    <header className="app-header">
      <div className="app-header__left">
        <h1 className="app-header__section">{sectionName}</h1>
        <span className="app-header__label">MYNEST DESIGN STUDIO</span>
      </div>

      <div className="app-header__right">
        <button className="icon-button" type="button" aria-label="Notifications">
          <Bell size={18} />
        </button>

        <div className="app-header__profile">
          <div className="avatar">MT</div>
          <div className="app-header__profile-meta">
            <span className="app-header__profile-name">MyNest Team</span>
            <span className="app-header__profile-role">Interior Design</span>
          </div>
        </div>
      </div>
    </header>
  );
}
