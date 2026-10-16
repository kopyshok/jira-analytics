import { TriangleAlert } from 'lucide-react';

/** Треугольник-предупреждение тонкой линией — у конфликтов и сигналов. */
export function WarnIcon({ className, size = 16 }: { className?: string; size?: number }) {
  return <TriangleAlert className={className} size={size} strokeWidth={1.5} aria-hidden="true" />;
}
