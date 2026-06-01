import { useMemo, useState } from 'react';
import { App, Button, Space, Transfer, Typography } from 'antd';
import type { TransferProps } from 'antd/es/transfer';
import { useBulkCascadeInherit } from '../../../hooks/useBulkTriage';
import { useCategories } from '../../../hooks/useCategories';

const { Text } = Typography;

export type EpicCandidate = {
  id: string;
  key: string;
  summary: string;
  assigned_category: string;
};

type Props = {
  candidates: EpicCandidate[];
  onApplied: () => void;
};

export default function BulkCascadeInheritSection({ candidates, onApplied }: Props) {
  const { message, modal } = App.useApp();
  const { labels: categoryLabels } = useCategories();
  const [targetKeys, setTargetKeys] = useState<string[]>([]);
  const cascadeMut = useBulkCascadeInherit();

  const dataSource = useMemo(
    () => candidates.map(c => ({
      key: c.id,
      title: `${c.key} — ${c.summary}`,
      description: categoryLabels[c.assigned_category] || c.assigned_category,
    })),
    [candidates, categoryLabels],
  );

  const onChange: TransferProps['onChange'] = (nextTargetKeys) => {
    setTargetKeys(nextTargetKeys.map(String));
  };

  const runCascade = () => {
    if (targetKeys.length === 0) return;
    modal.confirm({
      title: `Протянуть категорию ${targetKeys.length} эпиков на потомков?`,
      content: 'Категория эпика проставится всем его потомкам без своей категории. Ручные решения не трогаются.',
      okText: 'Применить',
      cancelText: 'Отмена',
      onOk: async () => {
        const res = await cascadeMut.mutateAsync({ ancestorIds: targetKeys });
        message.success(`Применено к ${res.applied} задачам, пропущено эпиков без категории: ${res.skipped_ancestors}`);
        setTargetKeys([]);
        onApplied();
      },
    });
  };

  if (candidates.length === 0) {
    return (
      <Text type="secondary">
        Нет эпиков с назначенной категорией в текущей выборке команды. Сначала
        присвойте категорию хотя бы одному эпику — затем протяните её на потомков.
      </Text>
    );
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Text>
        Выберите эпики (или контейнеры) с уже назначенной категорией.
        Категория протянется ко всем потомкам без собственной.
      </Text>
      <Transfer
        dataSource={dataSource}
        titles={['Доступные эпики', 'К применению']}
        targetKeys={targetKeys}
        onChange={onChange}
        render={(item) => `${item.title} [${item.description}]`}
        listStyle={{ width: 280, height: 320 }}
      />
      <Button
        type="primary"
        disabled={targetKeys.length === 0}
        loading={cascadeMut.isPending}
        onClick={runCascade}
      >
        Протянуть ({targetKeys.length})
      </Button>
    </Space>
  );
}
