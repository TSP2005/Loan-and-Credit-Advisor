import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiPost, sendLog } from '../api/client';
import EMICalculator from '../components/EMICalculator';

export default function GuestPage() {
  const navigate = useNavigate();
  const [policyQuery, setPolicyQuery] = useState('');
  const [policyResults, setPolicyResults] = useState([]);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [rateType, setRateType] = useState('home_loan');
  const [rateScore, setRateScore] = useState(700);
  const [rateResult, setRateResult] = useState(null);

  const searchPolicy = async (e) => {
    e.preventDefault();
    if (!policyQuery.trim()) return;
    setPolicyLoading(true);
    sendLog('info', 'GuestPage', 'POLICY_SEARCH', `query=${policyQuery}`);
    try {
      const data = await apiPost('/guest/policy-search', { query: policyQuery, top_k: 5 });
      setPolicyResults(data.data?.results || []);
    } catch (err) {
      sendLog('error', 'GuestPage', 'POLICY_SEARCH_FAILED', err.message);
    }
    setPolicyLoading(false);
  };

  const checkRate = async () => {
    sendLog('info', 'GuestPage', 'RATE_CHECK', `type=${rateType} score=${rateScore}`);
    try {
      const data = await apiPost('/guest/rate-estimate', { loan_type: rateType, credit_score: rateScore });
      setRateResult(data.data);
    } catch (err) {
      sendLog('error', 'GuestPage', 'RATE_CHECK_FAILED', err.message);
    }
  };

  return (
    <>
      {/* Navbar */}
      <nav className="navbar" style={{ marginLeft: 0 }}>
        <div className="navbar-brand">
          <span className="logo-icon">🏦</span>
          <h1>AI Loan Advisor — Guest Mode</h1>
        </div>
        <div className="navbar-actions">
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/login')} id="login-btn">
            🔐 Sign In for Full Access
          </button>
        </div>
      </nav>

      <div className="guest-page">
        <div className="guest-header">
          <h1>Financial Tools & Policy Info</h1>
          <p>Calculate EMIs, check interest rates, and explore policy documents — no login needed</p>
        </div>

        <div className="guest-grid">
          {/* EMI Calculator */}
          <div className="glass-card">
            <div className="section-title">📊 EMI Calculator</div>
            <EMICalculator />
          </div>

          {/* Rate Estimator */}
          <div className="glass-card">
            <div className="section-title">💰 Interest Rate Lookup</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
              <div className="input-group">
                <label>Loan Type</label>
                <select className="input-field" value={rateType} onChange={(e) => setRateType(e.target.value)} id="rate-loan-type">
                  <option value="home_loan">🏠 Home Loan</option>
                  <option value="personal_loan">💳 Personal Loan</option>
                  <option value="car_loan">🚗 Car Loan</option>
                  <option value="business_loan">🏢 Business Loan</option>
                  <option value="education_loan">🎓 Education Loan</option>
                  <option value="gold_loan">🥇 Gold Loan</option>
                  <option value="mudra_loan">🏪 MUDRA Loan</option>
                </select>
              </div>
              <div className="slider-group">
                <div className="slider-header">
                  <label>Credit Score</label>
                  <span className="slider-value">{rateScore}</span>
                </div>
                <input type="range" min="300" max="900" value={rateScore}
                  onChange={(e) => setRateScore(+e.target.value)} id="rate-credit-score" />
              </div>
              <button className="btn btn-primary" onClick={checkRate} id="check-rate-btn">
                Check Rates
              </button>

              {rateResult && !rateResult.error && (
                <div style={{ marginTop: 'var(--spacing-md)' }}>
                  <div className="emi-results">
                    <div className="emi-result-card">
                      <div className="emi-amount">{rateResult.min_rate}%</div>
                      <div className="emi-label">Min Rate</div>
                    </div>
                    <div className="emi-result-card">
                      <div className="emi-amount" style={{ color: 'var(--success)' }}>{rateResult.personalized_rate}%</div>
                      <div className="emi-label">Your Rate</div>
                    </div>
                    <div className="emi-result-card">
                      <div className="emi-amount">{rateResult.max_rate}%</div>
                      <div className="emi-label">Max Rate</div>
                    </div>
                  </div>
                  <p style={{ marginTop: 'var(--spacing-md)', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    Credit Tier: <strong>{rateResult.credit_tier}</strong> • Providers: {rateResult.providers?.join(', ')}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Policy Search */}
          <div className="glass-card" style={{ gridColumn: '1 / -1' }}>
            <div className="section-title">📋 Policy & Scheme Search</div>
            <form onSubmit={searchPolicy} style={{ display: 'flex', gap: 'var(--spacing-md)', marginBottom: 'var(--spacing-lg)' }}>
              <input className="input-field" placeholder="e.g., Am I eligible for PMAY?" value={policyQuery}
                onChange={(e) => setPolicyQuery(e.target.value)} id="policy-query-input" />
              <button type="submit" className="btn btn-primary" disabled={policyLoading} id="policy-search-btn">
                {policyLoading ? '🔍...' : '🔍 Search'}
              </button>
            </form>

            {policyResults.length > 0 && (
              <div>
                {policyResults.map((r, i) => (
                  <div className="policy-result" key={i}>
                    <div className="source">{r.source?.replace(/_/g, ' ').replace('.txt', '')} — Score: {(r.score * 100).toFixed(0)}%</div>
                    <div className="excerpt">{r.text}</div>
                  </div>
                ))}
              </div>
            )}

            {policyResults.length === 0 && policyQuery && !policyLoading && (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center' }}>
                No results found. Try searching for "PMAY eligibility", "home loan RBI guidelines", or "MUDRA scheme".
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
