import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import { useEditorStore } from '../../store/useEditorStore';

export default function AppShell() {
  const sidebarCollapsed = useEditorStore((s) => s.sidebarCollapsed);
  const zenMode = useEditorStore((s) => s.zenMode);

  return (
    <div
      className={`app-layout${sidebarCollapsed ? ' app-layout--collapsed' : ''}${
        zenMode ? ' app-layout--zen' : ''
      }`}
    >
      <Sidebar />
      <div className="app-main">
        <Header />
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
