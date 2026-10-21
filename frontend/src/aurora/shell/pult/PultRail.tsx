import { useNavigate } from 'react-router';
import { NAV_GROUPS, useNavSections } from '../navConfig';

/** Короткие подписи под значками (только визуально; полное имя — в title/aria-label). */
const SHORT_LABEL: Record<string, string> = {
  '/analytics/work-type-report': 'Тематич. отчёт',
  '/executive': 'Сводка руковод.',
  '/sync': 'Синхрониз.',
};

/** Полные имена там, где в общем меню уже стоит сокращение. */
const FULL_LABEL: Record<string, string> = {
  '/resource-planning': 'Ресурсное планирование',
};

const GROUP_CAPTION: Record<string, string> = {
  'Обзор': 'Обзор',
  'Планирование': 'План',
  'Данные': 'Данные',
};

export function PultRail() {
  const navigate = useNavigate();
  const { groups, selectedKey } = useNavSections();

  return (
    <nav className="pult-rail" aria-label="Разделы">
      <div className="pult-logo" title={`Jira Analytics v${__APP_VERSION__}`} aria-label="Jira Analytics">JA</div>
      <div className="pult-ver" title={`Версия ${__APP_VERSION__}`}>v{__APP_VERSION__}</div>
      {groups.map((g) => {
        const num = String(NAV_GROUPS.findIndex((x) => x.label === g.label) + 1).padStart(2, '0');
        return (
          <div key={g.label} className="pult-rail-group" role="group" aria-label={g.label}>
            <div className="pult-rail-cap" aria-hidden="true">
              <b>{num}</b> {GROUP_CAPTION[g.label] ?? g.label}
            </div>
            {g.items.map(({ key, icon: Icon, label }) => {
              const active = selectedKey === key;
              const full = FULL_LABEL[key] ?? label;
              return (
                <button
                  key={key}
                  type="button"
                  className={`pult-rail-item${active ? ' is-active' : ''}`}
                  title={full}
                  aria-label={full}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => navigate(key)}
                >
                  {active && <span className="pult-rail-dot" aria-hidden="true" />}
                  <Icon size={20} strokeWidth={1.6} aria-hidden="true" />
                  <span className="pult-rail-label">{SHORT_LABEL[key] ?? label}</span>
                </button>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
