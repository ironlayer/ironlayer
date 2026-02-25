import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { setAuthToken, setLogoutHandler } from '../api/client';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface User {
  id: string;
  email: string;
  display_name: string;
  role: string;
  tenant_id: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
}

/* ------------------------------------------------------------------ */
/* API helpers (inline to avoid circular imports)                       */
/* ------------------------------------------------------------------ */

const BASE_URL = (import.meta.env.VITE_API_URL ?? '') + '/api/v1';

function getCsrfToken(): string {
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : '';
}

async function authRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    ...options,
    credentials: 'include', // Always send cookies for auth endpoints.
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': getCsrfToken(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail ?? 'Authentication failed');
  }
  return resp.json() as Promise<T>;
}

interface TokenResponse {
  access_token: string;
  user: User;
  tenant_id: string;
}

interface SessionResponse {
  access_token: string;
  user: User;
  tenant_id: string;
}

/* ------------------------------------------------------------------ */
/* Context                                                             */
/* ------------------------------------------------------------------ */

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isAuthenticated: false,
    isLoading: true, // Start as loading — we'll try to restore the session.
  });

  // Guard against double-mount in StrictMode calling restore twice.
  const sessionRestoreAttempted = useRef(false);

  // Sync auth token to the API client whenever it changes.
  useEffect(() => {
    setAuthToken(state.accessToken);
  }, [state.accessToken]);

  // On mount, attempt to restore the session from the HttpOnly cookie.
  useEffect(() => {
    if (sessionRestoreAttempted.current) return;
    sessionRestoreAttempted.current = true;

    let cancelled = false;

    (async () => {
      try {
        const data = await authRequest<SessionResponse>('/auth/session', {
          method: 'GET',
        });
        if (!cancelled) {
          setAuthToken(data.access_token);
          setState({
            user: data.user,
            accessToken: data.access_token,
            isAuthenticated: true,
            isLoading: false,
          });
        }
      } catch {
        // No valid refresh cookie — user is not authenticated.
        if (!cancelled) {
          setState({
            user: null,
            accessToken: null,
            isAuthenticated: false,
            isLoading: false,
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await authRequest<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setAuthToken(data.access_token);
    setState({
      user: data.user,
      accessToken: data.access_token,
      isAuthenticated: true,
      isLoading: false,
    });
  }, []);

  const signup = useCallback(async (email: string, password: string, displayName: string) => {
    const data = await authRequest<TokenResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        display_name: displayName,
      }),
    });
    setAuthToken(data.access_token);
    setState({
      user: data.user,
      accessToken: data.access_token,
      isAuthenticated: true,
      isLoading: false,
    });
  }, []);

  const logout = useCallback(async () => {
    // Call the backend to clear the refresh cookie.
    try {
      await authRequest<unknown>('/auth/logout', { method: 'POST' });
    } catch {
      // Best-effort — clear local state regardless.
    }
    setAuthToken(null);
    setState({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,
    });
  }, []);

  // Register/deregister the logout handler so the API client can force
  // a logout when an unrecoverable 401 occurs (e.g. expired refresh token).
  useEffect(() => {
    const handler = () => {
      setAuthToken(null);
      setState({
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isLoading: false,
      });
    };
    setLogoutHandler(handler);
    return () => setLogoutHandler(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, signup, logout }),
    [state, login, signup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an <AuthProvider>');
  }
  return ctx;
}
