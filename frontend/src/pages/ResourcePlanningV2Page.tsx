import { Tag } from 'antd';
import PageHeader from '../components/shared/PageHeader';

export default function ResourcePlanningV2Page() {
  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader
        title={<span>Планирование <Tag color="purple" style={{ marginLeft: 8 }}>β</Tag></span>}
      />
      <div style={{ color: '#8ab0d8', marginTop: 24 }}>
        Заглушка — здесь будет SVAR Gantt + кнопка «Оптимизировать».
      </div>
    </div>
  );
}
