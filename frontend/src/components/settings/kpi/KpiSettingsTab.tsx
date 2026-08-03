import { useState } from 'react';
import { Tabs, Typography } from 'antd';
import ProfileEditor from './ProfileEditor';
import MetricEditor from './MetricEditor';
import CycleTimeNorms from './CycleTimeNorms';
import GeneralRules from './GeneralRules';

const { Paragraph } = Typography;

/** Подпись раздела над формой — вместо заголовков, которые раньше шли подряд одной лентой. */
function SectionNote({ children }: { children: React.ReactNode }) {
  return (
    <Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 14 }}>
      {children}
    </Paragraph>
  );
}

const ITEMS = [
  {
    key: 'profiles',
    label: 'Профили оценки',
    children: (
      <>
        <SectionNote>
          Профиль оценивает перечисленные роли сотрудников. Сумма весов метрик обязана
          равняться 100%. Сотрудники, чья роль не привязана ни к одному профилю, в
          ведомость не попадают — следите за таблицей покрытия внизу.
        </SectionNote>
        <ProfileEditor />
      </>
    ),
  },
  {
    key: 'constructor',
    label: 'Конструктор метрики',
    children: (
      <>
        <SectionNote>
          Все параметры метрики — на одной форме. Предпросмотр считает то, что сейчас в
          форме, не сохраняя её. Список полей Jira и их сопоставление настраиваются
          отдельно — «Настройки → Подключение → Поля Jira».
        </SectionNote>
        <MetricEditor />
      </>
    ),
  },
  {
    key: 'cycletime',
    label: 'Нормативы Cycle Time',
    children: (
      <>
        <SectionNote>Ожидаемое время выполнения задачи по командам и кварталам, дней.</SectionNote>
        <CycleTimeNorms />
      </>
    ),
  },
  {
    key: 'rules',
    label: 'Общие правила',
    children: (
      <>
        <SectionNote>Применяются ко всем метрикам раздела KPI.</SectionNote>
        <GeneralRules />
      </>
    ),
  },
];

export default function KpiSettingsTab() {
  // Раньше здесь была колонка якорей и все четыре справочника одной прокруткой:
  // колонка съедала ~200 px ширины рядом с левым меню настроек, а форма
  // конструктора в остатке не помещалась.
  const [active, setActive] = useState('profiles');

  return <Tabs activeKey={active} onChange={setActive} items={ITEMS} />;
}
