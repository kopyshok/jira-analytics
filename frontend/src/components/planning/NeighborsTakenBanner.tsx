import { Alert, Switch } from 'antd';
import { neighborsTakenTitle } from '../../utils/multiTeamProgress';

/** Над таблицей сценария: задачи мультикомандных RFA, которые соседние команды
 *  уже взяли в работу, а в этом сценарии они не включены. */
export default function NeighborsTakenBanner({
  count,
  onlyThem,
  onOnlyThemChange,
}: {
  count: number;
  onlyThem: boolean;
  onOnlyThemChange: (next: boolean) => void;
}) {
  return (
    <Alert
      type="warning"
      showIcon
      banner
      title={neighborsTakenTitle(count)}
      action={
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12 }}>
          <Switch size="small" checked={onlyThem} onChange={onOnlyThemChange} />
          Показать только их
        </label>
      }
    />
  );
}
