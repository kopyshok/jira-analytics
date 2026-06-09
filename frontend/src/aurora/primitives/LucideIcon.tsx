import { type LucideIcon as LucideIconType, type LucideProps } from 'lucide-react';

interface Props extends Omit<LucideProps, 'size'> {
  icon: LucideIconType;
  size?: number;
}

export function LucideIcon({ icon: Icon, size = 18, strokeWidth = 1.8, ...rest }: Props) {
  return <Icon size={size} strokeWidth={strokeWidth} {...rest} />;
}
