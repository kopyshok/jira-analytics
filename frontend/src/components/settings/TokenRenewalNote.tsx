import { Typography } from 'antd';
import { useTokenRenewal } from '../../hooks/useSettings';
import { renewalExpiry, renewalReason } from './tokenRenewalText';

const { Text } = Typography;

/** Под полями подключения: до какого числа действует ключ и продлевается ли он сам. */
export default function TokenRenewalNote({ system }: { system: 'jira' | 'confluence' }) {
  const { data } = useTokenRenewal();
  const state = data?.[system];
  if (!data || !state) return null;
  if (!data.enabled) return <Text type="secondary">Автопродление ключа на этом сервере выключено</Text>;
  const exp = renewalExpiry(state);
  const when = exp ? `${exp.expired ? 'истёк' : 'действует до'} ${exp.date}` : null;
  if (state.error) {
    return (
      <Text type="danger">
        Не удалось продлить ключ: {renewalReason(state.error)}{when ? `. Ключ ${when}` : ''}
      </Text>
    );
  }
  if (!when) return <Text type="secondary">Ключ продлится автоматически в течение часа</Text>;
  return <Text type="secondary">Ключ продлевается автоматически, {when}</Text>;
}
