import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, App, Button, Card, Empty, List, Modal, Radio, Select, Space, Spin, Table, Tag, Typography,
} from 'antd';
import { employeeMergeApi } from '../../api/employeeMerge';
import type { MergeCard } from '../../api/employeeMerge';
import { getEmployees } from '../../api/employees';

const { Text, Paragraph } = Typography;

function fmtDay(iso: string | null): string {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

function CardLine({ card }: { card: MergeCard }) {
  return (
    <Space orientation="vertical" size={0}>
      <Text strong>{card.display_name}</Text>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {card.jira_username ?? 'логин неизвестен'} · {card.hours} ч ·{' '}
        {card.teams.length ? card.teams.join(', ') : 'без команды'}
      </Text>
    </Space>
  );
}

/** Окно подтверждения: что переедет и что мешает. */
function MergeModal({
  pair, onClose,
}: { pair: { keep: string; drop: string } | null; onClose: () => void }) {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const preview = useQuery({
    queryKey: ['admin', 'employee-merge', 'preview', pair?.keep, pair?.drop],
    queryFn: () => employeeMergeApi.preview(pair!.keep, pair!.drop),
    enabled: pair !== null,
    gcTime: 0,
  });
  const merge = useMutation({
    mutationFn: () => employeeMergeApi.merge(pair!.keep, pair!.drop),
    onSuccess: (res) => {
      onClose();
      // Удалённой карточки больше нет — предпросмотр не перечитываем.
      qc.removeQueries({ queryKey: ['admin', 'employee-merge', 'preview'] });
      // Объединение меняет часы, составы и задачи во всех разделах.
      qc.invalidateQueries();
      notification.success({ title: `Карточки объединены: ${res.keep.display_name}` });
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось объединить', description: e.message }),
  });
  const data = preview.data;
  const blocked = (data?.blockers.length ?? 0) > 0;

  return (
    <Modal
      open={pair !== null}
      title="Объединить карточки сотрудника"
      onCancel={onClose}
      okText="Объединить"
      okButtonProps={{ danger: true, disabled: !data || blocked, loading: merge.isPending }}
      onOk={() => merge.mutate()}
      cancelText="Отмена"
      width={620}
      destroyOnHidden
    >
      {preview.isLoading && <Spin />}
      {preview.isError && <Alert type="error" showIcon title={(preview.error as Error).message} />}
      {data && (
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Text type="secondary">Остаётся</Text>
            <div><CardLine card={data.keep} /></div>
          </div>
          <div>
            <Text type="secondary">Вливается и удаляется</Text>
            <div><CardLine card={data.drop} /></div>
          </div>
          {blocked ? (
            <Alert type="warning" showIcon title="Объединить пока нельзя" description={data.blockers.join(' ')} />
          ) : (
            <>
              <Text>К оставшейся карточке перейдёт:</Text>
              {data.moves.length ? (
                <List
                  size="small"
                  dataSource={data.moves}
                  renderItem={(m) => (
                    <List.Item style={{ padding: '2px 0' }}>
                      <Text>{m.label}</Text><Text strong>{m.count}</Text>
                    </List.Item>
                  )}
                />
              ) : <Text type="secondary">у удаляемой карточки нет данных</Text>}
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                Учётка удаляемой карточки запомнится: синхронизация будет относить её часы и задачи к
                оставшейся, двойник больше не появится. Отменить объединение нельзя — сначала сделайте
                выгрузку базы.
              </Paragraph>
            </>
          )}
        </Space>
      )}
    </Modal>
  );
}

/** Группа похожих карточек: какую оставить — выбирает человек. */
function SuggestionGroup({
  cards, onMerge,
}: { cards: MergeCard[]; onMerge: (keep: string, drop: string) => void }) {
  // Первой сервер ставит карточку с самым свежим списанием — под ней человек работает сейчас.
  const [keep, setKeep] = useState(cards[0].id);
  return (
    <Table<MergeCard>
      size="small"
      rowKey="id"
      pagination={false}
      dataSource={cards}
      columns={[
        {
          title: 'Оставить', width: 90,
          render: (_, c) => <Radio checked={keep === c.id} onChange={() => setKeep(c.id)} />,
        },
        {
          title: 'Сотрудник',
          render: (_, c) => (
            <Space orientation="vertical" size={0}>
              <Text>{c.display_name}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {c.jira_username ?? 'логин неизвестен'}{c.email ? ` · ${c.email}` : ''}
              </Text>
            </Space>
          ),
        },
        {
          title: 'Команды',
          render: (_, c) => (c.teams.length
            ? c.teams.map((t) => <Tag key={t}>{t}</Tag>)
            : <Text type="secondary">без команды</Text>),
        },
        { title: 'Часов', dataIndex: 'hours', width: 90, align: 'right' as const },
        {
          title: 'Списания', width: 190,
          render: (_, c) => (c.worklogs
            ? `${fmtDay(c.first_worklog)} – ${fmtDay(c.last_worklog)}`
            : <Text type="secondary">нет</Text>),
        },
        {
          title: '', width: 170,
          render: (_, c) => (c.id === keep ? null : (
            <Button size="small" onClick={() => onMerge(keep, c.id)}>Влить в выбранную</Button>
          )),
        },
      ]}
    />
  );
}

export default function EmployeeMergeTab() {
  const [pair, setPair] = useState<{ keep: string; drop: string } | null>(null);
  const [manual, setManual] = useState<{ keep?: string; drop?: string }>({});
  const suggestions = useQuery({
    queryKey: ['admin', 'employee-merge', 'suggestions'],
    queryFn: () => employeeMergeApi.suggestions(),
  });
  const employees = useQuery({ queryKey: ['employees'], queryFn: () => getEmployees() });
  const options = (employees.data ?? [])
    .map((e) => {
      const hint = e.email ?? e.team;
      return { value: e.id, label: `${e.display_name}${hint ? ` (${hint})` : ''}` };
    })
    .sort((a, b) => a.label.localeCompare(b.label, 'ru'));
  const groups = suggestions.data ?? [];

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        title="Один человек — две карточки"
        description={
          'После переезда на новую Jira часть сотрудников списывает часы под другой учёткой, чем та, '
          + 'к которой привязана их карточка. Вторая карточка появляется без команды и роли, и её часы '
          + 'не попадают в разделы команды. Объединение переносит всё на оставшуюся карточку.'
        }
      />
      <Card size="small" title="Похожие карточки — одинаковые фамилия и имя">
        {suggestions.isLoading && <Spin />}
        {suggestions.isError && <Alert type="error" showIcon title="Не удалось загрузить список" />}
        {suggestions.isSuccess && !groups.length && <Empty description="Похожих карточек нет" />}
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          {groups.map((g) => (
            <SuggestionGroup
              key={g.cards.map((c) => c.id).join()}
              cards={g.cards}
              onMerge={(keep, drop) => setPair({ keep, drop })}
            />
          ))}
        </Space>
        {groups.length > 0 && (
          <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            Совпадение имени — только подсказка: у однофамильцев с разным отчеством это могут быть разные
            люди. Сверьте логин, команду и даты списаний.
          </Paragraph>
        )}
      </Card>
      <Card size="small" title="Другая пара">
        <Space wrap>
          <Select
            showSearch optionFilterProp="label" style={{ width: 340 }} placeholder="Оставить"
            options={options} value={manual.keep} onChange={(keep) => setManual((m) => ({ ...m, keep }))}
          />
          <Select
            showSearch optionFilterProp="label" style={{ width: 340 }} placeholder="Влить и удалить"
            options={options} value={manual.drop} onChange={(drop) => setManual((m) => ({ ...m, drop }))}
          />
          <Button
            disabled={!manual.keep || !manual.drop || manual.keep === manual.drop}
            onClick={() => setPair({ keep: manual.keep!, drop: manual.drop! })}
          >
            Проверить и объединить
          </Button>
        </Space>
      </Card>
      <MergeModal pair={pair} onClose={() => setPair(null)} />
    </Space>
  );
}
