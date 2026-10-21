import { useEffect, useRef, useState } from 'react';
import { InputNumber } from 'antd';

interface Props {
  /** Норма с сервера; меняется только после ответа на сохранение. */
  value: number | null;
  onCommit: (hours: number | null) => void;
  /** Вид поля для встроенных модулей обложки (по умолчанию — обычная рамка). */
  variant?: 'borderless';
  ariaLabel?: string;
}

/**
 * Поле дневной нормы «резиновой» задачи: одно сохранение на один ввод —
 * по Enter или при уходе из поля, а не на каждое нажатие клавиши.
 *
 * Сохранять на каждое изменение значило слать запрос на каждый символ и ещё
 * один по Enter: поле сверяет набранное со значением с сервера, которое до
 * ответа остаётся старым, и сообщает об изменении повторно.
 */
export function DailyRateInput({ value, onCommit, variant, ariaLabel }: Props) {
  const [draft, setDraft] = useState(value);
  const [base, setBase] = useState(value);
  // Пришла норма с сервера (наше сохранение или чужая правка) — набор с неё.
  if (base !== value) {
    setBase(value);
    setDraft(value);
  }
  // Ссылки, а не состояние: поле дописывает значение (вводит в пределы) в том же
  // событии, что и Enter или уход фокуса, — до перерисовки.
  const draftRef = useRef(value);
  const savedRef = useRef(value);
  useEffect(() => {
    draftRef.current = value;
    savedRef.current = value;
  }, [value]);

  const commit = () => {
    const next = draftRef.current;
    if (next === savedRef.current) return;
    savedRef.current = next;
    onCommit(next);
  };

  return (
    // Уход фокуса слушаем снаружи: само поле дописывает значение уже после
    // обработчиков на нём. Щелчок не доходит до строки таблицы.
    <span onBlur={commit} onClick={(e) => e.stopPropagation()}>
      <InputNumber
        size="small"
        variant={variant}
        aria-label={ariaLabel}
        min={0}
        max={24}
        step={0.5}
        placeholder="—"
        value={draft}
        onChange={(v) => {
          const hours = v == null ? null : Number(v);
          draftRef.current = hours;
          setDraft(hours);
        }}
        onPressEnter={commit}
        style={{ width: 84 }}
      />
    </span>
  );
}
