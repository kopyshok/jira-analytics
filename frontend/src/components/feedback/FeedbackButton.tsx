import { FloatButton } from 'antd';
import { CommentOutlined, ThunderboltOutlined } from '@ant-design/icons';
import FeedbackDrawer from './FeedbackDrawer';
import { useFeedbackActions } from './useFeedbackActions';

export default function FeedbackButton() {
  const { open, setOpen, count, handleQuickBug } = useFeedbackActions();

  return (
    <>
      <FloatButton.Group
        trigger="hover"
        icon={<CommentOutlined />}
        badge={count > 0 ? { count, overflowCount: 99 } : undefined}
      >
        <FloatButton
          icon={<CommentOutlined />}
          tooltip={{ title: 'Открыть форму', placement: 'left' }}
          onClick={() => setOpen(true)}
        />
        <FloatButton
          icon={<ThunderboltOutlined />}
          tooltip={{ title: 'Быстрый баг → в буфер', placement: 'left' }}
          onClick={handleQuickBug}
        />
      </FloatButton.Group>
      <FeedbackDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
