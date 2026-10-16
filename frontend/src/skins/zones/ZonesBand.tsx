import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useZonesBand } from './bandContext';

interface Props {
  /** Рубрика над заголовком; по умолчанию — название зоны. */
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  /** Кнопки страницы справа в верхнем ряду (после глобальных). */
  tools?: ReactNode;
  /** Нижние ряды: фильтры и вкладки экрана. */
  children?: ReactNode;
}

/** Переносит заголовок и элементы управления страницы в полосу зоны. */
export default function ZonesBand({ eyebrow, title, subtitle, tools, children }: Props) {
  const slots = useZonesBand();
  if (!slots) return null;
  return (
    <>
      {slots.head && createPortal(
        <div className="zn-page-head">
          <div className="zn-page-eyebrow">{eyebrow ?? slots.zoneLabel}</div>
          <h1 className="zn-page-title">{title}</h1>
          {subtitle && <p className="zn-page-sub">{subtitle}</p>}
        </div>,
        slots.head,
      )}
      {tools && slots.tools && createPortal(tools, slots.tools)}
      {children && slots.rows && createPortal(children, slots.rows)}
    </>
  );
}

/** Белое поле на цветной полосе: подпись капителью и значение. */
export function BandField({ label, children, className, ...rest }: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLDivElement>, 'children'>) {
  return (
    <div className={['zn-field', className].filter(Boolean).join(' ')} {...rest}>
      <span className="zn-field-label">{label}</span>
      {children}
    </div>
  );
}

interface TabItem {
  key: string;
  label: ReactNode;
}

/** Вкладки экрана «папками» внизу полосы; активная сливается с телом. */
export function BandTabs({ items, activeKey, onChange, ...rest }: {
  items: TabItem[];
  activeKey: string;
  onChange: (key: string) => void;
} & Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'>) {
  return (
    <div className="zn-band-tabs" role="tablist" {...rest}>
      {items.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={t.key === activeKey}
          className={`zn-band-tab${t.key === activeKey ? ' is-active' : ''}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
