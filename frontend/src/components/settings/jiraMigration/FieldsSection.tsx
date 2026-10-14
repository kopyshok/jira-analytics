import { App, Select, Table, Tag, Typography } from 'antd';
import type { DcField, FieldDecision, FieldRow } from '../../../api/jiraMigration';
import { useSetDecision } from '../../../hooks/useJiraMigration';
import { fieldStatus } from '../../../utils/jiraMigration';

const NOT_USED = '__not_used__';
const SUGGESTED = '__suggested__';

interface Props {
  rows?: FieldRow[];
  dcFields?: DcField[];
  readOnly: boolean;
}

export default function FieldsSection({ rows, dcFields = [], readOnly }: Props) {
  const { notification } = App.useApp();
  const setDecision = useSetDecision();

  const dcOptions = [
    { value: NOT_USED, label: 'Не использовать' },
    ...dcFields.map((f) => ({ value: f.id, label: f.custom ? f.name : `${f.name} (системное)` })),
  ];

  const save = (row: FieldRow, value: string) => {
    let decision: FieldDecision | null;
    if (value === SUGGESTED) decision = null;
    else if (value === NOT_USED) decision = { dc_field_id: null };
    else decision = { dc_field_id: value };
    setDecision.mutate(
      { kind: 'field', item_key: row.cloud_id, decision },
      { onError: (e) => notification.error({ title: 'Решение не сохранено', description: e.message }) },
    );
  };

  const valueOf = (row: FieldRow): string | undefined => {
    if (row.decision) return row.decision.dc_field_id ?? NOT_USED;
    return row.suggested_id ? SUGGESTED : undefined;
  };

  if (!rows) return null;

  return (
    <>
      <Typography.Paragraph type="secondary">
        Номера полей в новой Jira другие. Сервис предлагает поле с тем же названием, что было
        в облаке. Если предложения нет или оно неверное — выберите поле из списка или
        «Не использовать».
      </Typography.Paragraph>
      <Table<FieldRow>
        rowKey="cloud_id"
        size="small"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: 'Поле в облаке', dataIndex: 'cloud_name' },
          { title: 'Для чего', dataIndex: 'labels', render: (labels: string[]) => labels.join(', ') },
          {
            title: 'Поле в новой Jira',
            key: 'choice',
            width: 360,
            render: (_: unknown, row) => (
              <Select
                style={{ width: '100%' }}
                showSearch
                optionFilterProp="label"
                placeholder="Выберите поле"
                aria-label={`Решение по ${row.cloud_name}`}
                disabled={readOnly || (setDecision.isPending && setDecision.variables?.item_key === row.cloud_id)}
                value={valueOf(row)}
                options={
                  row.suggested_id
                    ? [{ value: SUGGESTED, label: `${row.suggested_name} (предложено)` }, ...dcOptions]
                    : dcOptions
                }
                onChange={(value: string) => save(row, value)}
              />
            ),
          },
          {
            title: 'Статус',
            key: 'status',
            width: 190,
            render: (_: unknown, row) => {
              const status = fieldStatus(row);
              return <Tag color={status.color}>{status.label}</Tag>;
            },
          },
        ]}
      />
    </>
  );
}
