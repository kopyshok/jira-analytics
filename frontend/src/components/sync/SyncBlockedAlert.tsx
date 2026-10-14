import { Alert } from 'antd';
import { Link } from 'react-router';
import { useAuth } from '../../hooks/useAuth';
import { useSyncBlocked } from '../../hooks/useSettings';
import { SYNC_BLOCKED_TEXT } from '../../utils/syncBlocked';

/** Плашка «синхронизация остановлена»; администратору — со ссылкой на страницу переезда. */
export default function SyncBlockedAlert() {
  const blocked = useSyncBlocked();
  const { user } = useAuth();
  if (!blocked) return null;
  const isAdmin = user?.role === 'admin';
  return (
    <Alert
      type="warning"
      showIcon
      title={SYNC_BLOCKED_TEXT}
      description={
        isAdmin ? (
          <span>
            Данные из Jira не обновляются, пока администратор не завершит переезд.{' '}
            <Link to="/admin/jira-migration">Перейти к переезду</Link>
          </span>
        ) : (
          'Синхронизация остановлена, пока администратор не завершит переезд на новую Jira'
        )
      }
    />
  );
}
