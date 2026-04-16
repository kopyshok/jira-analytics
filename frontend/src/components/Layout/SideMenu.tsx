import { useNavigate, useLocation } from 'react-router';
import { Menu } from 'antd';
import {
  DashboardOutlined,
  BarChartOutlined,
  SyncOutlined,
  TeamOutlined,
  UnorderedListOutlined,
  FundProjectionScreenOutlined,
} from '@ant-design/icons';

const items = [
  { key: '/', icon: <DashboardOutlined />, label: 'Обзор' },
  { key: '/analytics', icon: <BarChartOutlined />, label: 'Аналитика' },
  { key: '/sync', icon: <SyncOutlined />, label: 'Jira и Scope' },
  { key: '/capacity', icon: <TeamOutlined />, label: 'Ёмкость' },
  { key: '/backlog', icon: <UnorderedListOutlined />, label: 'Бэклог' },
  { key: '/planning', icon: <FundProjectionScreenOutlined />, label: 'Планирование' },
];

export default function SideMenu() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[location.pathname]}
      items={items}
      onClick={({ key }) => navigate(key)}
    />
  );
}
