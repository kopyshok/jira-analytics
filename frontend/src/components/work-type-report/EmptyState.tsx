import { Button, Result } from 'antd';
import { LoadingOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useBuildWorkTypeReport } from '../../hooks/useWorkTypeReport';
import { useGlobalPeriod } from '../../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  workTypeId: string | null;
}

export default function EmptyState({ workTypeId }: Props) {
  const buildMutation = useBuildWorkTypeReport();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();

  const handleBuild = () => {
    if (!workTypeId) return;
    buildMutation.mutate({
      work_type_id: workTypeId,
      year: period.year,
      quarter: period.quarter,
      month: period.month ?? null,
      teams: selectedTeams.length > 0 ? selectedTeams : undefined,
      force_refresh: false,
    });
  };

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
            disabled={!workTypeId || buildMutation.isPending}
            icon={buildMutation.isPending ? <LoadingOutlined /> : undefined}
            onClick={handleBuild}
          >
            Построить первый отчёт
          </Button>
        }
      />
    </div>
  );
}
