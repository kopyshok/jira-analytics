import { useRef, useState } from 'react';
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import {
  Button, Card, Checkbox, Dropdown, InputNumber, Space, Switch, Table, Tag, Tooltip, Typography,
} from 'antd';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  roundHours, type DeskDeveloper, type DeskIssue, type FlagCode,
} from '../../api/teamDesk';
import { FlagList } from './FlagChip';
import { HoursScale } from './HoursScale';
import { IssueKey, StatusTag } from './IssueCells';
import { StatusCounters } from './StatusCounters';
import { inQueueScope, type QueueScope } from './queueFilter';

interface Row extends Partial<DeskIssue> {
  rowKey: string;
  isGroup?: boolean;
  groupName?: string;
  groupCount?: number;
  groupInDev?: number;
  groupDeveloperId?: string;
  groupStatusCounts?: Record<string, number>;
  /** Имя, если подзадачу делает не владелец группы. */
  otherDeveloper?: string | null;
  children?: Row[];
}

interface Props {
  title: string;
  developers: DeskDeveloper[];
  issues: DeskIssue[];
  overrunPct: number;
  jiraBaseUrl?: string;
  /** bar — «факт / оценка» полосой, centered — недобор влево, перебор вправо. */
  scale?: 'bar' | 'centered';
  /** Оставить только задачи с этим признаком (и их родителей). */
  flagFilter?: FlagCode | null;
  /** Оставить только задачи в этом статусе (и их родителей). */
  statusFilter?: string | null;
  /** Оставить только одного разработчика — клик по карточке или строке сводки. */
  onlyDeveloper?: string | null;
  /** Разложенная строка очереди: оставить только её задачи. */
  queueScope?: QueueScope;
  /** Правка дневной нормы «резиновой» задачи; не задана — колонки нет. */
  onDailyRate?: (issueId: string, hours: number | null) => void;
  /** Пояснение слева от счётчика задач в шапке карточки. */
  hint?: string;
  /** Счётчики статусов в строке разработчика; пусто — не показывать. */
  statuses?: string[];
  statusGroups?: Record<string, string[]>;
  onStatusFilter?: (developerId: string, status: string | null) => void;
  /** Колонки, которые тимлид убрал с экрана. */
  hiddenColumns?: string[];
  /** Группировать по разработчикам; выключено — сплошной список. */
  groupByDeveloper?: boolean;
  /** Оставить задачи с этими спринтами (по последнему) и релизами. */
  sprintFilter?: string[];
  releaseFilter?: string[];
  /** Ширины колонок, растянутых мышкой. Пусто — ширина по умолчанию. */
  columnWidths?: Record<string, number>;
  onColumnWidthsChange?: (widths: Record<string, number>) => void;
  /** Настройка рабочего места: какие колонки показывать и группировать ли. */
  onHiddenColumnsChange?: (hidden: string[]) => void;
  onGroupByDeveloperChange?: (value: boolean) => void;
  /** Перечитать с Jira задачи, которые сейчас в списке. */
  onRefreshVisible?: (keys: string[]) => void;
  refreshing?: boolean;
}

/** Подписи колонок для настройки видимости. «Задача» не убирается. */
const COLUMN_LABELS: [string, string][] = [
  ['developer', 'Разработчик'],
  ['status', 'Статус'],
  ['sprint', 'Спринт'],
  ['release', 'Релиз'],
  ['est', 'Оценка'],
  ['daily_rate', 'DevForDay'],
  ['fact', 'Факт'],
  ['left', 'Осталось'],
  ['scale', 'Шкала'],
  ['days', 'Дней'],
  ['flags', 'Замечания'],
];

