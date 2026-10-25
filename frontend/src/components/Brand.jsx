// Shared Parakh AI brand lockup: logo mark + wordmark (+ optional tagline).
export function BrandMark({ size = 40 }) {
  return (
    <svg
      className="brand-logo"
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="Parakh AI"
    >
      <rect width="48" height="48" rx="13" fill="#282e34" />
      <path
        d="M17 36V12h9.2c5 0 8.3 2.8 8.3 7.2s-3.3 7.3-8.3 7.3H21.5"
        fill="none"
        stroke="#fff"
        strokeWidth="4.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="35.5" cy="34.5" r="3.4" fill="#dc926d" />
    </svg>
  )
}

export default function Brand({ onClick, size = 40, tagline = false, light = false, stacked = false }) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      className={`brand${light ? ' brand-light-theme' : ''}${stacked ? ' brand-stacked' : ''}`}
      onClick={onClick}
      aria-label="Parakh AI home"
    >
      <BrandMark size={size} />
      <span className="brand-text">
        <span className="brand-wordmark">
          Parakh<span className="brand-ai"> AI</span>
        </span>
        {tagline && <span className="brand-tagline">Oral assessment, reimagined</span>}
      </span>
    </Tag>
  )
}
