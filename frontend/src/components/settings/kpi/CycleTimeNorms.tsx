import { useEffect, useMemo, useState } from 'react';
import { App, Button, Card, InputNumber, Space, Table, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CopyOutlined } from '@ant-design/icons';
import { useTeams } from '../../../hooks/useSync';
import { fetchNorms, saveNorms } from '../../../api/kpi';

const { Text } = Typography;
const QUARTERS = [1, 2, 3, 4] as const;

function currentQuarter(): number {
  return Math.floor(new Date().getMonth() / 3) + 1;
}

export default function CycleTimeNorms() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const { data: teams } = useTeams();

  const [year, setYear] = useState(new Date().getFullYear());
  const normsQuery = useQuery({
    queryKey: ['kpi-settings', 'norms', year],
    queryFn: () => fetchNorms(year),
  });

  // team -> quarter -> value; правится локально до нажатия «Сохранить».
  const [grid, setGrid] = useState<Record<string, Record<number, number | null>>>({});

  useEffect(() => {
    const next: Record<string, Record<number, number | null>> = {};
    for (const team of teams ?? []) {
      next[team] = { 1: null, 2: null, 3: null, 4: null };
    }
    for (const row of normsQuery.data ?? []) {
      if (!next[row.team]) next[row.team] = { 1: null, 2: null, 3: null, 4: null };
      next[row.team][row.quarter] = row.norm_value;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- гидратация локальной сетки из запроса
    setGrid(next);
  }, [teams, normsQuery.data]);

  const saveMut = useMutation({
    mutationFn: () => {
      // Отправляем и очищенные ячейки (`norm_value: null`) — иначе стёртый
      // норматив не удалялся бы на сервере и возвращался бы после
      // перезагрузки страницы (см. ревью, ВАЖНО 10).
      const items = Object.entries(grid).flatMap(([team, byQuarter]) => QUARTERS
        .map((q) => ({ team, year, quarter: q, norm_value: byQuarter[q] ?? null })));
      return saveNorms(items);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'norms', year] });
      // Норматив участвует в живом расчёте метрики Cycle Time — ведомость
      // должна пересчитаться (см. ревью, ВАЖНО 7).
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Нормативы сохранены' });
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось сохранить', description: e.message }),
  });

  const setCell = (team: string, quarter: number, value: number | null) => {
    setGrid((g) => ({ ...g, [team]: { ...g[team], [quarter]: value } }));
  };

  // Копирует значение соседнего квартала влево в пустые ячейки выбранного
  // года — раньше цель всегда бралась от системной даты («сегодняшний
  // квартал»), поэтому заполнить прошлый год или прошлый квартал текущего
  // года было нечем (см. ревью, мелочи).
  const copyFromPrevious = () => {
    setGrid((g) => {
      const next: typeof g = {};
      for (const [team, byQuarter] of Object.entries(g)) {
        const updated = { ...byQuarter };
        for (const q of [2, 3, 4] as const) {
          if (updated[q] == null && byQuarter[q - 1] != null) updated[q] = byQuarter[q - 1];
        }
        next[team] = updated;
      }
      return next;
    });
  };

  const columns = useMemo(() => [
    { title: 'Команда', dataIndex: 'team', fixed: 'left' as const, width: 200 },
    ...QUARTERS.map((q) => ({
      title: `Q${q} ${year}${q === currentQuarter() && year === new Date().getFullYear() ? ' (текущий)' : ''}`,
      key: `q${q}`,
      width: 140,
      render: (_: unknown, r: { team: string }) => (
        <InputNumber
          style={{ width: 100 }}
          min={0}
          step={0.5}
          value={grid[r.team]?.[q] ?? null}
          placeholder="—"
          onChange={(v) => setCell(r.team, q, v)}
        />
      ),
    })),
  ], [year, grid]);

  return (
    <Card
      size="small"
      title="Норматив Cycle Time, дней"
      extra={(
        <Space>
          <InputNumber value={year} min={2020} max={2035} onChange={(v) => v && setYear(v)} style={{ width: 100 }} />
          <Button icon={<CopyOutlined />} onClick={copyFromPrevious}>
            Скопировать значения предыдущего квартала
          </Button>
          <Button type="primary" loading={saveMut.isPending} onClick={() => saveMut.mutate()}>
            Сохранить
          </Button>
        </Space>
      )}
    >
      {!teams || teams.length === 0 ? (
        <Text type="secondary">Команды не найдены — загрузите их в разделе «Синхронизация».</Text>
      ) : (
        <Table
          dataSource={teams.map((team) => ({ team, key: team }))}
          columns={columns}
          pagination={false}
          size="small"
          loading={normsQuery.isLoading}
          scroll={{ x: 'max-content' }}
        />
      )}
    </Card>
  );
}
