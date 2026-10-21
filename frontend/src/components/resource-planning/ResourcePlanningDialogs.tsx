import { Input, Modal } from 'antd';
import ScheduledBlocksModal from './ScheduledBlocksModal';
import AppearanceModal from './AppearanceModal';
import type { ResourcePlanningPageState } from '../../hooks/useResourcePlanningPage';

/** Окна страницы — общие для всех раскладок (заблокированные периоды, копия плана, цвета). */
export default function ResourcePlanningDialogs({ rp }: { rp: ResourcePlanningPageState }) {
  const {
    blocksOpen, setBlocksOpen, team, blockMembers,
    forkModalOpen, forkLabel, setForkLabel, submitFork, cancelFork, forkMutation,
    appearanceOpen, setAppearanceOpen, appearanceForEditing,
  } = rp;
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
        confirmLoading={forkMutation.isPending}
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
        current={appearanceForEditing}
        onClose={() => setAppearanceOpen(false)}
      />
    </>
  );
}
