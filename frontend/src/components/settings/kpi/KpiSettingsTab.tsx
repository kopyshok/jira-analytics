import { Typography } from 'antd';
import ProfileEditor from './ProfileEditor';
import MetricEditor from './MetricEditor';
import CycleTimeNorms from './CycleTimeNorms';
import GeneralRules from './GeneralRules';

const { Title, Paragraph } = Typography;

const SECTIONS = [
  { id: 'kpi-profiles', label: 'Профили оценки' },
  { id: 'kpi-constructor', label: 'Конструктор метрики' },
  { id: 'kpi-cycletime', label: 'Нормативы Cycle Time' },
  { id: 'kpi-rules', label: 'Общие правила' },
];

export default function KpiSettingsTab() {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 24 }}>
      <nav
        aria-label="Быстрый переход по разделам KPI"
        style={{
          flex: 'none', width: 200, position: 'sticky', top: 16,
          display: 'flex', flexDirection: 'column', gap: 2,
        }}
      >
        {SECTIONS.map((s) => (
          <a
            key={s.id}
            href={`#${s.id}`}
            style={{ fontSize: 12.5, fontWeight: 600, padding: '8px 10px', borderRadius: 8 }}
          >
            {s.label}
          </a>
        ))}
      </nav>

      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 24 }}>
        <section id="kpi-profiles" style={{ scrollMarginTop: 16 }}>
          <Title level={4} style={{ marginBottom: 2 }}>Профили оценки</Title>
          <Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 12 }}>
            Профиль привязан к роли сотрудника. Сумма весов метрик обязана равняться 100%.
          </Paragraph>
          <ProfileEditor />
        </section>

        <section id="kpi-constructor" style={{ scrollMarginTop: 16 }}>
          <Title level={4} style={{ marginBottom: 2 }}>Конструктор метрики</Title>
          <Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 12 }}>
            Все параметры метрики — на одной форме, предпросмотр формулы закреплён справа.
            Список полей Jira и их сопоставление настраиваются отдельно —
            «Настройки → Подключение → Поля Jira».
          </Paragraph>
          <MetricEditor />
        </section>

        <section id="kpi-cycletime" style={{ scrollMarginTop: 16 }}>
          <Title level={4} style={{ marginBottom: 2 }}>Нормативы Cycle Time</Title>
          <Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 12 }}>
            Ожидаемое время выполнения задачи по командам и кварталам, дней.
          </Paragraph>
          <CycleTimeNorms />
        </section>

        <section id="kpi-rules" style={{ scrollMarginTop: 16 }}>
          <Title level={4} style={{ marginBottom: 2 }}>Общие правила</Title>
          <Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 12 }}>
            Применяются ко всем метрикам раздела KPI.
          </Paragraph>
          <GeneralRules />
        </section>
      </div>
    </div>
  );
}
