import {
  Alert, Badge, Button, Card, Popconfirm, Select, Space, Switch, Tooltip, Typography,
} from 'antd';
import {
  BarChartOutlined, CheckCircleOutlined, DeleteOutlined, DiffOutlined, HistoryOutlined,
  PlusOutlined, RollbackOutlined, SwapOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import PlanningCapacityPanel from '../components/planning/PlanningCapacityPanel';
import ScenarioRulesEditor from '../components/planning/ScenarioRulesEditor';
import ExternalQaInput from '../components/planning/ExternalQaInput';
import ScenarioResourceSummary from '../components/planning/ScenarioResourceSummary';
import ScenarioDeficitBadge from '../components/planning/ScenarioDeficitBadge';
import CapacityDriftIndicator from '../components/planning/CapacityDriftIndicator';
import ScenarioBacklogTable from '../components/planning/ScenarioBacklogTable';
import { planningOverlays } from '../components/planning/planningOverlays';
import { TeamSelector } from '../components/planning/TeamSelector';
import { DARK_THEME, FONTS } from '../utils/constants';
import { useSkin } from '../contexts/ThemeContext';
import { usePlanningPage, type PlanningPageModel } from '../hooks/usePlanningPage';
import SwissPlanningLayout from '../skins/swiss/pages/PlanningLayout';

/** Раскладка Aurora: шапка с выбором сценария, карточка сценария, сводка ресурса, бэклог и ресурс справа. */
function AuroraPlanningLayout({ vm }: { vm: PlanningPageModel }) {
  const {
    navigate, scenarioId, setScenarioId, scenario, scenarioOptions, setCompareOpen, setInvolvementOpen,
    setCreateOpen, handleTeamChange, handleRename, isApproved, isDraft, deficit, allocations, includedIds,
    ungrouped, handleApprove, approve, handleRevert, revert, openDiagram, setDiffOpen, setHistoryOpen,
    liftIncluded, setLiftIncluded, handleExport, handleDelete, resourceBase, pulsedRoles, activeTab,
    setActiveTab, setUngroupedDrawerId, allocLoading, setRightColumnEl, rightColumnHeight, quarterInt,
    resourceSummary,
  } = vm;
  const overlays = planningOverlays(vm);

  return (
    <Space orientation="vertical" size={12} style={{ width: '100%' }}>
      <div>
      <PageHeader
        eyebrow="Планирование"
        title="Сценарии"
        subtitle="Отметьте галочками задачи из бэклога — сформируется план квартала"
        actions={
          <Space>
            <Select
              data-tour="planning-scenario-select"
              style={{ minWidth: 320 }}
              placeholder="Выберите сценарий"
              value={scenarioId ?? undefined}
              onChange={(v) => setScenarioId(v)}
              options={scenarioOptions}
              allowClear
              onClear={() => setScenarioId(null)}
            />
            <Tooltip title="Сравнить два сценария">
              <Button icon={<SwapOutlined />} onClick={() => setCompareOpen(true)}>
                Сравнить
              </Button>
            </Tooltip>
            <Tooltip title="Вовлечённость и нормированные работы">
              <Button onClick={() => setInvolvementOpen(true)} data-tour="planning-involvement">
                Вовлечённость
              </Button>
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)} data-tour="planning-new-scenario">
              Новый сценарий
            </Button>
          </Space>
        }
      />
      </div>

      {overlays.create}

      {!scenarioId && (
        <Card>
          <div style={{ textAlign: 'center', padding: 40, color: DARK_THEME.textMuted }}>
            Сценарии отсутствуют или не выбраны. Нажмите «Новый сценарий», чтобы
            начать планирование квартала.
          </div>
        </Card>
      )}

      {scenarioId && scenario && !scenario.team && (
        <Card>
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Alert
              type="info"
              title="Для работы со сценарием выберите команду"
              description="Сценарий привязан к конкретной команде — именно по ней считается ресурс и загрузка."
              showIcon
            />
            <TeamSelector
              value={scenario.team || null}
              onChange={handleTeamChange}
            />
          </Space>
        </Card>
      )}

      {scenarioId && scenario && !!scenario.team && (
        // Намеренно plain `<div>`, не AntD `<Space>`: Space оборачивает каждого
        // ребёнка в `.ant-space-item`, который становится containing-block'ом
        // для `position: sticky` на ScenarioResourceSummary — и поскольку он
        // высотой ровно равен таблице, прилипать некуда. Тут все дочерние
        // элементы лежат прямо в flex-контейнере, и sticky упирается в его
        // полную высоту страницы.
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, width: '100%' }}>
          <Card
            styles={{ body: { padding: '14px 18px' } }}
            style={{ background: DARK_THEME.cardBg }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span data-tour="planning-scenario-name">
                <Typography.Text
                  editable={{
                    onChange: handleRename,
                    tooltip: 'Переименовать',
                    maxLength: 200,
                  }}
                  style={{ fontSize: 18, fontWeight: 600, color: DARK_THEME.textPrimary, margin: 0 }}
                >
                  {scenario.name}
                </Typography.Text>
                </span>
                <span style={{ color: DARK_THEME.textMuted, fontFamily: FONTS.mono, fontSize: 13 }}>
                  {scenario.quarter} {scenario.year}
                </span>
                <Badge
                  status={isApproved ? 'success' : 'processing'}
                  text={isApproved ? 'Утверждён' : 'Черновик'}
                />
                <ScenarioDeficitBadge deficit={deficit} />
                {allocations && (
                  <span style={{ color: DARK_THEME.textHint, fontSize: 12 }}>
                    включено {includedIds.length} из {allocations.length}
                  </span>
                )}
              </div>
              <Space>
                {isDraft ? (
                  ungrouped.length > 0 ? (
                    <Tooltip title={`Сначала проставьте группы: ${ungrouped.map((u) => u.display_name).join(', ')}`}>
                      {/* Tooltip не показывается на disabled-кнопках без обёртки. */}
                      <span style={{ display: 'inline-block', cursor: 'not-allowed' }}>
                        <Button
                          type="primary"
                          icon={<CheckCircleOutlined />}
                          size="small"
                          disabled
                          data-tour="planning-approve"
                        >
                          Утвердить
                        </Button>
                      </span>
                    </Tooltip>
                  ) : (
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      size="small"
                      onClick={handleApprove}
                      loading={approve.isPending}
                      data-tour="planning-approve"
                    >
                      Утвердить
                    </Button>
                  )
                ) : (
                  <Button
                    icon={<RollbackOutlined />}
                    size="small"
                    onClick={handleRevert}
                    loading={revert.isPending}
                    data-tour="planning-revert"
                  >
                    В черновик
                  </Button>
                )}
                {isApproved && scenario && (
                  <Button
                    size="small"
                    icon={<BarChartOutlined />}
                    onClick={openDiagram}
                    data-tour="planning-diagram"
                  >
                    Диаграмма
                  </Button>
                )}
                {isDraft && (
                  <Tooltip title="Сравнить с последним утверждённым">
                    <Button
                      icon={<DiffOutlined />}
                      size="small"
                      onClick={() => setDiffOpen(true)}
                    >
                      Diff
                    </Button>
                  </Tooltip>
                )}
                <Tooltip title="История ревизий и сравнение снапшотов">
                  <Button
                    icon={<HistoryOutlined />}
                    size="small"
                    onClick={() => setHistoryOpen(true)}
                  >
                    История
                  </Button>
                </Tooltip>
                <Tooltip title="При включении задача поднимается в начало списка">
                  <Space size={6} data-tour="planning-lift-toggle">
                    <Switch
                      size="small"
                      checked={liftIncluded}
                      onChange={setLiftIncluded}
                    />
                    <span style={{ color: DARK_THEME.textHint, fontSize: 12 }}>
                      поднимать наверх
                    </span>
                  </Space>
                </Tooltip>
                <Button
                  size="small"
                  onClick={handleExport}
                >
                  Экспорт
                </Button>
                <Popconfirm
                  title="Удалить сценарий?"
                  description="Вместе с раскладками. Отменить нельзя."
                  onConfirm={handleDelete}
                >
                  <Button danger size="small" icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            </div>
            {isApproved && scenarioId && (
              <CapacityDriftIndicator scenarioId={scenarioId} />
            )}
          </Card>

          <ScenarioResourceSummary
            scenarioId={scenarioId}
            enabled={!!scenario.team}
            allocations={allocations ?? []}
            employees={resourceBase?.employees}
            pulsedRoles={pulsedRoles}
          />

          {/* Вкладки — на всю ширину над сеткой */}
          <div style={{
            display: 'flex',
            borderBottom: `1px solid ${DARK_THEME.border}`,
            marginBottom: 0,
          }}>
            {(['distribution', 'rules'] as const).map((key) => (
              <div
                key={key}
                data-tour={`planning-tab-${key}`}
                onClick={() => setActiveTab(key)}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: 14,
                  borderBottom: activeTab === key ? `2px solid ${DARK_THEME.cyanPrimary}` : '2px solid transparent',
                  marginBottom: -1,
                  color: activeTab === key ? DARK_THEME.cyanPrimary : DARK_THEME.textMuted,
                  transition: 'color .15s',
                  userSelect: 'none' as const,
                }}
              >
                {key === 'distribution' ? 'Распределение' : 'Правила'}
              </div>
            ))}
          </div>

          {isDraft && ungrouped.length > 0 && (
            <Alert
              type="error"
              showIcon
              title={`Без группы: ${ungrouped.length} чел. — сценарий нельзя утвердить`}
              description={
                <>
                  {ungrouped.map((u, i) => (
                    <span key={u.employee_id}>
                      {i > 0 && ', '}
                      <a onClick={() => setUngroupedDrawerId(u.employee_id)}>{u.display_name}</a>
                    </span>
                  ))}
                  {' — '}
                  <a onClick={() => navigate('/capacity')}>Открыть «Ресурсы»</a>
                </>
              }
            />
          )}

          {/* Двуколоночная сетка */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', gap: 16, alignItems: 'start' }}>
            {/* Левая колонка — контент активной вкладки */}
            {activeTab === 'distribution' ? (
              <Card
                title="Элементы бэклога"
                styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', flex: 1 } }}
                style={{ display: 'flex', flexDirection: 'column', flex: 1 }}
                loading={allocLoading}
                extra={
                  <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                    {isApproved
                      ? 'сценарий утверждён — отметки заблокированы'
                      : 'клик по строке переключает включение'}
                  </span>
                }
              >
                <ScenarioBacklogTable vm={vm} />
              </Card>
            ) : (
              <Card
                data-tour="planning-rules-card"
                title="Правила обязательных работ"
                styles={{ body: { padding: 14 } }}
                style={{ background: DARK_THEME.cardBg }}
              >
                <ScenarioRulesEditor scenarioId={scenarioId} />
              </Card>
            )}

            {/* Правая колонка — sticky сверху, со своей прокруткой: секции по
                группам сделали блок выше экрана, и без этого до его низа
                приходилось прокручивать весь бэклог. Высоту берём от реального
                контейнера прокрутки — в Aurora страница листается внутри
                собственного вьюпорта, и 100vh там обрезал нижнюю карточку. */}
            <div
              ref={setRightColumnEl}
              style={{
                position: 'sticky',
                top: 56,
                alignSelf: 'start',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                maxHeight: rightColumnHeight,
                overflowY: 'auto',
                paddingRight: 4,
              }}
            >
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
                scenarioId={scenarioId}
                summary={resourceSummary}
              />
              <Card size="small" styles={{ body: { padding: 12 } }}>
                <ExternalQaInput
                  scenarioId={scenarioId}
                  value={scenario.external_qa_hours}
                  disabled={!isDraft}
                />
              </Card>
            </div>
          </div>
        </div>
      )}
      {overlays.rest}
    </Space>
  );
}

export default function PlanningPage() {
  const vm = usePlanningPage();
  const skin = useSkin();
  return skin === 'swiss' ? <SwissPlanningLayout vm={vm} /> : <AuroraPlanningLayout vm={vm} />;
}
