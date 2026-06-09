import { App, Button, Drawer, Form, Input, InputNumber, Space, Table } from 'antd';
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getPlanHistory,
  patchPlan,
  revertPlan,
  type PlanAuditRow,
} from '../../api/issues';

type RoleKey = 'analyst' | 'dev' | 'qa' | 'opo';

interface RoleValues {
  analyst: number | null;
  dev: number | null;
  qa: number | null;
  opo: number | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  issueId: string;
  issueKey: string;
  jiraValues: RoleValues;
  effectiveValues: RoleValues;
}

const ROLE_ROWS: Array<{ role: string; key: RoleKey }> = [
  { role: 'Аналитик', key: 'analyst' },
  { role: 'Разработка', key: 'dev' },
  { role: 'Тестирование', key: 'qa' },
  { role: 'ОПЭ', key: 'opo' },
];

export default function PlanEditDrawer({
  open,
  onClose,
  issueId,
  issueKey,
  jiraValues,
  effectiveValues,
}: Props) {
  const [form] = Form.useForm();
  const [showHistory, setShowHistory] = useState(false);
  const qc = useQueryClient();
  const { message } = App.useApp();

  useEffect(() => {
    if (open) {
      form.setFieldsValue({
        analyst: effectiveValues.analyst,
        dev: effectiveValues.dev,
        qa: effectiveValues.qa,
        opo: effectiveValues.opo,
        comment: '',
      });
    }
  }, [open, effectiveValues, form]);

  const editMut = useMutation({
    mutationFn: (vals: {
      analyst: number | null;
      dev: number | null;
      qa: number | null;
      opo: number | null;
      comment: string;
    }) =>
      patchPlan(
        issueId,
        { analyst: vals.analyst, dev: vals.dev, qa: vals.qa, opo: vals.opo },
        vals.comment,
      ),
    onSuccess: () => {
      message.success('План обновлён');
      qc.invalidateQueries({ queryKey: ['hours-breakdown'] });
      qc.invalidateQueries({ queryKey: ['plan-history', issueId] });
      qc.invalidateQueries({ queryKey: ['plan-conflicts', issueId] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
      onClose();
    },
    onError: (err: unknown) => {
      const e = err as { message?: string };
      message.error(e?.message ?? 'Не удалось сохранить');
    },
  });

  const revertMut = useMutation({
    mutationFn: () => revertPlan(issueId),
    onSuccess: () => {
      message.success('Сброс к Jira');
      qc.invalidateQueries({ queryKey: ['hours-breakdown'] });
      qc.invalidateQueries({ queryKey: ['plan-history', issueId] });
      qc.invalidateQueries({ queryKey: ['backlog'] });
      onClose();
    },
    onError: (err: unknown) => {
      const e = err as { message?: string };
      message.error(e?.message ?? 'Не удалось сбросить');
    },
  });

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`Редактирование плана · ${issueKey}`}
      size={520}
    >
      <Form form={form} layout="vertical" onFinish={(vals) => editMut.mutate(vals)}>
        <Table
          size="small"
          pagination={false}
          rowKey="key"
          dataSource={ROLE_ROWS}
          columns={[
            { title: 'Роль', dataIndex: 'role' },
            {
              title: 'Jira',
              dataIndex: 'key',
              align: 'right',
              render: (k: RoleKey) => (
                <span style={{ color: 'var(--text-muted, #94a3b8)' }}>{jiraValues[k] ?? '—'}</span>
              ),
            },
            {
              title: 'Правка',
              dataIndex: 'key',
              align: 'right',
              render: (k: RoleKey) => (
                <Form.Item name={k} noStyle>
                  <InputNumber min={0} max={9999} style={{ width: 90 }} />
                </Form.Item>
              ),
            },
          ]}
        />
        <Form.Item
          label="Комментарий"
          name="comment"
          rules={[{ required: true, min: 1, message: 'Комментарий обязателен' }]}
          style={{ marginTop: 12 }}
        >
          <Input.TextArea rows={3} placeholder="Например: после ретро Q1" />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={editMut.isPending}>
            Сохранить
          </Button>
          <Button onClick={() => revertMut.mutate()} loading={revertMut.isPending}>
            Сбросить к Jira
          </Button>
          <Button onClick={() => setShowHistory((s) => !s)}>
            {showHistory ? 'Скрыть' : 'Показать'} историю
          </Button>
        </Space>
      </Form>
      {showHistory && <PlanHistorySection issueId={issueId} />}
    </Drawer>
  );
}

function PlanHistorySection({ issueId }: { issueId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['plan-history', issueId],
    queryFn: () => getPlanHistory(issueId),
    staleTime: 10_000,
  });
  return (
    <Table<PlanAuditRow>
      style={{ marginTop: 16 }}
      size="small"
      loading={isLoading}
      pagination={false}
      rowKey="id"
      dataSource={data ?? []}
      columns={[
        {
          title: 'Дата',
          dataIndex: 'created_at',
          render: (v: string) => new Date(v).toLocaleString('ru'),
        },
        { title: 'Роль', dataIndex: 'role' },
        {
          title: 'Было',
          dataIndex: 'value_before',
          align: 'right',
          render: (v: number | null) => v ?? '—',
        },
        {
          title: 'Стало',
          dataIndex: 'value_after',
          align: 'right',
          render: (v: number | null) => v ?? '—',
        },
        { title: 'Источник', dataIndex: 'source' },
        {
          title: 'Комментарий',
          dataIndex: 'comment',
          render: (v: string | null) => v ?? '—',
        },
      ]}
    />
  );
}