/** Значение колонки для сортировки. Пусто — строка уходит в конец. */
const SORT_VALUE: Record<string, (row: Row) => string | number | null> = {
  task: (r) => r.summary ?? '',
  developer: (r) => r.developer_name ?? '',
  status: (r) => r.status ?? '',
  sprint: (r) => r.sprint ?? '',
  release: (r) => r.release ?? '',
  est: (r) => r.est_hours ?? null,
  daily_rate: (r) => r.daily_rate ?? null,
  fact: (r) => r.fact_hours ?? null,
  left: (r) => (r.est_hours == null ? null : r.est_hours - (r.fact_hours ?? 0)),
  scale: (r) => (r.est_hours ? (r.fact_hours ?? 0) / r.est_hours : null),
  days: (r) => r.days_in_status ?? null,
  flags: (r) => r.flags?.length ?? 0,
};

type SortState = { key: string; order: 'ascend' | 'descend' } | null;

interface HeaderCellProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  columnKey?: string;
  columnWidth?: number;
  onResize?: (key: string, width: number) => void;
  onResizeEnd?: () => void;
}

/** Заголовок колонки с «ручкой» справа: тянешь мышкой — меняется ширина. */
function ResizableHeaderCell({
  columnKey, columnWidth, onResize, onResizeEnd, children, ...rest
}: HeaderCellProps) {
  if (!columnKey || !onResize) return <th {...rest}>{children}</th>;
  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const cell = (e.currentTarget as HTMLElement).closest('th');
    const startX = e.clientX;
    const startWidth = columnWidth ?? cell?.getBoundingClientRect().width ?? 120;
    const move = (ev: MouseEvent) =>
      // Меньше 60 не даём: заголовок перестаёт читаться.
      onResize(columnKey, Math.max(60, Math.round(startWidth + ev.clientX - startX)));
    const stop = () => {
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', stop);
      onResizeEnd?.();
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', stop);
  };
  return (
    <th {...rest} style={{ ...rest.style, position: 'relative' }}>
      {children}
      <span
        onMouseDown={startDrag}
        onClick={(e) => e.stopPropagation()}
        style={{
          // Держим ручку внутри ячейки: у колонок с обрезкой края скрыты.
          position: 'absolute', top: 0, right: 0, bottom: 0, width: 8,
          cursor: 'col-resize', zIndex: 1, touchAction: 'none',
        }}
      />
    </th>
  );
}

/** Сортировка задач внутри уровня; подзадачи сортируются тем же порядком. */
function sortRows(rows: Row[], sort: SortState): Row[] {
  if (!sort || !SORT_VALUE[sort.key]) return rows;
  const value = SORT_VALUE[sort.key];
  const sign = sort.order === 'descend' ? -1 : 1;
  const sorted = [...rows].sort((a, b) => {
    const va = value(a);
    const vb = value(b);
    // Пустые значения всегда внизу — иначе «по оценке» сверху окажутся прочерки.
    if (va == null || va === '') return vb == null || vb === '' ? 0 : 1;
    if (vb == null || vb === '') return -1;
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sign;
    return String(va).localeCompare(String(vb), 'ru') * sign;
  });
  return sorted.map((row) =>
    row.children ? { ...row, children: sortRows(row.children, sort) } : row,
  );
}

/**
 * Список задач, сгруппированный по разработчикам. Одна и та же таблица во всех
 * трёх раскладках: колонки «Разработчик» нет — имя стоит в строке группы.
 */
