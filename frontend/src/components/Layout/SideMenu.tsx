import { useNavigate, useLocation } from 'react-router';
import { Menu } from 'antd';
import {
  DashboardOutlined,
  BarChartOutlined,
  BulbOutlined,
  ProjectOutlined,
  RocketOutlined,
  SyncOutlined,
  TeamOutlined,
  UnorderedListOutlined,
  FundProjectionScreenOutlined,
  SettingOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../hooks/useAuth';
import { getHiddenSections } from '../../api/uiConfig';

export default function SideMenu() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const { data: hidden } = useQuery({
    queryKey: ['ui-config', 'hidden-sections'],
    queryFn: getHiddenSections,
    staleTime: 60_000,
    enabled: !!user,
  });
  const hiddenSet = new Set(hidden?.keys ?? []);
  const isHidden = (k: string) => hiddenSet.has(k);

  const overview = [
    { key: '/', icon: <DashboardOutlined />, label: 'Дашборд' },
    { key: '/projects', icon: <ProjectOutlined />, label: 'Проекты' },
    { key: '/analytics', icon: <BarChartOutlined />, label: 'Аналитика' },
    { key: '/analytics/work-type-report', icon: <BulbOutlined />, label: 'Тематический отчёт' },
    { key: '/executive', icon: <RocketOutlined />, label: 'Сводка для руководителя' },
  ].filter(it => !isHidden(it.key));

  const planning = [
    { key: '/capacity', icon: <TeamOutlined />, label: 'Ресурсы' },
    { key: '/backlog', icon: <UnorderedListOutlined />, label: 'Целевые задачи' },
    { key: '/planning', icon: <FundProjectionScreenOutlined />, label: 'Сценарии' },
    { key: '/resource-planning', icon: <ProjectOutlined />, label: 'Ресурс. планир.' },
    { key: '/resource-planning-v2', icon: <ProjectOutlined />, label: <>Планирование <span style={{ marginLeft: 4, padding: '0 6px', background: '#722ed1', borderRadius: 4, fontSize: 10, color: '#fff' }}>β</span></> },
    { key: '/resource-planning-v3', icon: <ProjectOutlined />, label: <>Планирование <span style={{ marginLeft: 4, padding: '0 6px', background: '#13a8a8', borderRadius: 4, fontSize: 10, color: '#fff' }}>γ</span></> },
  ].filter(it => !isHidden(it.key));

  const data = [
    { key: '/sync', icon: <SyncOutlined />, label: 'Синхронизация' },
    { key: '/categories', icon: <TagsOutlined />, label: 'Категории задач' },
    ...(isAdmin ? [{ key: '/settings', icon: <SettingOutlined />, label: 'Настройки' }] : []),
  ].filter(it => !isHidden(it.key));

  const items: MenuProps['items'] = [
    overview.length ? { key: 'grp-overview', type: 'group', label: 'ОБЗОР', children: overview } : null,
    planning.length ? { key: 'grp-planning', type: 'group', label: 'ПЛАНИРОВАНИЕ', children: planning } : null,
    data.length ? { key: 'grp-data', type: 'group', label: 'ДАННЫЕ', children: data } : null,
  ].filter(Boolean) as MenuProps['items'];

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
