import { createContext, useContext, useState, useEffect } from 'react';
import { sendLog } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Restore session from localStorage
    const saved = localStorage.getItem('loan_advisor_auth');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setUser(parsed.user);
        setToken(parsed.token);
        sendLog('info', 'AuthContext', 'SESSION_RESTORED', `user=${parsed.user?.username}`);
      } catch (e) {
        localStorage.removeItem('loan_advisor_auth');
      }
    }
    setLoading(false);
  }, []);

  const login = (userData, accessToken) => {
    setUser(userData);
    setToken(accessToken);
    localStorage.setItem('loan_advisor_auth', JSON.stringify({ user: userData, token: accessToken }));
    sendLog('info', 'AuthContext', 'LOGIN', `user=${userData.username}`);
  };

  const logout = () => {
    sendLog('info', 'AuthContext', 'LOGOUT', `user=${user?.username}`);
    setUser(null);
    setToken(null);
    localStorage.removeItem('loan_advisor_auth');
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
