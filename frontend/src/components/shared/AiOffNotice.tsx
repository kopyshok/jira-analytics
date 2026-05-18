import React from 'react';
import { Result } from 'antd';
import { StopOutlined } from '@ant-design/icons';

type Props = {
  title?: string;
  description?: string;
};

/**
 * Полноэкранная заглушка для разделов, целиком построенных на ИИ.
 * Используется когда AI выключен — никаких запросов/скриптов не запускается.
 */
export const AiOffNotice: React.FC<Props> = ({
  title = 'Раздел выключен администратором',
  description = 'Этот раздел использует ИИ. Чтобы включить, обратитесь к администратору сервиса.',
}) => (
  <Result
    icon={<StopOutlined style={{ color: '#ff7875' }} />}
    title={title}
    subTitle={description}
    style={{ padding: '64px 24px' }}
  />
);