export function GroupedIssues({
  title, developers, issues, overrunPct, jiraBaseUrl,
  scale = 'bar', flagFilter = null, statusFilter = null,
  onlyDeveloper = null, queueScope = null, onDailyRate, hint = '',
  statuses = [], statusGroups, onStatusFilter,
  hiddenColumns = [], groupByDeveloper = true,
  sprintFilter = [], releaseFilter = [],
  columnWidths = {}, onColumnWidthsChange,
  onHiddenColumnsChange, onGroupByDeveloperChange, onRefreshVisible, refreshing = false,
}: Props) {
  const [sort, setSort] = useState<SortState>(null);
  // Пока тянут мышкой, ширина живёт на экране; в профиль уходит один раз,
  // когда кнопку отпустили — иначе на каждый пиксель шёл бы запрос.
  const [draggedWidths, setDraggedWidths] = useState<Record<string, number> | null>(null);
  // Обработчики тяги живут с момента нажатия кнопки, поэтому итог берём из
  // ссылки, а не из состояния: в замыкании оно так и осталось бы пустым.
  const draggedRef = useRef<Record<string, number> | null>(null);
  const widths = draggedWidths ?? columnWidths;
  // Люди развёрнуты по умолчанию, задачи — свёрнуты; здесь только отклонения
  // от этого правила, чтобы не пересобирать состояние на каждой загрузке.
  const [toggled, setToggled] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setToggled((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });

  const childrenOf = new Map<string, DeskIssue[]>();
  const ids = new Set(issues.map((i) => i.id));
  issues.forEach((issue) => {
    if (issue.parent_id && ids.has(issue.parent_id)) {
      const list = childrenOf.get(issue.parent_id) ?? [];
      list.push(issue);
      childrenOf.set(issue.parent_id, list);
    }
  });

  // Фильтры складываются: строка остаётся, если под оба условия попадает она
  // сама либо её подзадача — иначе подзадача осталась бы без родителя.
  const hit = (issue: DeskIssue): boolean =>
    (!flagFilter || issue.flags.includes(flagFilter)) &&
    (!statusFilter || issue.status === statusFilter) &&
    (!sprintFilter.length || (!!issue.sprint && sprintFilter.includes(issue.sprint))) &&
    (!releaseFilter.length || (!!issue.release && releaseFilter.includes(issue.release))) &&
    inQueueScope(issue, queueScope);

  const matches = (issue: DeskIssue): boolean =>
    hit(issue) || (childrenOf.get(issue.id) ?? []).some(hit);

  const toRow = (issue: DeskIssue, ownerId?: string | null): Row => {
    const kids = (childrenOf.get(issue.id) ?? []).map((kid) => toRow(kid, ownerId));
    return {
      ...issue,
      rowKey: issue.id,
      otherDeveloper:
        ownerId && issue.developer_id && issue.developer_id !== ownerId
          ? issue.developer_name
          : null,
      children: kids.length ? kids : undefined,
    };
  };

  const data: Row[] = [];
  if (groupByDeveloper) {
    developers
      .filter((dev) => !onlyDeveloper || dev.developer_id === onlyDeveloper)
      .forEach((dev) => {
        const own = issues
          .filter(
            (i) => i.developer_id === dev.developer_id && !(i.parent_id && ids.has(i.parent_id)),
          )
          .filter(matches);
        if (!own.length) return;
        data.push({
          rowKey: `group-${dev.developer_id}`,
          isGroup: true,
          groupName: dev.display_name ?? 'Без имени',
          groupCount: own.length,
          groupInDev: dev.in_dev,
          groupDeveloperId: dev.developer_id,
          groupStatusCounts: dev.status_counts ?? {},
          est_hours: dev.est_hours,
          fact_hours: dev.fact_hours,
          children: sortRows(own.map((i) => toRow(i, dev.developer_id)), sort),
        });
      });
  } else {
    // Сплошной список: группировка по людям выключена, сортировка идёт по
    // всем задачам сразу, а имя разработчика показывается колонкой.
    const flat = issues
      .filter((i) => !(i.parent_id && ids.has(i.parent_id)))
      .filter((i) => !onlyDeveloper || i.developer_id === onlyDeveloper)
      .filter(matches)
      .map((i) => toRow(i, null));
    data.push(...sortRows(flat, sort));
  }

  const countRows = (rows: Row[]): number =>
    rows.reduce(
      (n, row) => n + (row.isGroup ? 0 : 1) + countRows(row.children ?? []),
      0,
    );
  // Ключи задач на экране — их и перечитываем по кнопке.
  const collectKeys = (rows: Row[]): string[] =>
    rows.flatMap((row) => [
      ...(row.isGroup || !row.key ? [] : [row.key]),
      ...collectKeys(row.children ?? []),
    ]);
  const visibleKeys = collectKeys(data);

  const shown = groupByDeveloper
    ? data.reduce((n, g) => n + (g.children?.length ?? 0), 0)
    : countRows(data);

  const expandableKeys: string[] = [];
  const collect = (rows: Row[]) =>
    rows.forEach((row) => {
      if (row.children?.length) {
        expandableKeys.push(row.rowKey);
        collect(row.children);
      }
    });
  collect(data);
  const expandedRowKeys = expandableKeys.filter(
    (key) => key.startsWith('group-') !== toggled.has(key),
  );

  const allColumns: ColumnsType<Row> = [
    {
      title: 'Задача',
      key: 'task',
      render: (_, row) =>
        row.isGroup ? (
          <>
            <Typography.Text strong>
              {row.groupName}{' '}
              <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
                · {row.groupCount} задач · {row.groupInDev} у него
              </Typography.Text>
            </Typography.Text>
            {statuses.length > 0 && (
              <div style={{ marginTop: 5 }}>
                <StatusCounters
                  counts={row.groupStatusCounts ?? {}}
                  statuses={statuses}
                  statusGroups={statusGroups}
                  selected={statusFilter}
                  onSelect={
                    onStatusFilter
                      ? (status) => onStatusFilter(row.groupDeveloperId!, status)
                      : undefined
                  }
                />
              </div>
            )}
          </>
        ) : (
          <span>
            <IssueKey issueKey={row.key!} jiraBaseUrl={jiraBaseUrl} /> {row.summary}
            {row.is_analysis && <Tag style={{ marginLeft: 6 }}>тех. анализ</Tag>}
            {row.daily_rate ? (
              <Tooltip title={`В очередь идёт по ${row.daily_rate} ч в день, а не весь остаток`}>
                <Tag color="geekblue" style={{ marginLeft: 6 }}>резиновая</Tag>
              </Tooltip>
            ) : null}
            {row.otherDeveloper && (
              <Typography.Text type="secondary"> · {row.otherDeveloper}</Typography.Text>
            )}
          </span>
        ),
    },
    ...(groupByDeveloper
      ? []
      : [{
          title: 'Разработчик',
          key: 'developer',
          width: 140,
          ellipsis: true,
          render: (_: unknown, row: Row) => row.developer_name ?? '—',
        }]),
    {
      title: 'Статус',
      key: 'status',
      width: 150,
      ellipsis: true,
      render: (_, row) =>
        row.isGroup ? null : <StatusTag status={row.status!} group={row.status_group!} />,
    },
    {
      title: 'Спринт',
      key: 'sprint',
      width: 148,
      ellipsis: true,
      render: (_, row) => {
        if (row.isGroup || !row.sprint) return row.isGroup ? null : '—';
        // Задача переходящая — в колонке последний спринт, остальные подсказкой.
        const all = row.sprints ?? [];
        return (
          <Tooltip
            title={
              <div>
                {(all.length ? all : [row.sprint]).map((name) => (
                  <div key={name}>{name}</div>
                ))}
              </div>
            }
          >
            <span style={{ whiteSpace: 'nowrap' }}>
              <Tag style={{ marginInlineEnd: 0 }}>{row.sprint}</Tag>
              {all.length > 1 && (
                <Typography.Text type="secondary"> +{all.length - 1}</Typography.Text>
              )}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: 'Релиз',
      key: 'release',
      width: 132,
      ellipsis: true,
      render: (_, row) => {
        if (row.isGroup) return null;
        if (!row.release) return '—';
        return (
          <Tooltip title={row.release}>
            <Tag style={{ marginInlineEnd: 0 }}>{row.release}</Tag>
          </Tooltip>
        );
      },
    },
    { title: 'Оценка', key: 'est', width: 82, align: 'right',
      render: (_, row) => (row.est_hours == null ? '—' : roundHours(row.est_hours)) },
    ...(onDailyRate
      ? [{
          title: (
            <Tooltip title="Часов в день по «резиновой» задаче: в очередь пойдёт норма за настроенное число дней, а не весь остаток">
              <span style={{ borderBottom: '1px dotted rgba(160,175,195,0.6)' }}>
                DevForDay
              </span>
            </Tooltip>
          ),
          key: 'daily_rate',
          width: 104,
          align: 'right' as const,
          render: (_: unknown, row: Row) =>
            row.isGroup ? null : (
              <InputNumber
                size="small"
                min={0}
                max={24}
                step={0.5}
                placeholder="—"
                value={row.daily_rate ?? null}
                onClick={(e) => e.stopPropagation()}
                onChange={(v) => onDailyRate(row.id!, v == null ? null : Number(v))}
                style={{ width: 84 }}
              />
            ),
        }]
      : []),
    {
      title: 'Факт',
      key: 'fact',
      width: 76,
      align: 'right',
      render: (_, row) => {
        const hours = roundHours(row.fact_hours ?? 0);
        const people = row.fact_by_person ?? [];
        if (row.isGroup || !people.length) return hours;
        return (
          <Tooltip
            title={
              <div>
                {people.map((p) => (
                  <div key={p.name}>
                    {p.name}: {roundHours(p.hours)} ч
                  </div>
                ))}
                {(row.alien_hours ?? 0) > 0 && (
                  <div style={{ marginTop: 4, opacity: 0.75 }}>
                    Часы других разработчиков в факт не входят
                  </div>
                )}
              </div>
            }
          >
            <span style={{ borderBottom: '1px dotted rgba(160,175,195,0.6)' }}>{hours}</span>
          </Tooltip>
        );
      },
    },
    {
      title: 'Осталось',
      key: 'left',
      width: 92,
      align: 'right',
      render: (_, row) => {
        if (row.est_hours == null) return '—';
        // Минус — перерасход: оценка исчерпана, работа продолжается.
        const left = roundHours(row.est_hours - (row.fact_hours ?? 0));
        return <span style={{ color: left < 0 ? '#ff6b6b' : undefined }}>{left}</span>;
      },
    },
    {
      title: scale === 'centered' ? 'Недобор / перебор' : 'Шкала',
      key: 'scale',
      width: 150,
      render: (_, row) => (
        <HoursScale
          fact={row.fact_hours ?? 0}
          est={row.est_hours ?? null}
          variant={scale}
          overrunPct={overrunPct}
        />
      ),
    },
    { title: 'Дней', key: 'days', width: 68, align: 'right',
      render: (_, row) => (row.isGroup ? null : row.days_in_status) },
    {
      title: 'Замечания',
      key: 'flags',
      width: 132,
      render: (_, row) =>
        row.isGroup ? null : (
          <FlagList
            issueId={row.id!}
            flags={row.flags ?? []}
            signatures={row.signatures ?? {}}
            reviewed={row.reviewed ?? []}
          />
        ),
    },
  ];

  // Сортируем сами: строки групп остаются на месте, порядок меняется только
  // у задач. Колонка «Задача» в сплошном списке сортируется по названию.
  const resizeColumn = (key: string, width: number) => {
    const next = { ...(draggedRef.current ?? widths), [key]: width };
    draggedRef.current = next;
    setDraggedWidths(next);
  };
  const saveWidths = () => {
    const next = draggedRef.current;
    draggedRef.current = null;
    if (next) onColumnWidthsChange?.(next);
    // Состояние не сбрасываем: пока сохранённые ширины не приехали обратно,
    // таблица должна остаться в том виде, в каком её отпустили.
  };

  const columns: ColumnsType<Row> = allColumns
    .filter((col) => !hiddenColumns.includes(String(col.key)))
    .map((col) => {
      const key = String(col.key);
      const width = widths[key] ?? (col.width as number | undefined);
      return {
        ...col,
        width,
        ...(SORT_VALUE[key]
          ? { sorter: true, sortOrder: sort?.key === key ? sort.order : null }
          : {}),
        ...(onColumnWidthsChange
          ? {
              onHeaderCell: () => ({
                columnKey: key,
                columnWidth: width,
                onResize: resizeColumn,
                onResizeEnd: saveWidths,
              }) as React.HTMLAttributes<HTMLElement>,
            }
          : {}),
      };
    });
  // Ширины заданы руками — таблица больше не обязана влезать в экран,
  // и тогда появляется горизонтальная прокрутка.
  const resized = Object.keys(widths).length > 0;
  const columnMenuItems: MenuProps['items'] = [
    ...COLUMN_LABELS
      .filter(([key]) => key !== 'developer' || !groupByDeveloper)
      .map(([key, label]) => ({
        key,
        label: <Checkbox checked={!hiddenColumns.includes(key)}>{label}</Checkbox>,
      })),
    ...(onColumnWidthsChange && resized
      ? [
          { type: 'divider' as const, key: 'w-div' },
          { key: '__reset_widths__', label: 'Сбросить ширину колонок' },
        ]
      : []),
  ];
  const totalWidth = columns.reduce(
    (sum, col) => sum + ((col.width as number | undefined) ?? 160), 0,
  );

  return (
    <Card
      size="small"
      title={title}
      extra={
        <Space size="small">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {hint ? `${hint} · ` : ''}{shown} задач
          </Typography.Text>
          {onGroupByDeveloperChange && (
            <Tooltip title="Группировать задачи по разработчикам">
              <Switch
                size="small"
                checked={groupByDeveloper}
                onChange={onGroupByDeveloperChange}
                checkedChildren="по людям"
                unCheckedChildren="списком"
              />
            </Tooltip>
          )}
          {onHiddenColumnsChange && (
            <Dropdown
              trigger={['click']}
              menu={{
                items: columnMenuItems,
                onClick: ({ key }) => {
                  if (key === '__reset_widths__') {
                    draggedRef.current = null;
                    setDraggedWidths(null);
                    onColumnWidthsChange?.({});
                    return;
                  }
                  onHiddenColumnsChange(
                    hiddenColumns.includes(key)
                      ? hiddenColumns.filter((k) => k !== key)
                      : [...hiddenColumns, key],
                  );
                },
              }}
            >
              <Button size="small" icon={<SettingOutlined />}>Колонки</Button>
            </Dropdown>
          )}
          {onRefreshVisible && (
            <Tooltip title="Перечитать с Jira только задачи из этого списка">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={refreshing}
                onClick={() => onRefreshVisible(visibleKeys)}
              >
                Обновить видимые
              </Button>
            </Tooltip>
          )}
        </Space>
      }
    >
      <Table<Row>
        size="small"
        rowKey="rowKey"
        dataSource={data}
        columns={columns}
        pagination={false}
        onChange={(_p, _f, sorter) => {
          const single = Array.isArray(sorter) ? sorter[0] : sorter;
          const key = single?.columnKey ? String(single.columnKey) : null;
          setSort(key && single?.order ? { key, order: single.order } : null);
        }}
        // По умолчанию прокрутки вправо нет: таблица ужимается под ширину
        // экрана, длинные значения обрезаются многоточием с подсказкой.
        // Колонки растянули мышкой — уважаем ширину и включаем прокрутку.
        tableLayout={resized ? 'fixed' : undefined}
        scroll={resized ? { x: totalWidth } : undefined}
        components={
          onColumnWidthsChange
            ? { header: { cell: ResizableHeaderCell } }
            : undefined
        }
        expandable={{
          expandedRowKeys,
          onExpand: (_, row) => toggle(row.rowKey),
        }}
        onRow={(row) =>
          row.isGroup
            ? { onClick: () => toggle(row.rowKey), style: { cursor: 'pointer' } }
            : {}
        }
      />
    </Card>
  );
}
