import { useState } from 'react';
import { Tabs, Button, Space, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { feedbackApi, type FeedbackItem } from '../api/feedback';
import FeedbackList from '../components/feedback/FeedbackList';
import FeedbackDrawer from '../components/feedback/FeedbackDrawer';
import FeedbackDetailDrawer from '../components/feedback/FeedbackDetailDrawer';

export default function FeedbackPage() {
  const [tab, setTab] = useState<'my' | 'ideas'>('my');
  const [submitOpen, setSubmitOpen] = useState(false);
  const [detail, setDetail] = useState<FeedbackItem | null>(null);

  const myQ = useQuery({
    queryKey: ['feedback', 'my'],
    queryFn: () => feedbackApi.my(),
    enabled: tab === 'my',
    staleTime: 30_000,
  });
  const ideasQ = useQuery({
    queryKey: ['feedback', 'ideas-feed'],
    queryFn: () => feedbackApi.ideasFeed(),
    enabled: tab === 'ideas',
    staleTime: 30_000,
  });

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Обратная связь
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setSubmitOpen(true)}>
          Создать
        </Button>
      </Space>

      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as 'my' | 'ideas')}
        items={[
          {
            key: 'my',
            label: 'Мои обращения',
            children: (
              <FeedbackList
                items={myQ.data ?? []}
                loading={myQ.isLoading}
                onRowClick={(it) => setDetail(it)}
              />
            ),
          },
          {
            key: 'ideas',
            label: 'Лента идей',
            children: (
              <FeedbackList
                items={ideasQ.data ?? []}
                loading={ideasQ.isLoading}
                showAuthor
                onRowClick={(it) => setDetail(it)}
              />
            ),
          },
        ]}
      />

      <FeedbackDrawer
        open={submitOpen}
        onClose={() => setSubmitOpen(false)}
        onSubmitted={() => {
          void myQ.refetch();
          void ideasQ.refetch();
        }}
      />
      <FeedbackDetailDrawer item={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
