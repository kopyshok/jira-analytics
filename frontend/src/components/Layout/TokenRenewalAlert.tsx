import { Alert } from 'antd';
import { Link } from 'react-router';
import dayjs from 'dayjs';
import { useAuth } from '../../hooks/useAuth';
import { useTokenRenewal } from '../../hooks/useSettings';

const SYSTEMS = [
  { key: 'jira', name: 'Jira', section: 'connection', stops: 'синхронизация остановится' },
  { key: 'confluence', name: 'Confluence', section: 'confluence', stops: 'страницы Confluence перестанут загружаться' },
] as const;

/** Плашка администратору на всех страницах: ключ Jira или Confluence не продлился сам. */
export default function TokenRenewalAlert() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { data } = useTokenRenewal(isAdmin);
  if (!isAdmin || !data?.enabled) return null;
  return (
    <>
      {SYSTEMS.map(({ key, name, section, stops }) => {
        const state = data[key];
        if (!state?.error) return null;
        const until = state.expires_at
          ? ` Ключ действует до ${dayjs(state.expires_at).format('DD.MM.YYYY')}, потом ${stops}.`
          : '';
        return (
          <Alert
            key={key}
            type="error"
            showIcon
            title={`Не удалось продлить ключ ${name}`}
            description={
              <span>
                {state.error}.{until} <Link to={`/settings#${section}`}>Вставить новый ключ</Link>
              </span>
            }
          />
        );
      })}
    </>
  );
}
