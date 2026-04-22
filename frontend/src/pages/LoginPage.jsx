import { useState } from 'react';
import { apiPost, sendLog } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function LoginPage() {
  const [isSignup, setIsSignup] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', full_name: '', email: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const endpoint = isSignup ? '/auth/signup' : '/auth/login';
    const body = isSignup
      ? { username: form.username, password: form.password, full_name: form.full_name, email: form.email }
      : { username: form.username, password: form.password };

    sendLog('info', 'LoginPage', isSignup ? 'SIGNUP_ATTEMPT' : 'LOGIN_ATTEMPT', `username=${form.username}`);

    try {
      const data = await apiPost(endpoint, body);
      login(
        { user_id: data.user_id, username: data.username, full_name: data.full_name },
        data.access_token
      );
      sendLog('info', 'LoginPage', isSignup ? 'SIGNUP_SUCCESS' : 'LOGIN_SUCCESS', `user_id=${data.user_id}`);
      navigate('/dashboard');
    } catch (err) {
      setError(err.message);
      sendLog('warning', 'LoginPage', isSignup ? 'SIGNUP_FAILED' : 'LOGIN_FAILED', err.message);
    }
    setLoading(false);
  };

  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-header">
          <span className="logo">🏦</span>
          <h1>AI Loan & Credit Advisor</h1>
          <p>Your intelligent financial advisory companion</p>
        </div>

        <div className="glass-card">
          <form className="auth-form" onSubmit={handleSubmit} id="auth-form">
            {error && <div className="error-message" id="auth-error">{error}</div>}

            {isSignup && (
              <>
                <div className="input-group">
                  <label htmlFor="full_name">Full Name</label>
                  <input id="full_name" name="full_name" className="input-field" type="text"
                    placeholder="Enter your full name" value={form.full_name} onChange={handleChange} required />
                </div>
                <div className="input-group">
                  <label htmlFor="email">Email</label>
                  <input id="email" name="email" className="input-field" type="email"
                    placeholder="you@example.com" value={form.email} onChange={handleChange} required />
                </div>
              </>
            )}

            <div className="input-group">
              <label htmlFor="username">Username</label>
              <input id="username" name="username" className="input-field" type="text"
                placeholder="Choose a username" value={form.username} onChange={handleChange} required />
            </div>
            <div className="input-group">
              <label htmlFor="password">Password</label>
              <input id="password" name="password" className="input-field" type="password"
                placeholder="Enter password" value={form.password} onChange={handleChange} required minLength={6} />
            </div>

            <button type="submit" className="btn btn-primary btn-lg" disabled={loading} id="auth-submit">
              {loading ? '⏳ Please wait...' : isSignup ? '🚀 Create Account' : '🔐 Sign In'}
            </button>
          </form>

          <div className="auth-divider">or</div>

          <button className="btn btn-secondary" style={{ width: '100%' }}
            onClick={() => { sendLog('info', 'LoginPage', 'GUEST_MODE', ''); navigate('/guest'); }}
            id="guest-mode-btn">
            👤 Continue as Guest
          </button>

          <div className="auth-toggle">
            {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button onClick={() => { setIsSignup(!isSignup); setError(''); }} id="toggle-auth">
              {isSignup ? 'Sign In' : 'Sign Up'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
