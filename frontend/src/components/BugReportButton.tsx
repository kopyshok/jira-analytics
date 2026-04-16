import { useSyncExternalStore } from 'react';
import { FloatButton, App } from 'antd';
import { BugOutlined } from '@ant-design/icons';
import { buildBugReport, getErrors, getErrorCount, clearErrors, subscribe } from '../utils/errorStore';

export default function BugReportButton() {
  const { message, modal } = App.useApp();
  const count = useSyncExternalStore(subscribe, getErrorCount);

  const handleClick = () => {
    const errors = getErrors();
    if (errors.length === 0) {
      message.info('Ошибок нет — нечего выгружать');
      return;
    }

    const report = buildBugReport();

    modal.confirm({
      title: `Баг-репорт (${errors.length} ошибок)`,
      content: 'Скопировать отчёт в буфер обмена? После этого вставьте его в чат для разбора.',
      okText: 'Скопировать',
      cancelText: 'Отмена',
      onOk: async () => {
        await navigator.clipboard.writeText(report);
        message.success('Баг-репорт скопирован в буфер обмена');
        clearErrors();
      },
    });
  };

  return (
    <FloatButton
      icon={<BugOutlined />}
      tooltip="Баг-репорт"
      badge={{ count, overflowCount: 99 }}
      onClick={handleClick}
    />
  );
}
