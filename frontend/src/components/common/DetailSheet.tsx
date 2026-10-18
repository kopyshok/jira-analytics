import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { CloseOutlined, FullscreenExitOutlined, FullscreenOutlined } from '@ant-design/icons';
import { clamp, loadPrefs, savePrefs, type Placement, type Prefs } from './detailSheetPrefs';
import { DetailSheetWidthContext } from './detailSheetWidth';
import './DetailSheet.css';

/**
 * Панель подробностей поверх страницы: лист снизу на всю ширину или широкая панель справа.
 * Пользователь переключает место, тянет край мышью и разворачивает на весь экран;
 * выбор и размер запоминаются в браузере. Пока панель открыта, на <html> висят
 * data-detail-sheet и --detail-sheet-size — оболочка темы по ним ужимает рабочую
 * область, чтобы панель ничего не закрывала.
 * Ширину тела содержимое берёт из useDetailSheetWidth() — по ней раскладывает колонки.
 * На странице открыта не больше одной панели.
 */

// ponytail: признаки открытых окон AntD по классам — если Esc закроет лишнее, перейти на счётчик открытых окон.
const OVERLAY_OPEN =
  '.ant-modal-wrap:not([style*="display: none"]), .ant-select-dropdown:not(.ant-select-dropdown-hidden), ' +
  '.ant-picker-dropdown:not(.ant-picker-dropdown-hidden), .ant-dropdown:not(.ant-dropdown-hidden), ' +
  '.ant-popover:not(.ant-popover-hidden)';

interface Props {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Строка под заголовком: исполнитель, даты, часы. */
  subtitle?: ReactNode;
  /** Действия в шапке: «предыдущая / следующая», «Сохранить». */
  extra?: ReactNode;
  ariaLabel: string;
  className?: string;
  children: ReactNode;
}

function PlacementIcon({ placement }: { placement: Placement }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden>
      <rect x="1" y="1" width="12" height="12" rx="1.5" />
      {placement === 'bottom' ? <path d="M1 8.5h12" /> : <path d="M7.5 1v12" />}
    </svg>
  );
}

export default function DetailSheet({ open, onClose, title, subtitle, extra, ariaLabel, className, children }: Props) {
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  const [expanded, setExpanded] = useState(false);
  const [body, setBody] = useState<HTMLDivElement | null>(null);
  const [bodyWidth, setBodyWidth] = useState(0);
  // Закрыли панель — следующее открытие начинается не развёрнутым.
  // Открыли — место и размер перечитываем: их могла сменить другая панель страницы.
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (!open) setExpanded(false);
    else {
      setPrefs(loadPrefs());
      setBodyWidth(0);
    }
  }
  const [viewport, setViewport] = useState({ w: window.innerWidth, h: window.innerHeight });
  const dragging = useRef(false);

  const { placement } = prefs;
  const size = Math.round(placement === 'bottom' ? prefs[placement] * viewport.h : prefs[placement] * viewport.w);

  useEffect(() => {
    const onResize = () => setViewport({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Рабочая область оболочки ужимается на размер панели (раскрытая панель закрывает всё — ужимать незачем).
  useEffect(() => {
    if (!open) return;
    const root = document.documentElement;
    root.dataset.detailSheet = placement;
    root.style.setProperty('--detail-sheet-size', `${size}px`);
    return () => {
      delete root.dataset.detailSheet;
      root.style.removeProperty('--detail-sheet-size');
    };
  }, [open, placement, size]);

  useEffect(() => {
    if (!body || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => setBodyWidth(Math.round(entry.contentRect.width)));
    ro.observe(body);
    return () => ro.disconnect();
  }, [body]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      const t = e.target as HTMLElement | null;
      if (t?.closest('input, textarea, select, [contenteditable="true"]') || document.querySelector(OVERLAY_OPEN)) return;
      if (expanded) setExpanded(false);
      else onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, expanded, onClose]);

  const update = useCallback((next: Partial<Prefs>) => {
    setPrefs((prev) => {
      const merged = { ...prev, ...next };
      savePrefs(merged);
      return merged;
    });
  }, []);

  const fractionAt = (e: PointerEvent) =>
    placement === 'bottom'
      ? (window.innerHeight - e.clientY) / window.innerHeight
      : (window.innerWidth - e.clientX) / window.innerWidth;

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    // Во время перетаскивания не пишем в браузер на каждый кадр — только в конце.
    setPrefs((prev) => ({ ...prev, [placement]: clamp(placement, fractionAt(e)) }));
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    update({ [placement]: clamp(placement, fractionAt(e)) });
  };
  const onHandleKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const grow = placement === 'bottom' ? 'ArrowUp' : 'ArrowLeft';
    const shrink = placement === 'bottom' ? 'ArrowDown' : 'ArrowRight';
    if (e.key !== grow && e.key !== shrink) return;
    e.preventDefault();
    update({ [placement]: clamp(placement, prefs[placement] + (e.key === grow ? 0.05 : -0.05)) });
  };

  if (!open) return null;

  const style = expanded ? undefined : placement === 'bottom' ? { height: size } : { width: size };
  const other: Placement = placement === 'bottom' ? 'right' : 'bottom';
  // До первого замера — оценка по окну, чтобы содержимое не мигало узкой раскладкой.
  const width = bodyWidth || (placement === 'right' && !expanded ? size : viewport.w);

  return createPortal(
    <section
      className={`detail-sheet detail-sheet--${placement}${expanded ? ' is-expanded' : ''}${className ? ` ${className}` : ''}`}
      style={style}
      aria-label={ariaLabel}
    >
      {!expanded && (
        <div
          className="detail-sheet__handle"
          role="separator"
          aria-orientation={placement === 'bottom' ? 'horizontal' : 'vertical'}
          aria-label="Изменить размер панели"
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onKeyDown={onHandleKey}
        />
      )}
      <header className="detail-sheet__head">
        <div className="detail-sheet__title">
          <div className="detail-sheet__name">{title}</div>
          {subtitle && <div className="detail-sheet__sub">{subtitle}</div>}
        </div>
        {extra && <div className="detail-sheet__extra">{extra}</div>}
        <div className="detail-sheet__tools">
          <button
            type="button"
            className="detail-sheet__tool"
            onClick={() => update({ placement: other })}
            title={other === 'right' ? 'Показать панелью справа' : 'Показать листом снизу'}
            aria-label={other === 'right' ? 'Показать панелью справа' : 'Показать листом снизу'}
          >
            <PlacementIcon placement={other} />
          </button>
          <button
            type="button"
            className="detail-sheet__tool"
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? 'Свернуть (Esc)' : 'Развернуть на весь экран'}
            aria-label={expanded ? 'Свернуть' : 'Развернуть на весь экран'}
            aria-pressed={expanded}
          >
            {expanded ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
          </button>
          <button type="button" className="detail-sheet__tool" onClick={onClose} title="Закрыть (Esc)" aria-label="Закрыть">
            <CloseOutlined />
          </button>
        </div>
      </header>
      <div className="detail-sheet__body" ref={setBody}>
        <DetailSheetWidthContext.Provider value={width}>{children}</DetailSheetWidthContext.Provider>
      </div>
    </section>,
    document.body,
  );
}
