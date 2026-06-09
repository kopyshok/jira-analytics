import { type ReactNode, type InputHTMLAttributes } from 'react';

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  trailing?: ReactNode;
  wrapperStyle?: React.CSSProperties;
}

export function GlassInput({ icon, trailing, wrapperStyle, style, ...rest }: Props) {
  return (
    <div className="ginput" style={wrapperStyle}>
      {icon}
      <input {...rest} style={style} />
      {trailing}
    </div>
  );
}
