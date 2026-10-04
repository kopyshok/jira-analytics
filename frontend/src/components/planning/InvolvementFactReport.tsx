import { useMemo, useState } from 'react';
import { Alert, Empty, Modal, Select, Space, Spin, Table, Tooltip, Typography } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { useInvolvementFact } from '../../hooks/useInvolvementFact';
import { useTeams } from '../../hooks/useSync';
import type { InvolvementFactCell, InvolvementFactMonth } from '../../types/api';
import {
  FACT_FORMULA, LOGGED_OF_NORM_FORMULA, cellHint, factTableRows, lastCompletedQuarter,
  monthLabel, quarterOptions, type FactRow,
} from '../../utils/involvementFact';
import { formatInvolvement } from '../../utils/personalSettings';

const ROLE_NAMES: Record<string, string> = { analyst: 'Аналитик', dev: 'Разработчик' };

function HeaderHint({ title, hint }: { title: string; hint: string }) {
  return (
    <Space size={4}>
      {title}
      <Tooltip title={hint}>
        <QuestionCircleOutlined style={{ opacity: 0.6 }} aria-label={hint} />
      </Tooltip>
    </Space>
  );
}

function FactValue({ cell, strong }: { cell: InvolvementFactCell | undefined; strong: boolean }) {
  if (!cell) return <span>—</span>;
  return (
    <Tooltip title={cellHint(cell)}>
      <Typography.Text strong={strong}>{formatInvolvement(cell.fact)}</Typography.Text>
    </Tooltip>
  );
}

/**
 * Отчёт «Фактическая вовлечённость»: аналитики и разработчики выбранных команд,
 * факт по месяцам квартала, итог квартала, списано от нормы и среднее по роли.
 * Монтируется при открытии — выбор команд и квартала каждый раз начинается заново.
 */
export default function InvolvementFactReport({
  onClose, team,
}: {
  onClose: () => void;
  team: string | null;
}) {
  const { selectedTeams } = useGlobalTeamFilter();
  const { data: allTeams = [] } = useTeams();
  const teamOptions = useMemo(() => {
    const base = selectedTeams.length > 0 ? selectedTeams : allTeams;
    const list = team && !base.includes(team) ? [team, ...base] : base;
    return list.map((t) => ({ value: t, label: t }));
  }, [selectedTeams, allTeams, team]);

  const [teams, setTeams] = useState<string[]>(() => (team ? [team] : selectedTeams.slice(0, 1)));
  const [period, setPeriod] = useState<string>(() => {
    const q = lastCompletedQuarter(new Date());
    return `${q.year}-${q.quarter}`;
  });
  const periodOptions = useMemo(() => quarterOptions(new Date()), []);
  const [year, quarter] = period.split('-').map(Number);
  const { data, isLoading, isError, error } = useInvolvementFact(teams, { year, quarter });

  const months = data?.months ?? [];
  const monthOf = (list: InvolvementFactMonth[], m: number) => list.find((c) => c.month === m);

  const columns = [
    {
      title: 'Сотрудник',
      key: 'name',
      fixed: 'left' as const,
      render: (_: unknown, row: FactRow) => (row.kind === 'person'
        ? row.name
        : <Typography.Text strong>Среднее по роли · {row.people} чел.</Typography.Text>),
    },
    {
      title: 'Роль',
      key: 'role',
      render: (_: unknown, row: FactRow) => ROLE_NAMES[row.role] ?? row.role,
    },
    ...months.map((m) => ({
      title: <HeaderHint title={monthLabel(m)} hint={FACT_FORMULA} />,
      key: `m${m}`,
      align: 'right' as const,
      render: (_: unknown, row: FactRow) => (
        <FactValue cell={monthOf(row.months, m)} strong={row.kind === 'role'} />
      ),
    })),
    {
      title: <HeaderHint title="Итог квартала" hint={`${FACT_FORMULA}, за весь квартал`} />,
      key: 'total',
      align: 'right' as const,
      render: (_: unknown, row: FactRow) => <FactValue cell={row.total} strong />,
    },
    {
      title: <HeaderHint title="Списано от нормы" hint={LOGGED_OF_NORM_FORMULA} />,
      key: 'logged',
      align: 'right' as const,
      render: (_: unknown, row: FactRow) => (
        <Tooltip title={`Списано ${Math.round(row.total.logged_hours)} ч при норме ${Math.round(row.total.norm_hours)} ч`}>
          <Typography.Text strong={row.kind === 'role'}>
            {formatInvolvement(row.total.logged_of_norm)}
          </Typography.Text>
        </Tooltip>
      ),
    },
  ];

  return (
    <Modal
      open
      title="Фактическая вовлечённость"
      onCancel={onClose}
      footer={null}
      width={1000}
      destroyOnHidden
    >
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          Факт — доля часов на задачах вида «Проекты и развитие» среди всех списанных часов
          сотрудника. Человек относится к команде по участию на дату списания. В отчёте —
          аналитики и разработчики; сотрудники без роли не показываются.
        </Typography.Text>
        <Space wrap>
          <Select
            mode="multiple"
            style={{ minWidth: 320, maxWidth: 560 }}
            placeholder="Команды"
            value={teams}
            onChange={setTeams}
            options={teamOptions}
            showSearch
            optionFilterProp="label"
            maxTagCount="responsive"
            aria-label="Команды"
          />
          <Select
            style={{ width: 170 }}
            value={period}
            onChange={setPeriod}
            options={periodOptions}
            aria-label="Квартал"
          />
        </Space>
        {teams.length === 0 ? (
          <Empty description="Выберите команду" />
        ) : isLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
        ) : isError ? (
          <Alert type="error" showIcon title="Не удалось посчитать" description={(error as Error).message} />
        ) : (
          (data?.teams ?? []).map((t) => (
            <div key={t.team}>
              {(data?.teams.length ?? 0) > 1 && <Typography.Title level={5}>{t.team}</Typography.Title>}
              {t.roles.length === 0 ? (
                <Empty description="Нет аналитиков и разработчиков со списаниями или нормой за квартал" />
              ) : (
                <Table<FactRow>
                  rowKey="key"
                  size="small"
                  pagination={false}
                  dataSource={factTableRows(t)}
                  columns={columns}
                  scroll={{ x: 'max-content' }}
                />
              )}
            </div>
          ))
        )}
      </Space>
    </Modal>
  );
}
