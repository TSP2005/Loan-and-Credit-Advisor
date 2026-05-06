import { useState, useRef, useEffect } from 'react';
import { apiPost, sendLog } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

const OTP_LENGTH = 6;
const RESEND_COOLDOWN = 60; // seconds

export default function LoginPage() {
  const [isSignup, setIsSignup] = useState(false);
  // step: 'form' | 'otp'
  const [step, setStep] = useState('form');
  const [form, setForm] = useState({ username: '', password: '', full_name: '', email: '' });
  const [otp, setOtp] = useState(Array(OTP_LENGTH).fill(''));
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [resendCountdown, setResendCountdown] = useState(0);
  const otpRefs = useRef([]);
  const { login } = useAuth();
  const navigate = useNavigate();

  // Countdown timer for resend
  useEffect(() => {
    if (resendCountdown <= 0) return;
    const t = setTimeout(() => setResendCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCountdown]);

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  // ── Step 1: Submit signup form → send OTP ──────────────────────────────────
  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    sendLog('info', 'LoginPage', 'SIGNUP_ATTEMPT', `username=${form.username}`);
    try {
      await apiPost('/auth/signup', {
        username: form.username,
        password: form.password,
        full_name: form.full_name,
        email: form.email,
      });
      setStep('otp');
      setResendCountdown(RESEND_COOLDOWN);
      sendLog('info', 'LoginPage', 'OTP_SENT', `email=${form.email}`);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  };

  // ── Step 2: Verify OTP ────────────────────────────────────────────────────
  const handleOtpSubmit = async (submittedOtp) => {
    const code = submittedOtp || otp.join('');
    if (code.length !== OTP_LENGTH) return;
    setError('');
    setLoading(true);
    sendLog('info', 'LoginPage', 'OTP_VERIFY_ATTEMPT', `email=${form.email}`);
    try {
      const data = await apiPost('/auth/verify-otp', {
        email: form.email.toLowerCase(),
        otp: code,
      });
      login(
        { user_id: data.user_id, username: data.username, full_name: data.full_name },
        data.access_token
      );
      sendLog('info', 'LoginPage', 'OTP_VERIFIED', `user_id=${data.user_id}`);
      navigate('/dashboard');
    } catch (err) {
      setError(err.message);
      // Clear OTP on error
      setOtp(Array(OTP_LENGTH).fill(''));
      otpRefs.current[0]?.focus();
    }
    setLoading(false);
  };

  // ── Login (existing users) ────────────────────────────────────────────────
  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    sendLog('info', 'LoginPage', 'LOGIN_ATTEMPT', `username=${form.username}`);
    try {
      const data = await apiPost('/auth/login', {
        username: form.username,
        password: form.password,
      });
      login(
        { user_id: data.user_id, username: data.username, full_name: data.full_name },
        data.access_token
      );
      sendLog('info', 'LoginPage', 'LOGIN_SUCCESS', `user_id=${data.user_id}`);
      navigate('/dashboard');
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  };

  // ── OTP digit handlers ────────────────────────────────────────────────────
  const handleOtpChange = (idx, val) => {
    if (!/^\d?$/.test(val)) return;
    const next = [...otp];
    next[idx] = val;
    setOtp(next);
    if (val && idx < OTP_LENGTH - 1) otpRefs.current[idx + 1]?.focus();
    if (next.every(d => d !== '')) handleOtpSubmit(next.join(''));
  };

  const handleOtpKeyDown = (idx, e) => {
    if (e.key === 'Backspace' && !otp[idx] && idx > 0) {
      otpRefs.current[idx - 1]?.focus();
    }
  };

  const handleResend = async () => {
    setError('');
    try {
      await apiPost('/auth/resend-otp', { email: form.email.toLowerCase() });
      setResendCountdown(RESEND_COOLDOWN);
      setOtp(Array(OTP_LENGTH).fill(''));
      otpRefs.current[0]?.focus();
    } catch (err) {
      setError(err.message);
    }
  };

  const switchMode = () => {
    setIsSignup(!isSignup);
    setStep('form');
    setError('');
    setOtp(Array(OTP_LENGTH).fill(''));
  };

  // ── OTP Entry Screen ───────────────────────────────────────────────────────
  if (step === 'otp') {
    return (
      <div className="auth-page">
        <div className="auth-container">
          <div className="auth-header">
            <span className="logo">📧</span>
            <h1>Check your email</h1>
            <p>We sent a 6-digit code to <strong>{form.email}</strong></p>
          </div>
          <div className="glass-card">
            {error && <div className="error-message" id="otp-error">{error}</div>}

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', margin: '24px 0' }}>
              {otp.map((digit, idx) => (
                <input
                  key={idx}
                  ref={el => otpRefs.current[idx] = el}
                  id={`otp-digit-${idx}`}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={e => handleOtpChange(idx, e.target.value)}
                  onKeyDown={e => handleOtpKeyDown(idx, e)}
                  autoFocus={idx === 0}
                  style={{
                    width: '48px', height: '56px',
                    textAlign: 'center', fontSize: '1.5rem', fontWeight: 700,
                    background: 'rgba(99,102,241,0.1)',
                    border: `2px solid ${digit ? '#6366f1' : 'rgba(99,102,241,0.3)'}`,
                    borderRadius: '12px', color: '#e0e7ff',
                    outline: 'none', transition: 'border-color 0.2s',
                  }}
                />
              ))}
            </div>

            <button
              className="btn btn-primary btn-lg"
              disabled={loading || otp.some(d => !d)}
              onClick={() => handleOtpSubmit()}
              id="otp-verify-btn"
              style={{ width: '100%' }}
            >
              {loading ? '⏳ Verifying...' : '✅ Verify & Create Account'}
            </button>

            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              {resendCountdown > 0 ? (
                <p style={{ color: 'rgba(199,210,254,0.5)', fontSize: '0.85rem' }}>
                  Resend code in <strong>{resendCountdown}s</strong>
                </p>
              ) : (
                <button
                  onClick={handleResend}
                  id="otp-resend-btn"
                  style={{
                    background: 'none', border: 'none',
                    color: '#818cf8', cursor: 'pointer',
                    fontSize: '0.88rem', textDecoration: 'underline',
                  }}
                >
                  🔄 Resend code
                </button>
              )}
              <button
                onClick={() => { setStep('form'); setError(''); }}
                style={{
                  background: 'none', border: 'none',
                  color: 'rgba(199,210,254,0.4)', cursor: 'pointer',
                  fontSize: '0.8rem', display: 'block', margin: '8px auto 0',
                }}
              >
                ← Back to signup
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Signup / Login Form ────────────────────────────────────────────────────
  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-header">
          <span className="logo">🏦</span>
          <h1>AI Loan &amp; Credit Advisor</h1>
          <p>Your intelligent financial advisory companion</p>
        </div>

        <div className="glass-card">
          <form
            className="auth-form"
            onSubmit={isSignup ? handleSignupSubmit : handleLoginSubmit}
            id="auth-form"
          >
            {error && <div className="error-message" id="auth-error">{error}</div>}

            {isSignup && (
              <>
                <div className="input-group">
                  <label htmlFor="full_name">Full Name</label>
                  <input id="full_name" name="full_name" className="input-field" type="text"
                    placeholder="Enter your full name" value={form.full_name}
                    onChange={handleChange} required />
                </div>
                <div className="input-group">
                  <label htmlFor="email">Email</label>
                  <input id="email" name="email" className="input-field" type="email"
                    placeholder="you@example.com" value={form.email}
                    onChange={handleChange} required />
                </div>
              </>
            )}

            <div className="input-group">
              <label htmlFor="username">Username</label>
              <input id="username" name="username" className="input-field" type="text"
                placeholder="Choose a username" value={form.username}
                onChange={handleChange} required />
            </div>
            <div className="input-group">
              <label htmlFor="password">Password</label>
              <input id="password" name="password" className="input-field" type="password"
                placeholder="Enter password" value={form.password}
                onChange={handleChange} required minLength={6} />
            </div>

            <button type="submit" className="btn btn-primary btn-lg"
              disabled={loading} id="auth-submit">
              {loading
                ? '⏳ Please wait...'
                : isSignup
                  ? '📧 Send Verification Code'
                  : '🔐 Sign In'}
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
            <button onClick={switchMode} id="toggle-auth">
              {isSignup ? 'Sign In' : 'Sign Up'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
