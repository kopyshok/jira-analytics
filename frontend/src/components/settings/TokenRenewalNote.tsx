import { Typography } from 'antd';
import dayjs from 'dayjs';
import { useTokenRenewal } from '../../hooks/useSettings';

const { Text } = Typography;

/** Под полями подключения: до какого числа действует ключ и продлевается ли он сам. */
export default function TokenRenewalNote({ system }: { system: 'jira' | 'confluence' }) {
  const { data } = useTokenRenewal();
  const state = data?.[system];
  if (!data || !state) return null;
  if (!data.enabled) return <Text type="secondary">Автопродление ключа на этом сервере выключено</Text>;
  const until = state.expires_at ? dayjs(state.expires_at).format('DD.MM.YYYY') : null;
  if (state.error) {
    return (
      <Text type="danger">
        Не удалось продлить ключ: {state.error}{until ? `. Действует до ${until}` : ''}
      </Text>
    );
  }
  if (!until) return <Text type="secondary">Ключ продлится автоматически в течение часа</Text>;
  return <Text type="secondary">Ключ продлевается автоматически, действует до {until}</Text>;
}
