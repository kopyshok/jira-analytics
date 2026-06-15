import { Col, List, Row, Statistic } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { CHART_COLORS } from '../../utils/constants';
import type { ExternalHelpData } from '../../types/desk';

export default function ExternalHelpWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<ExternalHelpData>(token, 'external_help');
  const own = data?.own_hours ?? 0;
  const alien = data?.alien_hours ?? 0;
  const byTeam = data?.by_team ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={own === 0 && alien === 0}
    >
      <Row gutter={16}>
        <Col span={12}>
          <Statistic
            title="Свои команды"
            value={own}
            precision={1}
            suffix="ч"
            valueStyle={{ color: CHART_COLORS.green }}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title="Чужие команды"
            value={alien}
            precision={1}
            suffix="ч"
            valueStyle={{ color: CHART_COLORS.orange }}
          />
        </Col>
      </Row>
      {byTeam.length > 0 && (
        <List
          size="small"
          style={{ marginTop: 12 }}
          dataSource={byTeam}
          renderItem={(t) => (
            <List.Item>
              <span>{t.team}</span>
              <span>{t.hours} ч</span>
            </List.Item>
          )}
        />
      )}
    </WidgetShell>
  );
}
