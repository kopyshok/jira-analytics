import { useNavigate, useLocation } from 'react-router';
import { Menu } from 'antd';
import {
  DashboardOutlined,
  BarChartOutlined,
  SyncOutlined,
  TeamOutlined,
  UnorderedListOutlined,
  FundProjectionScreenOutlined,
  SettingOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';

const items: MenuProps['items'] = [
  {
    key: 'grp-overview',
    type: 'group',
    label: 'ОБЗОР',
    children: [
      { key: '/', icon: <DashboardOutlined />, label: 'Дашборд' },
      { key: '/analytics', icon: <BarChartOutlined />, label: 'Аналитика' },
    ],
  },
  {
    key: 'grp-planning',
    type: 'group',
    label: 'ПЛАНИРОВАНИЕ',
    children: [
      { key: '/capacity', icon: <TeamOutlined />, label: 'Ресурсы' },
      { key: '/backlog', icon: <UnorderedListOutlined />, label: 'Целевые задачи' },
      { key: '/planning', icon: <FundProjectionScreenOutlined />, label: 'Сценарии' },
    ],
  },
  {
    key: 'grp-data',
    type: 'group',
    label: 'ДАННЫЕ',
    children: [
      { key: '/sync', icon: <SyncOutlined />, label: 'Синхронизация' },
      { key: '/categories', icon: <TagsOutlined />, label: 'Категории задач' },
      { key: '/settings', icon: <SettingOutlined />, label: 'Настройки' },
    ],
  },
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
      style={{ border: 'none', paddingTop: 8 }}
    />
  );
}
