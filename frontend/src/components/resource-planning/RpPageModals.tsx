import { Input, Modal } from 'antd';
import ScheduledBlocksModal from './ScheduledBlocksModal';
import AppearanceModal from './AppearanceModal';
import { useAppearanceSettings } from '../../contexts/AppearanceContext';
import type { ResourcePlanningPageState } from '../../hooks/useResourcePlanningPage';

/** Окна страницы ресурсного планирования: заблокированные периоды, копия плана, цвета. */
export default function RpPageModals({ state }: { state: ResourcePlanningPageState }) {
  const {
    blocksOpen, setBlocksOpen, team, blockMembers,
    forkModalOpen, forkLabel, setForkLabel, forkPending, submitFork, cancelFork,
    appearanceOpen, setAppearanceOpen,
  } = state;
  const appearanceSettings = useAppearanceSettings();
  return (
    <>
      <ScheduledBlocksModal
        open={blocksOpen}
        onClose={() => setBlocksOpen(false)}
        team={team || undefined}
        members={blockMembers}
      />

      <Modal
        open={forkModalOpen}
        title="Сделать копию плана"
        okText="Создать"
        cancelText="Отмена"
        onOk={submitFork}
        onCancel={cancelFork}
        confirmLoading={forkPending}
      >
        <Input
          placeholder="Метка сценария (например: «+1 разработчик»)"
          value={forkLabel}
          onChange={e => setForkLabel(e.target.value)}
          autoFocus
        />
      </Modal>

      <AppearanceModal
        open={appearanceOpen}
        current={appearanceSettings}
        onClose={() => setAppearanceOpen(false)}
      />
    </>
  );
}
