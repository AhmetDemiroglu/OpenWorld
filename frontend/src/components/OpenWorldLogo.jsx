export function OpenWorldLogo({ size = 40, className = "" }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Outer glow */}
      <circle cx="50" cy="50" r="46" stroke="#54d2d2" strokeWidth="1" opacity="0.15" />
      {/* Globe outline */}
      <circle cx="50" cy="50" r="42" stroke="#54d2d2" strokeWidth="2.5" opacity="0.9" />
      {/* Latitude lines */}
      <ellipse cx="50" cy="50" rx="42" ry="16" stroke="#54d2d2" strokeWidth="1.2" opacity="0.4" />
      <ellipse cx="50" cy="50" rx="42" ry="32" stroke="#54d2d2" strokeWidth="0.8" opacity="0.2" />
      {/* Meridian */}
      <ellipse cx="50" cy="50" rx="16" ry="42" stroke="#54d2d2" strokeWidth="1.2" opacity="0.4" />
      {/* Center node */}
      <circle cx="50" cy="50" r="5" fill="#54d2d2" />
      <circle cx="50" cy="50" r="8" stroke="#54d2d2" strokeWidth="1" opacity="0.3" />
      {/* Satellite nodes */}
      <circle cx="26" cy="34" r="3.5" fill="#54d2d2" opacity="0.85" />
      <circle cx="74" cy="36" r="3.5" fill="#54d2d2" opacity="0.85" />
      <circle cx="35" cy="74" r="3.5" fill="#54d2d2" opacity="0.85" />
      <circle cx="70" cy="68" r="3.5" fill="#54d2d2" opacity="0.85" />
      {/* Connection lines */}
      <line x1="50" y1="50" x2="26" y2="34" stroke="#54d2d2" strokeWidth="1" opacity="0.35" />
      <line x1="50" y1="50" x2="74" y2="36" stroke="#54d2d2" strokeWidth="1" opacity="0.35" />
      <line x1="50" y1="50" x2="35" y2="74" stroke="#54d2d2" strokeWidth="1" opacity="0.35" />
      <line x1="50" y1="50" x2="70" y2="68" stroke="#54d2d2" strokeWidth="1" opacity="0.35" />
      {/* Cross connections */}
      <line x1="26" y1="34" x2="74" y2="36" stroke="#54d2d2" strokeWidth="0.6" opacity="0.2" strokeDasharray="3 3" />
      <line x1="35" y1="74" x2="70" y2="68" stroke="#54d2d2" strokeWidth="0.6" opacity="0.2" strokeDasharray="3 3" />
    </svg>
  );
}
