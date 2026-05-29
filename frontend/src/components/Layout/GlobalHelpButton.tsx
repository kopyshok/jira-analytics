import { useState } from 'react';
import { Button } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import HelpDrawer from '../shared/HelpDrawer';
import { useHelpContext } from '../../contexts/HelpContext';

export default function GlobalHelpButton() {
  const { current } = useHelpContext();
  const [open, setOpen] = useState(false);
  const disabled = !current;
  return (
    <>
      <Button
        type="text"
        size="small"
        icon={<QuestionCircleOutlined />}
        onClick={() => setOpen(true)}
        disabled={disabled}
        title={disabled ? 'Для этого раздела справки пока нет' : 'Справка по разделу'}
        style={{ color: disabled ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.55)' }}
      />
      {current && (
        <HelpDrawer
          open={open}
          onClose={() => setOpen(false)}
          title={current.title}
          content={current.content}
          imageBase="/help-assets/"
        />
      )}
    </>
  );
}
