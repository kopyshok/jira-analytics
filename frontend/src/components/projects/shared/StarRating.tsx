import React from 'react';

interface Props {
  value: number;
  max?: number;
  size?: number;
}

export const StarRating: React.FC<Props> = ({ value, max = 5, size = 18 }) => (
  <div style={{ display: 'inline-flex', gap: 2 }}>
    {Array.from({ length: max }).map((_, i) => (
      <svg key={i} width={size} height={size} viewBox="0 0 24 24" fill={i < value ? '#00c9c8' : '#2a3a5c'}>
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
      </svg>
    ))}
  </div>
);
