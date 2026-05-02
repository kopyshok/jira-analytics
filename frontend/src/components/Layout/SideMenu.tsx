import { useNavigate, useLocation } from 'react-router';
import { Menu } from 'antd';
import {
  DashboardOutlined,
  BarChartOutlined,
  ProjectOutlined,
  SyncOutlined,
  TeamOutlined,
  UnorderedListOutlined,
  FundProjectionScreenOutlined,
  SettingOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useAuth } from '../../hooks/useAuth';

export default function SideMenu() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const items: MenuProps['items'] = [
    {
      key: 'grp-overview',
      type: 'group',
      label: 'ОБЗОР',
      children: [
        { key: '/', icon: <DashboardOutlined />, label: 'Дашборд' },
        { key: '/projects', icon: <ProjectOutlined />, label: 'Проекты' },
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
        ...(isAdmin ? [{ key: '/settings', icon: <SettingOutlined />, label: 'Настройки' }] : []),
      ],
    },
  ];

  // Для вложенных маршрутов нормализуем pathname к корневому сегменту
  const selectedKey = location.pathname.startsWith('/projects')
    ? '/projects'
    : location.pathname;

  return (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[selectedKey]}
      items={items}
      onClick={({ key }) => navigate(key)}
      style={{ border: 'none', paddingTop: 8 }}
    />
  );
}
