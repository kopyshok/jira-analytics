import { useState } from 'react';
import { Popover, Button, Table, InputNumber, Space, Typography } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import type { ContinuationInfoRow } from '../../api/planning';
import { useAllocationOverrideMutation } from '../../hooks/usePlanning';

const { Text } = Typography;

type Role = 'analyst' | 'dev' | 'qa' | 'opo';

interface Props {
  scenarioId: string;
  allocationId: string;
  scenarioStatus: 'draft' | 'approved';
  currentOverride: {
    analyst: number | null;
    dev: number | null;
    qa: number | null;
    opo: number | null;
  };
  continuation: ContinuationInfoRow | undefined;
}

const ROLE_LABEL: Record<Role, string> = {
  analyst: 'Аналитика',
  dev: 'Разработка',
  qa: 'Тестирование',
  opo: 'ОПЭ',
};

const ROLES: Role[] = ['analyst', 'dev', 'qa', 'opo'];

const ZERO_BREAKDOWN = { analyst: 0, dev: 0, qa: 0, opo: 0 };

interface FormProps {
  scenarioId: string;
  allocationId: string;
  isApproved: boolean;
  hasOverride: boolean;
  currentOverride: Props['currentOverride'];
  continuation: ContinuationInfoRow | undefined;
  onDone: () => void;
}

/**
 * Тело Popover'а вынесено в отдельный компонент: его useState(initial) выполняется
 * только при mount'е (когда popover открывается через destroyOnHidden). Это
 * избавляет от setState внутри useEffect для синхронизации с обновлённым
 * currentOverride после save.
 */
function OverrideForm({
  scenarioId,
  allocationId,
  isApproved,
  hasOverride,
  currentOverride,
  continuation,
  onDone,
}: FormProps) {
  const jira = continuation?.jira_estimate ?? ZERO_BREAKDOWN;
  const spent = continuation?.spent ?? ZERO_BREAKDOWN;

  const [values, setValues] = useState<Record<Role, number>>({
    analyst:
      currentOverride.analyst ?? Math.max(0, (jira.analyst ?? 0) - (spent.analyst ?? 0)),
    dev: currentOverride.dev ?? Math.max(0, (jira.dev ?? 0) - (spent.dev ?? 0)),
    qa: currentOverride.qa ?? Math.max(0, (jira.qa ?? 0) - (spent.qa ?? 0)),
    opo: currentOverride.opo ?? Math.max(0, (jira.opo ?? 0) - (spent.opo ?? 0)),
  });

  const mut = useAllocationOverrideMutation(scenarioId);

  const jiraTotal =
    (jira.analyst ?? 0) + (jira.dev ?? 0) + (jira.qa ?? 0) + (jira.opo ?? 0);
  const spentTotal = continuation?.spent_total ?? 0;

  const handleSave = () => {
    mut.mutate({ allocationId, payload: values }, { onSuccess: onDone });
  };

  const handleReset = () => {
    mut.mutate(
      { allocationId, payload: { analyst: null, dev: null, qa: null, opo: null } },
      { onSuccess: onDone },
    );
  };

  return (
    <div style={{ minWidth: 380 }} onClick={(e) => e.stopPropagation()}>
      <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
        Оригинал Jira: А {jira.analyst} / Р {jira.dev} / Т {jira.qa} / ОПЭ {jira.opo} = {jiraTotal}ч
      </Text>
      <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 12 }}>
        Списано в прошлых периодах: А {spent.analyst} / Р {spent.dev} / Т {spent.qa} / ОПЭ {spent.opo} = {spentTotal}ч
      </Text>

      <Table
        size="small"
        pagination={false}
        rowKey="role"
        dataSource={ROLES.map((role) => ({
          role,
          label: ROLE_LABEL[role],
          value: values[role],
          spent: spent[role] ?? 0,
          remainder: Math.max(0, (jira[role] ?? 0) - (spent[role] ?? 0)),
        }))}
        columns={[
          { title: 'Роль', dataIndex: 'label' },
          {
            title: 'План Q',
            dataIndex: 'value',
            render: (_: number, row: { role: Role; value: number; spent: number }) => (
              <div>
                <InputNumber
                  min={0}
                  value={row.value}
                  disabled={isApproved}
                  onChange={(v) =>
                    setValues((s) => ({ ...s, [row.role]: v ?? 0 }))
                  }
                  style={{ width: 80 }}
                />
                {row.value < row.spent && (
                  <Text type="danger" style={{ display: 'block', fontSize: 11 }}>
                    план меньше уже списанного
                  </Text>
                )}
              </div>
            ),
          },
          { title: 'Списано', dataIndex: 'spent', align: 'right' as const },
          { title: 'Остаток оригинала', dataIndex: 'remainder', align: 'right' as const },
        ]}
      />

      <Space
        style={{ marginTop: 12, justifyContent: 'flex-end', display: 'flex', width: '100%' }}
      >
        {hasOverride && (
          <Button onClick={handleReset} loading={mut.isPending} disabled={isApproved}>
            Сбросить
          </Button>
        )}
        <Button
          type="primary"
          onClick={handleSave}
          loading={mut.isPending}
          disabled={isApproved}
        >
          Сохранить
        </Button>
      </Space>
    </div>
  );
}

export function AllocationOverridePopover({
  scenarioId,
  allocationId,
  scenarioStatus,
  currentOverride,
  continuation,
}: Props) {
  const [open, setOpen] = useState(false);

  const isApproved = scenarioStatus === 'approved';
  const hasOverride =
    currentOverride.analyst !== null ||
    currentOverride.dev !== null ||
    currentOverride.qa !== null ||
    currentOverride.opo !== null;

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottomRight"
      destroyOnHidden
      content={
        <OverrideForm
          scenarioId={scenarioId}
          allocationId={allocationId}
          isApproved={isApproved}
          hasOverride={hasOverride}
          currentOverride={currentOverride}
          continuation={continuation}
          onDone={() => setOpen(false)}
        />
      }
    >
      <Button
        size="small"
        type="text"
        icon={<EditOutlined />}
        onClick={(e) => e.stopPropagation()}
        title="Переоценить план квартала"
      />
    </Popover>
  );
}
