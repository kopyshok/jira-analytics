import { useEffect, useState } from 'react';
import { App, Button, Modal, Segmented, Select, Space, Table, Tag, Typography } from 'antd';
import type { PersonDecision, PersonRow } from '../../../api/jiraMigration';
import { useDcUserSearch, useSetDecision } from '../../../hooks/useJiraMigration';
import {
  PERSON_SOURCE_LABEL, PERSON_STATUS_COLOR, PERSON_STATUS_LABEL, candidateLabel, dcUserLabel,
  filterPeople, formatHours, hoursLeaving, matchedWorklogsLabel, personBindingText,
} from '../../../utils/jiraMigration';
import type { PeopleFilter } from '../../../utils/jiraMigration';

const { Paragraph, Text } = Typography;

const FILTERS: { value: PeopleFilter; label: string }[] = [
  { value: 'attention', label: 'Нужно решение' },
  { value: 'all', label: 'Все' },
  { value: 'by_hours', label: 'По списаниям' },
  { value: 'by_name', label: 'По ФИО' },
  { value: 'unbound', label: 'Без привязки' },
];

const SEARCH_DELAY_MS = 300;

interface PickUser {
  key: string;
  name: string | null;
  display_name: string;
  email?: string | null;
  active?: boolean;
  votes?: number;
}

function PersonModal({ row, onClose }: { row: PersonRow; onClose: () => void }) {
  const { notification } = App.useApp();
  const setDecision = useSetDecision();
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  // Выбранный хранится целиком: после выбора поиск сбрасывается и его может не быть в списке.
  const [picked, setPicked] = useState<PickUser | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [query]);
  const search = useDcUserSearch(debounced);

  const users: PickUser[] = [...row.candidates];
  for (const u of [...(search.data ?? []), ...(picked ? [picked] : [])]) {
    if (!users.some((c) => c.key === u.key)) users.push(u);
  }

  const save = (decision: PersonDecision | null) =>
    setDecision.mutate(
      { kind: 'person', item_key: row.employee_id, decision },
      {
        onSuccess: onClose,
        onError: (e) => notification.error({ title: 'Решение не сохранено', description: e.message }),
      },
    );

  const bind = () => {
    if (picked) save({ action: 'bind', key: picked.key, name: picked.name, display_name: picked.display_name });
  };

  const tooShort = query.trim().length < 2;
  let notFound: string = 'Никого не нашли';
  if (search.isError) notFound = search.error.message;
  else if (tooShort) notFound = 'Введите хотя бы две буквы';
  else if (query !== debounced || search.isFetching) notFound = 'Ищем…';

  return (
    <Modal open title={`Привязка: ${row.display_name}`} onCancel={onClose} footer={null} destroyOnHidden>
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Text type="secondary">
          Выберите пользователя новой Jira — из кандидатов или поиском по ФИО, логину либо почте.
          В поиске есть и неактивные учётные записи: у уволенных сотрудников остались списания.
        </Text>
        <Select
          style={{ width: '100%' }}
          showSearch={{ filterOption: false, onSearch: setQuery }}
          placeholder="ФИО, логин или почта"
          aria-label="Пользователь новой Jira"
          value={picked?.key}
          onChange={(key: string) => setPicked(users.find((u) => u.key === key) ?? null)}
          loading={search.isFetching}
          options={users.map((u) => ({
            value: u.key,
            label: u.votes ? `${dcUserLabel(u)} — ${matchedWorklogsLabel(u.votes)}` : dcUserLabel(u),
          }))}
          notFoundContent={notFound}
        />
        <Space wrap>
          <Button type="primary" disabled={!picked} loading={setDecision.isPending} onClick={bind}>
            Привязать
          </Button>
          <Button loading={setDecision.isPending} onClick={() => save({ action: 'unbind' })}>
            Оставить без привязки
          </Button>
          {row.decision && (
            <Button type="link" disabled={setDecision.isPending} onClick={() => save(null)}>
              Вернуть автоматический вариант
            </Button>
          )}
        </Space>
      </Space>
    </Modal>
  );
}

