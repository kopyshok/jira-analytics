import type { CSSProperties, ReactNode } from 'react';
import FeedbackLinks from './FeedbackLinks';
import '../swiss-pages.css';

/**
 * Каркас страницы обложки «Швейцарская»: 12-колоночная сетка, слева —
 * «паспорт экрана» (заголовок, крупные цифры, фильтры), справа — данные.
 * Страница занимает экран целиком, длинное прокручивается внутри блоков.
 */
export function SwissPage({ passportSpan = 3, className, children }: {
  /** Ширина паспорта в колонках сетки: 3 — обычно, 2 — у плотных экранов. */
  passportSpan?: 2 | 3;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`sw-page sw-page--p${passportSpan}${className ? ` ${className}` : ''}`}>
      {children}
    </div>
  );
}

/** Зона данных справа от паспорта. */
export function SwissData({ children, className, style }: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return <section className={`sw-data${className ? ` ${className}` : ''}`} style={style}>{children}</section>;
}

/** Паспорт экрана: рубрика, заголовок, подзаголовок, содержимое; внизу — обратная связь. */
export function Passport({ eyebrow, title, subtitle, children }: {
  eyebrow: string;
  title: ReactNode;
  subtitle?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <aside className="sw-passport">
      <div className="sw-eyebrow">{eyebrow}</div>
      <h1 className="sw-title">{title}</h1>
      {subtitle && <p className="sw-subtitle">{subtitle}</p>}
      {children}
      <FeedbackLinks />
    </aside>
  );
}

/** Ключевые цифры раздела — сеткой 2×N под линией. */
export function Figures({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={`sw-figures${className ? ` ${className}` : ''}`}>{children}</div>;
}

export function Figure({ value, caption, tone, strong, size, title }: {
  value: ReactNode;
  caption: ReactNode;
  /** accent — перерасход/проблема, good — норма достигнута. */
  tone?: 'accent' | 'good';
  /** Подпись жирным — у цифры-сигнала. */
  strong?: boolean;
  /** xl — главная цифра экрана во всю ширину паспорта. */
  size?: 'xl' | 'm';
  title?: string;
}) {
  return (
    <div className={`sw-figure${size ? ` sw-figure--${size}` : ''}`} title={title}>
      <div className={`sw-figure-value${tone ? ` is-${tone}` : ''}`}>{value}</div>
      <div className={`sw-figure-caption${strong ? ' is-strong' : ''}${tone && strong ? ` is-${tone}` : ''}`}>{caption}</div>
    </div>
  );
}

/** Раздел паспорта под линией: «2.1 ПЛАН», «1.1 ОТБОР». */
export function PassSection({ eyebrow, children, className }: {
  eyebrow: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`sw-pass-section${className ? ` ${className}` : ''}`}>
      <div className="sw-eyebrow">{eyebrow}</div>
      {children}
    </div>
  );
}

/** Поле фильтра: подпись заглавными над полем. */
export function Field({ label, children, className, htmlFor }: {
  label: ReactNode;
  children: ReactNode;
  className?: string;
  htmlFor?: string;
}) {
  return (
    <div className={`sw-field${className ? ` ${className}` : ''}`}>
      {htmlFor
        ? <label className="sw-field-label" htmlFor={htmlFor}>{label}</label>
        : <div className="sw-field-label">{label}</div>}
      {children}
    </div>
  );
}

/** Заголовок блока данных: номер «2.3», название, пояснение; справа — органы управления. */
export function BlockHead({ num, title, meta, children, size }: {
  num: string;
  title: ReactNode;
  meta?: ReactNode;
  children?: ReactNode;
  /** lg — главный блок экрана (16 px), по умолчанию 14 px. */
  size?: 'lg';
}) {
  return (
    <div className="sw-block-head">
      <div className="sw-block-title">
        <span className="sw-block-num">{num}</span>
        <b className={size === 'lg' ? 'is-lg' : undefined}>{title}</b>
        {meta && <span className="sw-block-meta">{meta}</span>}
      </div>
      {children && <div className="sw-block-tools">{children}</div>}
    </div>
  );
}
