import { useId } from 'react';
import { Input, Radio, Space, Typography } from 'antd';
import dayjs from 'dayjs';

/** undefined — срок неизвестен, null — бессрочный, пустая строка — дата ещё не выбрана. */
export default function TokenExpiryFields({ value, onChange, disabled }: {
  value: string | null | undefined;
  onChange: (value: string | null | undefined) => void;
  disabled: boolean;
}) {
  const id = useId();
  return (
    <Space orientation="vertical">
      <Typography.Text id={`${id}-label`}>Срок действия ключа</Typography.Text>
      <Radio.Group
        disabled={disabled}
        aria-labelledby={`${id}-label`}
        value={value === undefined ? undefined : value === null ? 'never' : 'date'}
        onChange={(e) => onChange(e.target.value === 'never' ? null : '')}
        options={[
          { value: 'never', label: 'Без ограничения срока' },
          { value: 'date', label: 'До даты' },
        ]}
      />
      {typeof value === 'string' && (
        <Space wrap>
          <label htmlFor={id}>Дата и время окончания</label>
          <Input
            disabled={disabled}
            id={id}
            type="datetime-local"
            value={value ? dayjs(value).format('YYYY-MM-DDTHH:mm') : ''}
            onChange={(e) => onChange(e.target.value ? dayjs(e.target.value).toISOString() : '')}
          />
        </Space>
      )}
      <Typography.Text type="secondary">
        Укажите срок, выбранный при создании ключа. Время местное. Замена за сутки до окончания.
      </Typography.Text>
    </Space>
  );
}
