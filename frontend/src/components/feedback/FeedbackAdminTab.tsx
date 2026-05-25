import { useState } from 'react';
import { Space, Button, Radio, App, Popconfirm } from 'antd';
import { DownloadOutlined, CheckOutlined, RollbackOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { feedbackApi, type FeedbackItem } from '../../api/feedback';
import { BASE_URL } from '../../api/client';
import FeedbackList from './FeedbackList';
import FeedbackDetailDrawer from './FeedbackDetailDrawer';

type Filter = 'unread' | 'all';
type Kind = 'bug' | 'idea';

export default function FeedbackAdminTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>('bug');
  const [filter, setFilter] = useState<Filter>('unread');
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<FeedbackItem | null>(null);

  const q = useQuery({
    queryKey: ['feedback', 'admin', kind, filter] as const,
    queryFn: () =>
      kind === 'bug'
        ? feedbackApi.adminListBugs(filter)
        : feedbackApi.adminListIdeas(filter),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['feedback'] });
    setSelected([]);
  };

  const handleMarkRead = async () => {
    if (selected.length === 0) return;
    try {
      await feedbackApi.markRead(selected);
      notification.success({
        title: 'Отмечено прочитанными',
        description: `${selected.length} шт.`,
      });
      invalidate();
    } catch (e) {
      notification.error({
        title: 'Ошибка',
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const handleMarkUnread = async () => {
    if (selected.length === 0) return;
    try {
      await feedbackApi.markUnread(selected);
      invalidate();
    } catch (e) {
      notification.error({
        title: 'Ошибка',
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const downloadMarkdown = async (params: {
    ids: string[] | null;
    only_unread: boolean;
    mark_after: boolean;
  }) => {
    try {
      const res = await fetch(`${BASE_URL}/feedback/admin/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ kind, ...params }),
      });
      if (!res.ok) {
        notification.error({
          title: 'Ошибка экспорта',
          description: `HTTP ${res.status}`,
        });
        return;
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      const today = new Date().toISOString().slice(0, 10);
      a.download = `feedback-${kind}s-${today}.md`;
      a.click();
      URL.revokeObjectURL(a.href);
      if (params.mark_after) invalidate();
    } catch (e) {
      notification.error({
        title: 'Ошибка экспорта',
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const handleExportSelected = () =>
    downloadMarkdown({ ids: selected, only_unread: false, mark_after: false });

  const handleExportAllUnreadAndMark = () =>
    downloadMarkdown({ ids: null, only_unread: true, mark_after: true });

  return (
    <div>
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Radio.Group
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setSelected([]);
          }}
          options={[
            { label: 'Баги', value: 'bug' },
            { label: 'Идеи', value: 'idea' },
          ]}
          optionType="button"
        />
        <Radio.Group
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          options={[
            { label: 'Только новые', value: 'unread' },
            { label: 'Все', value: 'all' },
          ]}
          optionType="button"
        />
        <Button
          icon={<DownloadOutlined />}
          disabled={selected.length === 0}
          onClick={handleExportSelected}
        >
          Выгрузить выбранные ({selected.length})
        </Button>
        <Popconfirm
          title="Выгрузить все новые и пометить прочитанными?"
          okText="Да"
          cancelText="Отмена"
          onConfirm={handleExportAllUnreadAndMark}
        >
          <Button type="primary" icon={<DownloadOutlined />}>
            Выгрузить новые и отметить прочитанными
          </Button>
        </Popconfirm>
        <Button
          icon={<CheckOutlined />}
          disabled={selected.length === 0}
          onClick={handleMarkRead}
        >
          Отметить прочитанными
        </Button>
        <Button
          icon={<RollbackOutlined />}
          disabled={selected.length === 0}
          onClick={handleMarkUnread}
        >
          Снять отметку
        </Button>
      </Space>

      <FeedbackList
        items={q.data ?? []}
        loading={q.isLoading}
        showAuthor
        showReadStatus
        rowSelection={{ selectedRowKeys: selected, onChange: setSelected }}
        onRowClick={(it) => setDetail(it)}
      />

      <FeedbackDetailDrawer item={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
