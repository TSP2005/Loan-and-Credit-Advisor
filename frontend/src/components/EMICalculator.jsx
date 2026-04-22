import { useState, useEffect } from 'react';
import { apiPost, sendLog } from '../api/client';

export default function EMICalculator() {
  const [principal, setPrincipal] = useState(3000000);
  const [rate, setRate] = useState(9.0);
  const [tenure, setTenure] = useState(240);
  const [result, setResult] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => calculate(), 300);
    return () => clearTimeout(timer);
  }, [principal, rate, tenure]);

  const calculate = async () => {
    try {
      const data = await apiPost('/guest/emi-calculate', {
        principal, annual_rate_percent: rate, tenure_months: tenure
      });
      setResult(data.data);
      sendLog('info', 'EMICalculator', 'EMI_CALCULATED',
        `P=${principal} R=${rate} T=${tenure} EMI=${data.data?.monthly_emi}`);
    } catch (err) {
      // Fallback client-side calculation
      const r = rate / (12 * 100);
      const n = tenure;
      const pow = Math.pow(1 + r, n);
      const emi = principal * r * pow / (pow - 1);
      setResult({
        monthly_emi: Math.round(emi * 100) / 100,
        total_interest: Math.round((emi * n - principal) * 100) / 100,
        total_repayment: Math.round(emi * n * 100) / 100,
      });
    }
  };

  const fmt = (n) => '₹' + (n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  return (
    <div className="emi-calculator">
      <div className="slider-group">
        <div className="slider-header">
          <label>Loan Amount</label>
          <span className="slider-value">{fmt(principal)}</span>
        </div>
        <input type="range" min={100000} max={50000000} step={100000} value={principal}
          onChange={(e) => setPrincipal(+e.target.value)} id="emi-principal-slider" />
      </div>

      <div className="slider-group">
        <div className="slider-header">
          <label>Interest Rate</label>
          <span className="slider-value">{rate}%</span>
        </div>
        <input type="range" min={5} max={25} step={0.25} value={rate}
          onChange={(e) => setRate(+e.target.value)} id="emi-rate-slider" />
      </div>

      <div className="slider-group">
        <div className="slider-header">
          <label>Tenure</label>
          <span className="slider-value">{tenure} months ({(tenure / 12).toFixed(1)} yrs)</span>
        </div>
        <input type="range" min={12} max={360} step={12} value={tenure}
          onChange={(e) => setTenure(+e.target.value)} id="emi-tenure-slider" />
      </div>

      {result && (
        <div className="emi-results">
          <div className="emi-result-card">
            <div className="emi-amount">{fmt(result.monthly_emi)}</div>
            <div className="emi-label">Monthly EMI</div>
          </div>
          <div className="emi-result-card">
            <div className="emi-amount" style={{ color: 'var(--warning)' }}>{fmt(result.total_interest)}</div>
            <div className="emi-label">Total Interest</div>
          </div>
          <div className="emi-result-card">
            <div className="emi-amount" style={{ color: 'var(--success)' }}>{fmt(result.total_repayment)}</div>
            <div className="emi-label">Total Repayment</div>
          </div>
        </div>
      )}
    </div>
  );
}
