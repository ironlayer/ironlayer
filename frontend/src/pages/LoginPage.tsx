import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Box, AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(email, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center">
          <Box className="h-10 w-10 text-ironlayer-500" />
          <h1 className="mt-3 text-2xl font-bold text-white">IronLayer</h1>
          <p className="mt-1 text-sm text-gray-500">
            Sign in to your account
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-300">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-describedby="email-hint"
              className="mt-1 block w-full rounded-lg border border-white/[0.1] bg-surface-100 px-3 py-2 text-sm text-gray-100 shadow-sm placeholder:text-gray-600 focus:border-ironlayer-500/60 focus:outline-none focus:ring-1 focus:ring-ironlayer-500/30"
              placeholder="you@example.com"
            />
            <span id="email-hint" className="sr-only">Enter your account email address</span>
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-300">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby="password-hint"
              className="mt-1 block w-full rounded-lg border border-white/[0.1] bg-surface-100 px-3 py-2 text-sm text-gray-100 shadow-sm placeholder:text-gray-600 focus:border-ironlayer-500/60 focus:outline-none focus:ring-1 focus:ring-ironlayer-500/30"
              placeholder="********"
            />
            <span id="password-hint" className="sr-only">Enter your account password</span>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-ironlayer-500 to-ironlayer-600 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-ironlayer-500/25 transition-all hover:shadow-ironlayer-500/40 hover:from-ironlayer-400 hover:to-ironlayer-500 disabled:opacity-50"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-gray-500">
          Don&apos;t have an account?{' '}
          <Link to="/signup" className="font-medium text-ironlayer-400 hover:text-ironlayer-300">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
