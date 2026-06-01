import { useState } from 'react';
import { Drawer, Tabs, Typography } from 'antd';
import BulkArchiveSection from './sections/BulkArchiveSection';
import BulkAcceptSuggestionsSection from './sections/BulkAcceptSuggestionsSection';
import BulkCascadeInheritSection, { type EpicCandidate } from './sections/BulkCascadeInheritSection';

const { Title, Text } = Typography;

type Section = 'archive' | 'accept' | 'cascade';

type Props = {
  open: boolean;
  onClose: () => void;
  selectedTeams: string[];
  scopeProjectKeys: string[];
  epicCandidates: EpicCandidate[];
};

export default function BulkTriageDrawer({
  open,
  onClose,
  selectedTeams,
  scopeProjectKeys,
  epicCandidates,
}: Props) {
  const [active, setActive] = useState<Section>('archive');

  return (
    <Drawer
      title="Массовые операции"
      placement="right"
      width={680}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      <Title level={5} style={{ marginTop: 0 }}>
        Инструменты массового разбора
      </Title>
      <Text type="secondary">
        Для онбординга руководителя проектов с большим стеком: архив по фильтру,
        применение системных подсказок, протяжка категории эпика на потомков.
      </Text>
      <Tabs
        activeKey={active}
        onChange={(k) => setActive(k as Section)}
        style={{ marginTop: 16 }}
        items={[
          {
            key: 'archive',
            label: 'Архив по фильтру',
            children: (
              <BulkArchiveSection
                selectedTeams={selectedTeams}
                scopeProjectKeys={scopeProjectKeys}
                onApplied={onClose}
              />
            ),
          },
          {
            key: 'accept',
            label: 'Принять подсказки',
            children: (
              <BulkAcceptSuggestionsSection
                selectedTeams={selectedTeams}
                scopeProjectKeys={scopeProjectKeys}
                onApplied={onClose}
              />
            ),
          },
          {
            key: 'cascade',
            label: 'Каскад от эпика',
            children: (
              <BulkCascadeInheritSection
                candidates={epicCandidates}
                onApplied={onClose}
              />
            ),
          },
        ]}
      />
    </Drawer>
  );
}
