import { LayoutDashboard, PencilRuler, type LucideIcon } from 'lucide-react';

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

/** Single source of truth for sidebar navigation and header section names. */
export const navItems: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/design-studio', label: 'Design Studio', icon: PencilRuler },
];
