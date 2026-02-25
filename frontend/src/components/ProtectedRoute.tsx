import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Route guard that redirects unauthenticated users to /login.
 *
 * Wraps child routes in an `<Outlet />` so it works as a layout route
 * in react-router:
 *
 *   <Route element={<ProtectedRoute />}>
 *     <Route element={<Layout />}>
 *       ...
 *     </Route>
 *   </Route>
 */
export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-ironlayer-200 border-t-ironlayer-600" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
