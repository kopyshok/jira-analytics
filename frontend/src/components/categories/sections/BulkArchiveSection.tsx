import { useState } from 'react';
import { App, Button, DatePicker, Radio, Select, Space, Statistic, Typography, List, Tag } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useBulkPreview, useBulkArchive } from '../../../hooks/useBulkTriage';
import type { BulkFilter, BulkPreviewItem } from '../../../types/api';

const { Text } = Typography;

type Props = {
  selectedTeams: string[];
  scopeProjectKeys: string[];
  onApplied: () => void;
};

export default function BulkArchiveSection({ selectedTeams, scopeProjectKeys, onApplied }: Props) {
  const { message, modal } = App.useApp();
  const [statuses, setStatuses] = useState<string[]>(['Закрыто', 'Отменено']);
  const [olderThan, setOlderThan] = useState<Dayjs | null>(dayjs().subtract(365, 'day'));
  const [categoryCode, setCategoryCode] = useState<'archive' | 'archive_target'>('archive');
  const [preview, setPreview] = useState<{ total: number; truncated: boolean; items: BulkPreviewItem[] } | null>(null);

  const previewMut = useBulkPreview();
  const archiveMut = useBulkArchive();

  const buildFilters = (): BulkFilter => ({
    project_keys: scopeProjectKeys.length > 0 ? scopeProjectKeys : undefined,
    teams: selectedTeams.length > 0 ? selectedTeams : undefined,
    statuses: statuses.length > 0 ? statuses : undefined,
    status_changed_before: olderThan ? olderThan.toISOString() : undefined,
  });

  const runPreview = async () => {
    const filters = buildFilters();
    const res = await previewMut.mutateAsync({ filters, limit: 200 });
    setPreview(res);
  };

  const runArchive = () => {
    if (!preview || preview.total === 0) return;
    modal.confirm({
      title: `Архивировать ${preview.total} задач?`,
      content: 'Им проставится архивная категория, флаг «В анализ» снимется. Откатить можно только вручную.',
      okText: 'Архивировать',
      okType: 'danger',
      cancelText: 'Отмена',
      onOk: async () => {
        const res = await archiveMut.mutateAsync({
          filters: buildFilters(),
          categoryCode,
        });
        message.success(`Архивировано: ${res.updated}, исключено из анализа: ${res.archived_ids.length}`);
        setPreview(null);
        onApplied();
      },
    });
  };

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Text>
        Фильтр запускается на стороне сервера. По командным фильтрам учитывается
        глобальная выборка команды.
      </Text>
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        <Text strong>Архивная категория</Text>
        <Radio.Group value={categoryCode} onChange={(e) => setCategoryCode(e.target.value as 'archive' | 'archive_target')}>
          <Radio value="archive">Архив неактуальных задач</Radio>
          <Radio value="archive_target">Архив квартальных целей</Radio>
        </Radio.Group>
      </Space>
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        <Text strong>Статусы</Text>
        <Select
          mode="tags"
          value={statuses}
          onChange={setStatuses}
          style={{ width: '100%' }}
          placeholder="Например, Закрыто, Отменено"
        />
      </Space>
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        <Text strong>Статус не менялся с</Text>
        <DatePicker
          value={olderThan}
          onChange={setOlderThan}
          style={{ width: '100%' }}
          placeholder="Дата отсечки"
        />
      </Space>
      <Space>
        <Button type="primary" onClick={runPreview} loading={previewMut.isPending}>
          Предпросмотр
        </Button>
        <Button
          danger
          type="primary"
          disabled={!preview || preview.total === 0}
          loading={archiveMut.isPending}
          onClick={runArchive}
        >
          Архивировать {preview ? `(${preview.total})` : ''}
        </Button>
      </Space>
      {preview && (
        <>
          <Statistic title="Найдено задач" value={preview.total} suffix={preview.truncated ? '(показано первых 200)' : ''} />
          <List
            size="small"
            bordered
            dataSource={preview.items}
            renderItem={(it) => (
              <List.Item>
                <Tag>{it.project_key}</Tag>
                <Text strong style={{ marginRight: 8 }}>{it.key}</Text>
                <Text ellipsis style={{ flex: 1 }}>{it.summary}</Text>
                <Tag>{it.status}</Tag>
              </List.Item>
            )}
            style={{ maxHeight: 320, overflow: 'auto' }}
          />
        </>
      )}
    </Space>
  );
}
