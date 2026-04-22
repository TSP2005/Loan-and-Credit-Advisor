import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { apiGet, apiPost, sendLog } from '../api/client';
import ChatPanel from '../components/ChatPanel';
import CreditGauge from '../components/CreditGauge';
import EMICalculator from '../components/EMICalculator';
import DocumentUpload from '../components/DocumentUpload';

export default function DashboardPage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [activeTab, setActiveTab] = useState('chat');
  const [profileForm, setProfileForm] = useState({
    annual_income: '', credit_score: '', employment_months: '',
    existing_loans: '', existing_emi_amount: '', credit_utilization: '',
    city: '', age: '', loan_type_interest: 'home_loan', requested_amount: '', requested_tenure_months: ''
  });
  const [profileMsg, setProfileMsg] = useState('');

  // Profile popup state
  const [profilePopupOpen, setProfilePopupOpen] = useState(false);
  const popupRef = useRef(null);

  // Chat Sessions
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [sessionToDelete, setSessionToDelete] = useState(null);

  useEffect(() => {
    if (user && token) {
      loadProfile();
      loadSessions();
    }
  }, [user, token]);

  // Close popup when clicking outside
  useEffect(() => {
    const handler = (e) => {
      if (popupRef.current && !popupRef.current.contains(e.target)) {
        setProfilePopupOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const loadProfile = async () => {
    try {
      const data = await apiGet(`/profile/${user.user_id}`, token);
      setProfile(data.profile);
      const p = data.profile;
      setProfileForm({
        annual_income: p.annual_income || '', credit_score: p.credit_score || '',
        employment_months: p.employment_months || '', existing_loans: p.existing_loans || '',
        existing_emi_amount: p.existing_emi_amount || '', credit_utilization: p.credit_utilization || '',
        city: p.city || '', age: p.age || '',
        loan_type_interest: p.loan_type_interest || 'home_loan',
        requested_amount: p.requested_amount || '', requested_tenure_months: p.requested_tenure_months || ''
      });
      sendLog('info', 'Dashboard', 'PROFILE_LOADED', `user_id=${user.user_id} complete=${p.profile_complete}`);
    } catch (err) {
      sendLog('error', 'Dashboard', 'PROFILE_LOAD_FAILED', err.message);
    }
  };

  const loadSessions = async () => {
    try {
      const data = await apiGet(`/chat/sessions/${user.user_id}`, token);
      const fetchedSessions = data.sessions || [];
      setSessions(fetchedSessions);
      // Auto-create a first session if none exist
      if (fetchedSessions.length === 0) {
        await createNewSession(true);
      } else {
        setActiveSessionId(fetchedSessions[0].session_id);
      }
    } catch (err) {
      sendLog('error', 'Dashboard', 'SESSIONS_LOAD_FAILED', err.message);
    }
  };

  const createNewSession = async (silent = false) => {
    try {
      const data = await apiPost(`/chat/sessions/${user.user_id}`, { title: 'New Chat' }, token);
      const newSession = data.session;
      setSessions(prev => [newSession, ...prev]);
      setActiveSessionId(newSession.session_id);
      if (!silent) setActiveTab('chat');
      return newSession;
    } catch (err) {
      sendLog('error', 'Dashboard', 'SESSION_CREATE_FAILED', err.message);
    }
  };

  const initiateDeleteSession = (sessionId, e) => {
    e.stopPropagation();
    setSessionToDelete(sessionId);
  };

  const confirmDeleteSession = async () => {
    if (!sessionToDelete) return;
    try {
      await fetch(`http://localhost:8000/chat/sessions/${user.user_id}/${sessionToDelete}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      setSessions(prev => {
        const remaining = prev.filter(s => s.session_id !== sessionToDelete);
        if (activeSessionId === sessionToDelete) {
          setActiveSessionId(remaining.length > 0 ? remaining[0].session_id : null);
        }
        return remaining;
      });
      setSessionToDelete(null);
    } catch (err) {
      sendLog('error', 'Dashboard', 'SESSION_DELETE_FAILED', err.message);
    }
  };

  const saveProfile = async (e) => {
    e.preventDefault();
    setProfileMsg('');
    try {
      const body = {};
      for (const [k, v] of Object.entries(profileForm)) {
        if (v !== '' && v !== null && v !== undefined) {
          body[k] = ['annual_income', 'existing_emi_amount', 'credit_utilization', 'requested_amount'].includes(k)
            ? parseFloat(v) : ['credit_score', 'employment_months', 'existing_loans', 'age', 'requested_tenure_months'].includes(k)
            ? parseInt(v) : v;
        }
      }
      await apiPost('/profile/update', body, token);
      setProfileMsg('✅ Profile saved!');
      loadProfile();
      sendLog('info', 'Dashboard', 'PROFILE_SAVED', `fields=${Object.keys(body).join(',')}`);
    } catch (err) {
      setProfileMsg('❌ ' + err.message);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const riskTier = profile?.risk_tier || (profile?.credit_score >= 750 ? 'Low' : profile?.credit_score >= 650 ? 'Medium' : 'High');

  const formatSessionDate = (iso) => {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1rem' }}>👤 {user?.full_name}</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>@{user?.username}</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={handleLogout} id="logout-btn">Logout</button>
        </div>

        {/* Credit Gauge */}
        {profile?.credit_score > 0 && (
          <div className="glass-card" style={{ padding: 'var(--spacing-md)' }}>
            <CreditGauge score={profile.credit_score} />
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 'var(--spacing-sm)' }}>
              <span className={`risk-badge ${riskTier.toLowerCase()}`}>
                {riskTier === 'Low' ? '🟢' : riskTier === 'Medium' ? '🟡' : '🔴'} {riskTier} Risk
              </span>
            </div>
          </div>
        )}

        {/* Tab buttons */}
        <div className="tab-bar">
          <button className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}>💬 Chat</button>
          <button className={`tab-btn ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}>📝 Profile</button>
          <button className={`tab-btn ${activeTab === 'tools' ? 'active' : ''}`}
            onClick={() => setActiveTab('tools')}>🔧 Tools</button>
        </div>

        {/* Chat Sessions List */}
        {activeTab === 'chat' && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '6px', overflow: 'hidden' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 2px' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Chats</span>
              <button
                id="new-chat-btn"
                onClick={() => createNewSession()}
                style={{
                  background: 'var(--primary)',
                  border: 'none',
                  borderRadius: '6px',
                  color: '#fff',
                  padding: '3px 10px',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontWeight: 600
                }}
              >
                ＋ New
              </button>
            </div>

            <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
              {sessions.length === 0 && (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', padding: '8px 4px' }}>
                  No chats yet. Click "＋ New" to start.
                </div>
              )}
              {sessions.map(s => (
                <div
                  key={s.session_id}
                  onClick={() => { setActiveSessionId(s.session_id); setActiveTab('chat'); }}
                  style={{
                    borderRadius: '8px',
                    padding: '8px 10px',
                    cursor: 'pointer',
                    background: activeSessionId === s.session_id
                      ? 'rgba(99,102,241,0.25)'
                      : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${activeSessionId === s.session_id ? 'var(--primary)' : 'rgba(255,255,255,0.06)'}`,
                    transition: 'all 0.15s',
                    position: 'relative',
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: '6px',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      color: activeSessionId === s.session_id ? '#fff' : 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      💬 {s.title}
                    </div>
                    {s.last_message && (
                      <div style={{
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        marginTop: '2px'
                      }}>
                        {s.last_message}
                      </div>
                    )}
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '3px' }}>
                      {formatSessionDate(s.last_updated || s.created_at)}
                    </div>
                  </div>
                  <button
                    onClick={(e) => initiateDeleteSession(s.session_id, e)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '0.9rem',
                      padding: '0 2px',
                      lineHeight: 1,
                      opacity: 0.5,
                      flexShrink: 0,
                    }}
                    title="Delete chat"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Quick actions for chat tab */}
        {activeTab === 'chat' && sessions.length > 0 && (
          <div className="quick-actions" style={{ marginTop: 'auto' }}>
            <button className="quick-action-btn" id="qa-eligibility">🏠 Check Eligibility</button>
            <button className="quick-action-btn" id="qa-pmay">📋 PMAY Info</button>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <div className="main-content">
        {/* Navbar */}
        <nav className="navbar">
          <div className="navbar-brand">
            <span className="logo-icon">🏦</span>
            <h1>AI Loan &amp; Credit Advisor</h1>
          </div>
          <div className="navbar-actions">
            {/* Profile popup badge */}
            <div ref={popupRef} style={{ position: 'relative' }}>
              <button
                id="profile-popup-btn"
                onClick={() => setProfilePopupOpen(v => !v)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '7px',
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: '20px',
                  padding: '5px 14px 5px 8px',
                  cursor: 'pointer',
                  color: 'var(--text-primary)',
                  fontSize: '0.88rem',
                  fontWeight: 600,
                  transition: 'all 0.2s',
                }}
              >
                <span className="status-dot online" style={{ width: 10, height: 10 }}></span>
                {user?.full_name}
                <span style={{ fontSize: '0.7rem', opacity: 0.6 }}>▾</span>
              </button>

              {/* Popup */}
              {profilePopupOpen && profile && (
                <div style={{
                  position: 'absolute',
                  top: 'calc(100% + 10px)',
                  right: 0,
                  width: 300,
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: '16px',
                  boxShadow: '0 12px 48px rgba(0,0,0,0.5)',
                  zIndex: 999,
                  overflow: 'hidden',
                  animation: 'fadeInDown 0.2s ease',
                }}>
                  {/* Header */}
                  <div style={{
                    background: 'linear-gradient(135deg, var(--primary), #a855f7)',
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px'
                  }}>
                    <div style={{
                      width: 44, height: 44,
                      borderRadius: '50%',
                      background: 'rgba(255,255,255,0.25)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '1.4rem',
                      flexShrink: 0
                    }}>👤</div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '1rem', color: '#fff' }}>{user?.full_name}</div>
                      <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)' }}>@{user?.username}</div>
                    </div>
                  </div>

                  {/* Stats grid */}
                  <div style={{ padding: '16px 20px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    {[
                      { label: 'Credit Score', value: profile.credit_score || '—', icon: '📊' },
                      { label: 'Annual Income', value: profile.annual_income ? `₹${(profile.annual_income/100000).toFixed(1)}L` : '—', icon: '💰' },
                      { label: 'Current EMI', value: profile.existing_emi_amount ? `₹${(profile.existing_emi_amount).toLocaleString()}` : '—', icon: '📅' },
                      { label: 'Existing Loans', value: profile.existing_loans ?? '—', icon: '🏦' },
                      { label: 'Employment', value: profile.employment_months ? `${profile.employment_months}mo` : '—', icon: '💼' },
                      { label: 'City', value: profile.city || '—', icon: '📍' },
                    ].map(stat => (
                      <div key={stat.label} style={{
                        background: 'rgba(255,255,255,0.04)',
                        borderRadius: '10px',
                        padding: '10px 12px',
                        border: '1px solid rgba(255,255,255,0.06)'
                      }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '3px' }}>{stat.icon} {stat.label}</div>
                        <div style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-primary)' }}>{stat.value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Risk + Status */}
                  <div style={{ padding: '0 20px 16px' }}>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <span className={`risk-badge ${riskTier.toLowerCase()}`} style={{ flex: 1, justifyContent: 'center', display: 'flex', padding: '6px' }}>
                        {riskTier === 'Low' ? '🟢' : riskTier === 'Medium' ? '🟡' : '🔴'} {riskTier} Risk
                      </span>
                      <span style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        borderRadius: '20px',
                        padding: '6px',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        background: profile.profile_complete ? 'rgba(34,197,94,0.15)' : 'rgba(234,179,8,0.15)',
                        color: profile.profile_complete ? 'var(--success)' : '#eab308',
                        border: `1px solid ${profile.profile_complete ? 'rgba(34,197,94,0.3)' : 'rgba(234,179,8,0.3)'}`
                      }}>
                        {profile.profile_complete ? '✅ Complete' : '⚠️ Incomplete'}
                      </span>
                    </div>

                    {/* Edit Profile shortcut */}
                    <button
                      onClick={() => { setActiveTab('profile'); setProfilePopupOpen(false); }}
                      className="btn btn-primary"
                      style={{ width: '100%', marginTop: '12px', padding: '8px' }}
                    >
                      ✏️ Edit Profile
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </nav>

        {/* Content based on active tab */}
        {activeTab === 'chat' && (
          <ChatPanel userId={user?.user_id} token={token} sessionId={activeSessionId} />
        )}

        {activeTab === 'profile' && (
          <div style={{ padding: 'var(--spacing-xl)', maxWidth: 1000, margin: '0 auto', display: 'flex', gap: 'var(--spacing-xl)', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 400px' }}>
              <h2 style={{ marginBottom: 'var(--spacing-lg)' }}>📝 Update Profile</h2>
              <div className="glass-card" style={{ padding: 'var(--spacing-lg)' }}>
                <form className="profile-form" onSubmit={saveProfile}>
                  {profileMsg && <div style={{ fontSize: '0.85rem', marginBottom: '10px', color: profileMsg.startsWith('✅') ? 'var(--success)' : 'var(--danger)' }}>{profileMsg}</div>}
                  {[
                    { label: 'Annual Income (₹)', name: 'annual_income', type: 'number' },
                    { label: 'Credit Score (300-900)', name: 'credit_score', type: 'number', min: 300, max: 900 },
                    { label: 'Employment (months)', name: 'employment_months', type: 'number' },
                    { label: 'Existing Loans', name: 'existing_loans', type: 'number' },
                    { label: 'Current EMI (₹/month)', name: 'existing_emi_amount', type: 'number' },
                    { label: 'Credit Utilization (%)', name: 'credit_utilization', type: 'number', max: 100 },
                    { label: 'Age', name: 'age', type: 'number', min: 18 },
                    { label: 'City', name: 'city', type: 'text' },
                    { label: 'Loan Amount Needed (₹)', name: 'requested_amount', type: 'number' },
                    { label: 'Tenure (months)', name: 'requested_tenure_months', type: 'number' },
                  ].map(f => (
                    <div className="input-group" key={f.name}>
                      <label>{f.label}</label>
                      <input className="input-field" type={f.type} name={f.name}
                        value={profileForm[f.name]} min={f.min} max={f.max}
                        onChange={(e) => setProfileForm({ ...profileForm, [f.name]: e.target.value })}
                        placeholder={f.label} />
                    </div>
                  ))}
                  <div className="input-group">
                    <label>Loan Interest</label>
                    <select className="input-field" name="loan_type_interest"
                      value={profileForm.loan_type_interest}
                      onChange={(e) => setProfileForm({ ...profileForm, loan_type_interest: e.target.value })}>
                      <option value="home_loan">Home Loan</option>
                      <option value="personal_loan">Personal Loan</option>
                      <option value="car_loan">Car Loan</option>
                      <option value="business_loan">Business Loan</option>
                      <option value="education_loan">Education Loan</option>
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary" id="save-profile-btn" style={{ marginTop: '15px', width: '100%' }}>
                    💾 Save Profile
                  </button>
                </form>
              </div>
            </div>

            <div style={{ flex: '1 1 400px' }}>
              <h2 style={{ marginBottom: 'var(--spacing-lg)' }}>📄 Document Parser</h2>
              <div className="glass-card" style={{ padding: 'var(--spacing-lg)' }}>
                <p style={{ marginBottom: '15px', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                  Upload your salary slips, tax forms, or CIBIL reports. The AI will automatically extract and construct your financial profile below.
                </p>
                <DocumentUpload userId={user?.user_id} token={token} onUploadComplete={loadProfile} />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'tools' && (
          <div style={{ padding: 'var(--spacing-xl)', maxWidth: 600, margin: '0 auto' }}>
            <h2 style={{ marginBottom: 'var(--spacing-lg)' }}>📊 EMI Calculator</h2>
            <div className="glass-card">
              <EMICalculator />
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {sessionToDelete && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          animation: 'fadeIn 0.2s ease'
        }}>
          <div style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '16px',
            padding: '24px',
            width: '90%',
            maxWidth: '380px',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
            animation: 'fadeInUp 0.3s ease',
            textAlign: 'center'
          }}>
            <div style={{ fontSize: '3rem', marginBottom: '10px' }}>🗑️</div>
            <h3 style={{ marginBottom: '12px', fontSize: '1.2rem', color: 'var(--text-primary)' }}>Delete Conversation</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', marginBottom: '24px', lineHeight: 1.5 }}>
              Are you sure you want to permanently delete this chat? This action cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button 
                className="btn btn-ghost" 
                style={{ flex: 1, padding: '10px' }}
                onClick={() => setSessionToDelete(null)}
              >
                Cancel
              </button>
              <button 
                className="btn btn-primary" 
                style={{ flex: 1, padding: '10px', background: 'var(--danger)', boxShadow: '0 4px 12px rgba(220, 38, 38, 0.3)' }}
                onClick={confirmDeleteSession}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
