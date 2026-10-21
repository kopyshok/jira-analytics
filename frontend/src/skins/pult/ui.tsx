import type { CSSProperties, ReactNode } from 'react';

/**
 * Кирпичики экранов обложки «Пульт».
 *
 * Экран = «панель управления» сверху (заголовок + органы экрана с подписями
 * над ними) и тело — сетка модулей с подписью в углу. Экран занимает всю
 * рабочую область без прокрутки страницы: длинное прокручивается внутри модуля.
 */

export function PultScreen({ panel, children, bodyClassName }: {
  panel: ReactNode;
  children: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <div className="pult-screen">
      <header className="pc-panel">{panel}</header>
      <div className={`pult-body${bodyClassName ? ` ${bodyClassName}` : ''}`}>{children}</div>
    </div>
  );
}

/** Ряд органов управления (с переносом на узком экране). */
export function PcRow({ children, className, style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return <div className={`pc-row${className ? ` ${className}` : ''}`} style={style}>{children}</div>;
}

/** Заголовок экрана: необязательная строка-раздел над ним, счётчик и пояснение справа. */
export function PcTitle({ eyebrow, title, count, sub }: {
  eyebrow?: ReactNode;
  title: ReactNode;
  count?: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="pc-title">
      {eyebrow && <div className="pc-cap pc-eyebrow">{eyebrow}</div>}
      <div className="pc-title-line">
        <h1>{title}</h1>
        {count != null && <span className="pc-count">{count}</span>}
        {sub && <span className="pc-sub">{sub}</span>}
      </div>
    </div>
  );
}

/** Орган управления с подписью над ним — как на приборе. */
export function PcField({ label, children, className, style }: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`pc-field${className ? ` ${className}` : ''}`} style={style}>
      <span className="pc-cap">{label}</span>
      {children}
    </div>
  );
}

/** «Экран» с индикатором — плашка состояния (статус, качество) в высоту поля. */
export function PcLamp({ color, children, dark, title }: {
  color?: string;
  children: ReactNode;
  dark?: boolean;
  title?: string;
}) {
  return (
    <span className={`pc-lamp${dark ? ' is-dark' : ''}`} title={title}>
      {color && <i className="p-dot" style={{ background: color }} />}
      {children}
    </span>
  );
}

/** Модуль стойки с подписью в левом верхнем углу. */
export function PModule({ title, extra, children, className, style, as = 'section', ariaLabel }: {
  title: ReactNode;
  extra?: ReactNode;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  as?: 'section' | 'div' | 'aside';
  ariaLabel?: string;
}) {
  const Tag = as;
  return (
    <Tag className={`pm${className ? ` ${className}` : ''}`} style={style} aria-label={ariaLabel}>
      <div className="pm-head">
        <span className="pm-cap">{title}</span>
        {extra}
      </div>
      {children}
    </Tag>
  );
}

/** Индикатор статуса 8px — круг. */
export function PDot({ color, title }: { color: string; title?: string }) {
  return <i className="p-dot" style={{ background: color }} title={title} aria-hidden={title ? undefined : true} />;
}
