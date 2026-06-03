import { Drawer } from 'antd';
import HoursBreakdownTable from './HoursBreakdownTable';
import { useHoursBreakdown } from '../../hooks/useHoursBreakdown';

interface Props {
  open: boolean;
  onClose: () => void;
  issueId: string | null;
  issueKey?: string;
  year: number;
  quarter: number;
}

export default function HoursBreakdownDrawer({
  open, onClose, issueId, issueKey, year, quarter,
}: Props) {
  const { data, isLoading } = useHoursBreakdown(issueId, year, quarter);
  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={720}
      title={`Разбивка часов · ${issueKey ?? ''} · Q${quarter} ${year}`}
    >
      {data && <HoursBreakdownTable data={data} loading={isLoading} />}
    </Drawer>
  );
}
