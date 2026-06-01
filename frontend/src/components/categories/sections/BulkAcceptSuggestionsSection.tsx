import { useState } from 'react';
import { App, Button, Checkbox, List, Space, Statistic, Tag, Typography } from 'antd';
import { useBulkPreview, useBulkAcceptSuggestions } from '../../../hooks/useBulkTriage';
import { useCategories } from '../../../hooks/useCategories';
import type { BulkFilter, BulkPreviewItem } from '../../../types/api';

const { Text } = Typography;

type Props = {
  selectedTeams: string[];
  scopeProjectKeys: string[];
  onApplied: () => void;
};

export default function BulkAcceptSuggestionsSection({
  selectedTeams, scopeProjectKeys, onApplied,
}: Props) {
  const { message, modal } = App.useApp();
  const { labels: categoryLabels } = useCategories();
  const [onlyUnverified, setOnlyUnverified] = useState(true);
  const [preview, setPreview] = useState<{ total: number; truncated: boolean; items: BulkPreviewItem[] } | null>(null);
  const previewMut = useBulkPreview();
  const acceptMut = useBulkAcceptSuggestions();

  const buildFilters = (): BulkFilter => ({
    project_keys: scopeProjectKeys.length > 0 ? scopeProjectKeys : undefined,
    teams: selectedTeams.length > 0 ? selectedTeams : undefined,
    only_no_assigned: true,
    only_unverified: onlyUnverified,
  });

  const runPreview = async () => {
    const res = await previewMut.mutateAsync({ filters: buildFilters(), limit: 200 });
    setPreview(res);
  };

  const withSuggestion = preview?.items.filter(i => !!i.category) ?? [];

  const runAccept = () => {
    if (!preview) return;
    modal.confirm({
      title: `Принять ${withSuggestion.length} подсказок?`,
      content: 'Системная подсказка станет назначенной категорией и пометится подтверждённой. Задачи без подсказки пропустятся.',
      okText: 'Принять',
      cancelText: 'Отмена',
      onOk: async () => {
        const res = await acceptMut.mutateAsync({ filters: buildFilters() });
        message.success(`Принято: ${res.applied}, пропущено без подсказки: ${res.skipped_no_suggestion}`);
        setPreview(null);
        onApplied();
      },
    });
  };

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Text>
        Применяет подсказки резолвера (правила и предки) к задачам без
        собственной категории. Используется на старте, чтобы не разбирать
        вручную задачи, которые система уже классифицировала автоматически.
      </Text>
      <Checkbox checked={onlyUnverified} onChange={(e) => setOnlyUnverified(e.target.checked)}>
        Только непроверенные («К разбору»)
      </Checkbox>
      <Space>
        <Button type="primary" onClick={runPreview} loading={previewMut.isPending}>
          Предпросмотр
        </Button>
        <Button
          type="primary"
          disabled={!preview || withSuggestion.length === 0}
          loading={acceptMut.isPending}
          onClick={runAccept}
        >
          Принять ({withSuggestion.length})
        </Button>
      </Space>
      {preview && (
        <>
          <Space size={32}>
            <Statistic title="Кандидатов всего" value={preview.total} />
            <Statistic title="С подсказкой" value={withSuggestion.length} />
            <Statistic title="Без подсказки" value={preview.items.length - withSuggestion.length} />
          </Space>
          <List
            size="small"
            bordered
            dataSource={preview.items}
            renderItem={(it) => (
              <List.Item>
                <Tag>{it.project_key}</Tag>
                <Text strong style={{ marginRight: 8 }}>{it.key}</Text>
                <Text ellipsis style={{ flex: 1 }}>{it.summary}</Text>
                {it.category
                  ? <Tag color="cyan">{categoryLabels[it.category] || it.category}</Tag>
                  : <Tag>нет подсказки</Tag>}
              </List.Item>
            )}
            style={{ maxHeight: 320, overflow: 'auto' }}
          />
        </>
      )}
    </Space>
  );
}
