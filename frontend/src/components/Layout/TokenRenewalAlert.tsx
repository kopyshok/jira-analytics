import { Alert } from 'antd';
import { Link } from 'react-router';
import { useAuth } from '../../hooks/useAuth';
import { useTokenRenewal } from '../../hooks/useSettings';
import { renewalExpiry, renewalReason } from '../settings/tokenRenewalText';

const SYSTEMS = [
  {
    key: 'jira', name: 'Jira', section: 'connection',
    stops: 'синхронизация остановится', stopped: 'синхронизация остановлена',
  },
  {
    key: 'confluence', name: 'Confluence', section: 'confluence',
    stops: 'страницы Confluence перестанут загружаться', stopped: 'страницы Confluence не загружаются',
  },
] as const;

/** Плашка администратору на всех страницах: ключ Jira или Confluence не продлился сам. */
export default function TokenRenewalAlert() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { data } = useTokenRenewal(isAdmin);
  if (!isAdmin || !data?.enabled) return null;
  return (
    <>
      {SYSTEMS.map(({ key, name, section, stops, stopped }) => {
        const state = data[key];
        if (!state?.error) return null;
        const reason = renewalReason(state.error);
        const exp = renewalExpiry(state);
        const tail = !exp
          ? ''
          : exp.expired
            ? ` Ключ истёк ${exp.date}, ${stopped}.`
            : ` Ключ действует до ${exp.date}, потом ${stops}.`;
        return (
          <Alert
            key={key}
            type="error"
            showIcon
            title={`Не удалось продлить ключ ${name}`}
            description={
              <span>
                {reason.charAt(0).toUpperCase() + reason.slice(1)}.{tail}{' '}
                <Link to={`/settings#${section}`}>Вставить новый ключ</Link>
              </span>
            }
          />
        );
      })}
    </>
  );
}
