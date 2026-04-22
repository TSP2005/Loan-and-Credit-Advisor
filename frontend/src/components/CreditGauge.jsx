export default function CreditGauge({ score }) {
  const maxScore = 900;
  const minScore = 300;
  const pct = Math.max(0, Math.min(1, (score - minScore) / (maxScore - minScore)));

  // SVG arc from -135deg to +135deg (270deg total)
  const angle = -135 + pct * 270;
  const cx = 80, cy = 80, r = 65;
  const toRad = (d) => (d * Math.PI) / 180;
  const x = cx + r * Math.cos(toRad(angle));
  const y = cy + r * Math.sin(toRad(angle));

  // Arc path
  const startAngle = -135;
  const endAngle = 135;
  const startX = cx + r * Math.cos(toRad(startAngle));
  const startY = cy + r * Math.sin(toRad(startAngle));
  const endX = cx + r * Math.cos(toRad(endAngle));
  const endY = cy + r * Math.sin(toRad(endAngle));

  const filledEndX = cx + r * Math.cos(toRad(angle));
  const filledEndY = cy + r * Math.sin(toRad(angle));
  const largeArc = angle - startAngle > 180 ? 1 : 0;

  const color = score >= 750 ? '#10b981' : score >= 650 ? '#f59e0b' : '#ef4444';
  const tier = score >= 750 ? 'Excellent' : score >= 700 ? 'Good' : score >= 650 ? 'Fair' : 'Needs Work';

  return (
    <div className="gauge-container">
      <svg className="gauge-svg" viewBox="0 0 160 100">
        {/* Background arc */}
        <path
          d={`M ${startX} ${startY} A ${r} ${r} 0 1 1 ${endX} ${endY}`}
          fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" strokeLinecap="round"
        />
        {/* Filled arc */}
        {pct > 0.01 && (
          <path
            d={`M ${startX} ${startY} A ${r} ${r} 0 ${largeArc} 1 ${filledEndX} ${filledEndY}`}
            fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
          />
        )}
        {/* Needle dot */}
        <circle cx={filledEndX} cy={filledEndY} r="5" fill={color} />
      </svg>
      <div className="gauge-value" style={{ color }}>{score}</div>
      <div className="gauge-label">{tier}</div>
    </div>
  );
}
