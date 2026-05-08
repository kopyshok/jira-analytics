import { Button, Result } from 'antd';
import { LoadingOutlined, ExperimentOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  workTypeId: string | null;
  onBuild: () => void;
  isBuilding: boolean;
}

export default function EmptyState({ workTypeId, onBuild, isBuilding }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 400,
      }}
    >
      <Result
        icon={<ExperimentOutlined style={{ color: DARK_THEME.cyanPrimary, fontSize: 64 }} />}
        title={
          <span style={{ color: DARK_THEME.textPrimary, fontSize: 22, fontWeight: 600 }}>
            Тематический отчёт ещё не построен
          </span>
        }
        subTitle={
          <span style={{ color: DARK_THEME.textMuted, maxWidth: 480, display: 'block', margin: '0 auto' }}>
            Система автоматически сгруппирует задачи по темам, выявит аномалии и сформирует AI-сводку
            для руководства. Первое построение займёт несколько минут.
          </span>
        }
        extra={
          <Button
            type="primary"
            size="large"
            disabled={!workTypeId || isBuilding}
            icon={isBuilding ? <LoadingOutlined /> : undefined}
            onClick={onBuild}
          >
            Построить первый отчёт
          </Button>
        }
      />
    </div>
  );
}
