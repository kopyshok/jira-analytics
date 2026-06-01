import { useState } from 'react';
import { Badge, Button } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import HelpDrawer from '../shared/HelpDrawer';
import { useHelpContext } from '../../contexts/HelpContext';
import { useUnreadReleaseNotes } from '../../hooks/useReleaseNotes';

export default function GlobalHelpButton() {
  const { current } = useHelpContext();
  const [open, setOpen] = useState(false);
  const { data: unread } = useUnreadReleaseNotes();
  const hasUnread = (unread?.unread_versions.length ?? 0) > 0;
  // Кнопка disabled только когда И справки нет, И непрочитанных нет.
  const disabled = !current && !hasUnread;

  const title = hasUnread
    ? 'Справка по разделу — есть новые обновления во вкладке «Что нового»'
    : disabled
    ? 'Для этого раздела справки пока нет'
    : 'Справка по разделу';

  // Дефолт всегда «Справка» (когда контент есть). Лента «Что нового» — вторая
  // вкладка; красная точка на иконке подсказывает что там что-то новое, но
  // переключается пользователем вручную.
  const defaultTab = current ? 'help' : 'whats-new';

  return (
    <>
      <Badge dot={hasUnread} offset={[-4, 4]} color="red">
        <Button
          type="text"
          size="small"
          icon={<QuestionCircleOutlined />}
          onClick={() => setOpen(true)}
          disabled={disabled}
          title={title}
          style={{
            color: disabled ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.55)',
          }}
        />
      </Badge>
      <HelpDrawer
        open={open}
        onClose={() => setOpen(false)}
        title={current?.title ?? 'Справка'}
        content={current?.content ?? ''}
        imageBase="/help-assets/"
        defaultTab={defaultTab}
      />
    </>
  );
}
