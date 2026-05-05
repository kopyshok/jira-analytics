import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { Segmented, Tag } from 'antd';
import ClassicMode from '../components/resource-planning-v3/modes/ClassicMode';
import ResourceCentricMode from '../components/resource-planning-v3/modes/ResourceCentricMode';
import RoadmapMode from '../components/resource-planning-v3/modes/RoadmapMode';

type Mode = 'classic' | 'resource' | 'roadmap';

export default function ResourcePlanningV3Page() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = (searchParams.get('mode') as Mode) || 'classic';
  const [mode, setMode] = useState<Mode>(initial);

  const handleModeChange = (m: Mode) => {
    setMode(m);
    const next = new URLSearchParams(searchParams);
    next.set('mode', m);
    setSearchParams(next);
  };

  return (
    <div style={{ padding: '0', height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '12px 24px', borderBottom: '1px solid #303030', display: 'flex', alignItems: 'center', gap: 16 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Планирование <Tag color="cyan">γ</Tag></h2>
        <Segmented
          value={mode}
          onChange={v => handleModeChange(v as Mode)}
          options={[
            { label: 'Классика', value: 'classic' },
            { label: 'Ресурсо-центричный', value: 'resource' },
            { label: 'Roadmap', value: 'roadmap' },
          ]}
        />
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {mode === 'classic' && <ClassicMode />}
        {mode === 'resource' && <ResourceCentricMode />}
        {mode === 'roadmap' && <RoadmapMode />}
      </div>
    </div>
  );
}
