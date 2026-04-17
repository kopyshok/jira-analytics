import { useState, useEffect } from 'react';
import { Tabs } from 'antd';
import ConnectionCard from '../components/ConnectionCard';
import ScopeAdmin from '../components/ScopeAdmin';
import JiraFieldsCard from '../components/JiraFieldsCard';
import HierarchyRulesTab from '../components/HierarchyRulesTab';

const TAB_KEYS = ['connection', 'scope', 'fields', 'hierarchy'] as const;
type TabKey = typeof TAB_KEYS[number];

function readHashKey(): TabKey {
  const raw = window.location.hash.replace('#', '');
  return TAB_KEYS.includes(raw as TabKey) ? (raw as TabKey) : 'connection';
}

export default function SettingsPage() {
  const [activeKey, setActiveKey] = useState<TabKey>(readHashKey);

  useEffect(() => {
    const handler = () => setActiveKey(readHashKey());
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);

  const onChange = (k: string) => {
    setActiveKey(k as TabKey);
    window.location.hash = k;
  };

  return (
    <Tabs
      activeKey={activeKey}
      onChange={onChange}
      items={[
        { key: 'connection', label: 'Подключение к Jira', children: <ConnectionCard /> },
        { key: 'scope', label: 'Проекты в scope', children: <ScopeAdmin /> },
        { key: 'fields', label: 'Поля Jira', children: <JiraFieldsCard /> },
        { key: 'hierarchy', label: 'Правила иерархии', children: <HierarchyRulesTab /> },
      ]}
    />
  );
}
