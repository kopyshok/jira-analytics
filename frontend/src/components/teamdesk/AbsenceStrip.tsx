import { Empty, Select, Space, Typography } from 'antd';
import { useState } from 'react';
import AbsenceHeatmap from '../capacity/AbsenceHeatmap';
import { useAbsences } from '../../hooks/useAbsences';
import { useEmployees } from '../../hooks/useCapacity';

const QUARTERS = [1, 2, 3, 4];

interface Props {
  /** id сотрудников, попавших в срез стола (ключ — учётная запись Jira) */
  employeeIds: Record<string, string>;
  /**
   * Компактный вид скина: свой заголовок с одним полем «Период» и мини-карта
   * по неделям квартала — для узкой правой колонки.
   */
  compact?: boolean;
}

/** Отсутствия людей стола: переиспользуем теплокарту с экрана ёмкости. */
export function AbsenceStrip({ employeeIds, compact = false }: Props) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [quarter, setQuarter] = useState(Math.floor(now.getMonth() / 3) + 1);

  const absences = useAbsences();
  const employees = useEmployees();

  const wanted = new Set(Object.values(employeeIds));
  const rows = (employees.data ?? [])
    .filter((e) => wanted.has(e.id))
    .map((e) => ({ id: e.id, display_name: e.display_name }));

  if (compact) {
    const years = [year - 1, year, year + 1];
    return (
      <>
        <div className="tdc-abs-head">
          <h2 className="rpc-card-title">Отсутствия</h2>
          <div className="wr-field tdc-field is-period">
            <label className="wr-field-label" htmlFor="tdc-abs-period">Период</label>
            <Select
              id="tdc-abs-period"
              variant="borderless"
              value={`${year}-${quarter}`}
              onChange={(value: string) => {
                const [y, q] = value.split('-').map(Number);
                setYear(y);
                setQuarter(q);
              }}
              options={years.flatMap((y) => QUARTERS.map((q) => ({ value: `${y}-${q}`, label: `${y} · Q${q}` })))}
              popupMatchSelectWidth={false}
            />
          </div>
        </div>
        {rows.length ? (
          <AbsenceHeatmap
            compact
            year={year}
            quarter={quarter}
            employees={rows}
            absences={absences.data ?? []}
          />
        ) : (
          <p className="tdc-empty">Выберите команды или людей</p>
        )}
      </>
    );
  }

  if (!rows.length) {
    return <Empty description="Выберите команды или людей" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <Space orientation="vertical" size={10} style={{ width: '100%' }}>
      <Space size={8}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>Период</Typography.Text>
        <Select
          size="small"
          value={year}
          onChange={setYear}
          options={[year - 1, year, year + 1].map((y) => ({ value: y, label: String(y) }))}
          style={{ width: 90 }}
        />
        <Select
          size="small"
          value={quarter}
          onChange={setQuarter}
          options={QUARTERS.map((q) => ({ value: q, label: `Q${q}` }))}
          style={{ width: 80 }}
        />
      </Space>
      <div style={{ overflowX: 'auto' }}>
        <AbsenceHeatmap
          year={year}
          quarter={quarter}
          employees={rows}
          absences={absences.data ?? []}
        />
      </div>
    </Space>
  );
}
