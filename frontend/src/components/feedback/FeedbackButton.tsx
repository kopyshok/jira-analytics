import { useState, useSyncExternalStore } from 'react';
import { FloatButton } from 'antd';
import { CommentOutlined } from '@ant-design/icons';
import { getErrorCount, subscribe } from '../../utils/errorStore';
import FeedbackDrawer from './FeedbackDrawer';

export default function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const count = useSyncExternalStore(subscribe, getErrorCount);

  return (
    <>
      <FloatButton
        icon={<CommentOutlined />}
        tooltip="Обратная связь — баг или идея"
        badge={count > 0 ? { count, overflowCount: 99 } : undefined}
        onClick={() => setOpen(true)}
      />
      <FeedbackDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
