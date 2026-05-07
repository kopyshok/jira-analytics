import { Button, Radio, Tag, Tooltip } from 'antd';
import { ReloadOutlined, DownloadOutlined, PrinterOutlined, TagsOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import 'dayjs/locale/ru';
import { DARK_THEME } from '../../utils/constants';
import { useMandatoryWorkTypes } from '../../hooks/useMandatoryWorkTypes';
import { useBuildWorkTypeReport } from '../../hooks/useWorkTypeReport';
import { useGlobalPeriod } from '../../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { workTypeReportApi } from '../../api/workTypeReport';
import type { WorkTypeReportResponse } from '../../types/workTypeReport';

interface Props {
  workTypeId: string;
  onWorkTypeChange: (id: string) => void;
  report: WorkTypeReportResponse | undefined;
  onOpenDictionary?: () => void;
}

function FreshnessPill({ report }: { report: WorkTypeReportResponse | undefined }) {
  if (!report) {
    return <Tag color="default">Нет данных</Tag>;
  }
  if (report.is_stale) {
    return (
      <Tooltip title={`Обновлён: ${dayjs(report.generated_at).format('DD MMM YYYY HH:mm')}`}>
        <Tag color="warning">Устарел (словарь обновлён)</Tag>
      </Tooltip>
    );
  }
  return (
    <Tooltip title={`Обновлён: ${dayjs(report.generated_at).format('DD MMM YYYY HH:mm')}`}>
      <Tag color="success">Свежий</Tag>
    </Tooltip>
  );
}

export default function Toolbar({ workTypeId, onWorkTypeChange, report, onOpenDictionary }: Props) {
  const { data: workTypes, isLoading: wtLoading } = useMandatoryWorkTypes();
  const buildMutation = useBuildWorkTypeReport();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();

  const activeTypes = workTypes ?? [];

  const handleRebuild = () => {
    buildMutation.mutate({
      work_type_id: workTypeId,
      year: period.year,
      quarter: period.quarter,
      month: period.month ?? null,
      teams: selectedTeams.length > 0 ? selectedTeams : undefined,
      force_refresh: true,
    });
  };

  const handleXlsx = () => {
    if (report?.snapshot_id) {
      workTypeReportApi.downloadXlsx(report.snapshot_id);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 12,
        alignItems: 'center',
        marginBottom: 16,
        padding: '10px 0',
        borderBottom: `1px solid ${DARK_THEME.border}`,
      }}
    >
      {/* Work-type selector */}
      <Radio.Group
        optionType="button"
        buttonStyle="solid"
        value={workTypeId}
        onChange={(e) => onWorkTypeChange(e.target.value as string)}
        disabled={wtLoading || activeTypes.length === 0}
        size="small"
      >
        {activeTypes.map((wt) => (
          <Radio.Button key={wt.id} value={wt.id}>
            {wt.label}
          </Radio.Button>
        ))}
      </Radio.Group>

      {/* Freshness pill */}
      <FreshnessPill report={report} />

      {/* Dictionary button */}
      <Button
        icon={<TagsOutlined />}
        size="small"
        onClick={onOpenDictionary}
      >
        Словарь тем
      </Button>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
        <Button
          icon={<ReloadOutlined />}
          size="small"
          loading={buildMutation.isPending}
          onClick={handleRebuild}
          disabled={!workTypeId}
        >
          Пересчитать
        </Button>
        <Button
          icon={<DownloadOutlined />}
          size="small"
          onClick={handleXlsx}
          disabled={!report?.snapshot_id}
        >
          XLSX
        </Button>
        <Button
          icon={<PrinterOutlined />}
          size="small"
          onClick={() => {/* Task 16 */}}
        >
          PDF для руководства
        </Button>
      </div>
    </div>
  );
}