function BindingCell({ row }: { row: PersonRow }) {
  const final = row.final;
  const conflict = final?.source === 'conflict';
  const hint = final?.note ?? (final?.source === 'decision' ? PERSON_SOURCE_LABEL.decision : null);
  return (
    <Space orientation="vertical" size={0}>
      <span>
        {conflict && <Tag color="orange">Конфликт</Tag>}
        <Text type={final?.unresolved ? 'danger' : undefined}>{personBindingText(row)}</Text>
      </span>
      {hint && <Text type="secondary" style={{ fontSize: 12 }}>{hint}</Text>}
    </Space>
  );
}

interface Props {
  rows?: PersonRow[];
  readOnly: boolean;
}

export default function PeopleSection({ rows, readOnly }: Props) {
  const [filter, setFilter] = useState<PeopleFilter>('attention');
  const [editing, setEditing] = useState<PersonRow | null>(null);
  if (!rows) return null;
  const shown = filterPeople(rows, filter);

  return (
    <>
      <Paragraph type="secondary">
        Сотрудник находится в новой Jira по совпавшим списаниям (та же задача, то же время
        начала, та же длительность), а если списаний нет — по точному совпадению ФИО. Спорных,
        ненайденных и тех, кого не удалось поискать, выберите вручную или оставьте без привязки.
        Без привязки старая карточка останется без часов по перенесённым задачам: часы из новой
        Jira придут к новой карточке без команды — лучше найти и привязать учётку. Сколько часов
        уйдёт — в колонке «Часы уйдут к новой карточке». Один пользователь новой Jira может быть
        привязан только к одному сотруднику — если на него претендуют двое, у второго будет
        «Конфликт».
      </Paragraph>
      <Segmented<PeopleFilter> options={FILTERS} value={filter} onChange={setFilter} style={{ marginBottom: 12 }} />
      <Table<PersonRow>
        rowKey="employee_id"
        size="small"
        dataSource={shown}
        pagination={{ pageSize: 50, showSizeChanger: false }}
        locale={{ emptyText: filter === 'attention' ? 'Все сотрудники решены' : 'Таких сотрудников нет' }}
        columns={[
          { title: 'Сотрудник', dataIndex: 'display_name' },
          { title: 'Списаний в базе', dataIndex: 'worklogs', width: 110, align: 'right' },
          { title: 'Совпало', dataIndex: 'matched', width: 90, align: 'right' },
          {
            title: 'Как найден',
            dataIndex: 'status',
            width: 150,
            render: (status: PersonRow['status']) => (
              <Tag color={PERSON_STATUS_COLOR[status]}>{PERSON_STATUS_LABEL[status]}</Tag>
            ),
          },
          {
            title: 'Кандидаты',
            dataIndex: 'candidates',
            render: (candidates: PersonRow['candidates']) =>
              candidates.length === 0
                ? <Text type="secondary">—</Text>
                : candidates
                    .map((c) => `${candidateLabel(c)}${c.votes ? ` — ${matchedWorklogsLabel(c.votes)}` : ''}`)
                    .join('; '),
          },
          { title: 'Привязка', key: 'final', width: 280, render: (_: unknown, row) => <BindingCell row={row} /> },
          {
            title: 'Часы уйдут к новой карточке',
            key: 'hours_leaving',
            width: 130,
            align: 'right',
            render: (_: unknown, row) => {
              const leaving = hoursLeaving(row);
              return leaving > 0
                ? <Text type="danger">{formatHours(leaving)} ч</Text>
                : <Text type="secondary">—</Text>;
            },
          },
          {
            title: '',
            key: 'edit',
            width: 110,
            render: (_: unknown, row) => (
              <Button size="small" disabled={readOnly} onClick={() => setEditing(row)}>
                Изменить
              </Button>
            ),
          },
        ]}
      />
      {editing && <PersonModal row={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
