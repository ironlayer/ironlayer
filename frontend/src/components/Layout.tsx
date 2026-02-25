import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  GitBranch,
  Database,
  Globe,
  RotateCcw,
  Box,
  BarChart2,
  CreditCard,
  Settings,
  Shield,
  FileBarChart,
} from 'lucide-react';
import UserMenu from './UserMenu';
import { useAuth } from '../contexts/AuthContext';

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/models', label: 'Models', icon: Database },
  { to: '/environments', label: 'Environments', icon: Globe },
  { to: '/backfills', label: 'Backfills', icon: RotateCcw },
  { to: '/usage', label: 'Usage', icon: BarChart2 },
  { to: '/billing', label: 'Billing', icon: CreditCard },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/admin', label: 'Admin', icon: Shield, adminOnly: true },
  { to: '/admin/reports', label: 'Reports', icon: FileBarChart, adminOnly: true },
];

function Layout() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const visibleItems = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      {/* Sidebar */}
      <aside className="flex w-60 flex-col border-r border-white/[0.06] bg-surface-50">
        {/* Logo */}
        <div className="flex h-16 items-center gap-2.5 border-b border-white/[0.06] px-5">
          <Box className="h-7 w-7 text-ironlayer-500" />
          <span className="text-lg font-bold tracking-tight text-white">
            IronLayer
          </span>
        </div>

        {/* Navigation */}
        <nav aria-label="Main navigation" className="flex-1 space-y-1 px-3 py-4">
          {visibleItems.map(({ to, label, icon: Icon, adminOnly }, idx) => (
            <div key={to}>
              {/* Admin separator */}
              {adminOnly && idx > 0 && !visibleItems[idx - 1].adminOnly && (
                <div className="my-3 border-t border-white/[0.06] pt-2">
                  <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
                    Admin
                  </p>
                </div>
              )}
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-ironlayer-500/10 text-ironlayer-400 border border-ironlayer-500/20'
                      : 'text-gray-400 hover:bg-white/5 hover:text-white border border-transparent'
                  }`
                }
              >
                <Icon className="h-4.5 w-4.5 shrink-0" size={18} />
                {label}
              </NavLink>
            </div>
          ))}
        </nav>

        {/* Environment badge */}
        <div className="border-t border-white/[0.06] px-5 py-3">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <GitBranch className="h-3.5 w-3.5" size={14} />
            <span className="font-medium">
              {import.meta.env.VITE_ENVIRONMENT ?? 'development'}
            </span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.06] bg-surface-50 px-6">
          <h1 className="text-sm font-medium text-gray-500">
            Data Transformation Control Plane
          </h1>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center rounded-full bg-ironlayer-500/10 border border-ironlayer-500/20 px-2.5 py-0.5 text-xs font-medium text-ironlayer-400">
              v{import.meta.env.VITE_APP_VERSION ?? '0.1.0'}
            </span>
            <UserMenu />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-surface p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default Layout;
