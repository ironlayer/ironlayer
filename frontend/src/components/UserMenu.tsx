import { useState, useRef, useEffect } from 'react';
import { LogOut, ChevronDown } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

/**
 * Dropdown menu showing the current user's name, role badge, and logout.
 * Placed in the top-right of the Layout header.
 */
export default function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click.
  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  if (!user) return null;

  const initials = user.display_name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-300 transition-colors hover:bg-white/5"
      >
        {/* Avatar */}
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ironlayer-500/15 text-xs font-semibold text-ironlayer-400">
          {initials}
        </span>
        <span className="hidden sm:inline">{user.display_name}</span>
        <ChevronDown className="h-3.5 w-3.5 text-gray-500" />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-1 w-56 origin-top-right rounded-lg border border-white/[0.06] bg-surface-100 shadow-lg shadow-black/40">
          <div className="border-b border-white/[0.06] px-4 py-3">
            <p className="text-sm font-medium text-white">{user.display_name}</p>
            <p className="truncate text-xs text-gray-500">{user.email}</p>
            <span className="mt-1 inline-flex items-center rounded-full bg-ironlayer-500/10 border border-ironlayer-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ironlayer-400">
              {user.role}
            </span>
          </div>
          <div className="py-1">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                logout();
              }}
              className="flex w-full items-center gap-2 px-4 py-2 text-sm text-gray-400 hover:bg-white/5 hover:text-white transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
