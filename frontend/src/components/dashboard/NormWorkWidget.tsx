import { useState } from 'react';
import { Card, Spin, Empty, Tooltip, Modal, InputNumber, Form } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import type { DashboardNormWorkResponse, NormWorkItem } from '../../types/api';

interface Thresholds { warnAbove: number; underBelow: number; }

// <underBelow → зелёный, underBelow..warnAbove → жёлтый, >warnAbove → красный
function barColor(pct: number, t: Thresholds): string {
  if (pct > t.warnAbove) return '#ff4d4f';
  if (pct >= t.underBelow) return '#faad14';
  return '#52c41a';
}

function BulletBar({ item, thresholds }: { item: NormWorkItem; thresholds: Thresholds }) {
  const color = barColor(item.pct, thresholds);
  const targetPct = 66;
  const factFillWidth = item.plan_hours > 0
    ? Math.min(targetPct, (item.fact_hours / item.plan_hours) * targetPct)
    : 0;
  const overrunWidth = item.plan_hours > 0 && item.fact_hours > item.plan_hours
    ? Math.min(100 - targetPct, ((item.fact_hours - item.plan_hours) / item.plan_hours) * targetPct)
    : 0;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '160px 1fr 90px',
        alignItems: 'center',
        gap: 12,
        padding: '8px 0',
        borderBottom: '1px solid rgba(28,51,88,.4)',
      }}
    >
      <div style={{ fontSize: 14, color: '#e6edf7', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {item.label}
      </div>
      <div style={{ position: 'relative', height: 26, background: '#1c3358', borderRadius: 6, overflow: 'visible' }}>
        <div style={{
          position: 'absolute', top: 0, left: 0,
          height: '100%', width: `${factFillWidth}%`,
          background: color, borderRadius: 6, transition: 'width .3s',
        }} />
        {overrunWidth > 0 && (
          <div style={{
            position: 'absolute', top: 0, left: `${targetPct}%`,
            height: '100%', width: `${overrunWidth}%`,
            background: '#ff4d4f', borderRadius: '0 6px 6px 0', transition: 'width .3s',
          }} />
        )}
        <div style={{
          position: 'absolute', top: -4, bottom: -4, left: `${targetPct}%`,
          width: 2, background: '#fff', borderRadius: 1,
        }} />
      </div>
      <div style={{ textAlign: 'right', fontSize: 13 }}>
        <span style={{ color, fontWeight: 700 }}>{item.pct.toFixed(0)}%</span>
        <div style={{ color: '#7e94b8', fontSize: 11, marginTop: 1 }}>
          {Math.round(item.fact_hours)}/{Math.round(item.plan_hours)} ч
        </div>
      </div>
    </div>
  );
}

interface Props {
  data: DashboardNormWorkResponse | undefined;
  loading: boolean;
}

const DEFAULT_THRESHOLDS: Thresholds = { warnAbove: 110, underBelow: 70 };

export default function NormWorkWidget({ data, loading }: Props) {
  const [thresholds, setThresholds] = useState<Thresholds>(DEFAULT_THRESHOLDS);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<Thresholds>();

  const summaryExtra = data && !loading ? (
    <span style={{ display: 'flex', alignItems: 'center', gap: 24, fontSize: 15, color: '#7e94b8' }}>
      <span>Σ план: <b style={{ color: '#fff', fontSize: 16 }}>{Math.round(data.total_plan)} ч</b></span>
      <span>Σ факт: <b style={{ color: '#fff', fontSize: 16 }}>{Math.round(data.total_fact)} ч</b></span>
      <span>Загрузка: <b style={{ color: barColor(data.total_pct, thresholds), fontSize: 16 }}>{data.total_pct.toFixed(0)}%</b></span>
    </span>
  ) : null;

  const gearIcon = (
    <Tooltip title="Настройка порогов">
      <SettingOutlined
        style={{ cursor: 'pointer', color: '#7e94b8', fontSize: 16 }}
        onClick={() => { form.setFieldsValue(thresholds); setModalOpen(true); }}
      />
    </Tooltip>
  );

  const cardTitle = (
    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: 16 }}>
      <span style={{ fontSize: 15, fontWeight: 600, color: '#e6edf7', whiteSpace: 'nowrap' }}>
        Нормированные работы: план / факт
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 28, flex: 1, justifyContent: 'center' }}>
        {summaryExtra}
      </span>
      {gearIcon}
    </span>
  );

  if (loading) return <Card title="Нормированные работы"><Spin /></Card>;
  if (!data?.items.length) return <Card title={cardTitle}><Empty description="Нет данных" /></Card>;

  return (
    <>
      <Card title={cardTitle}>
        {data.items.map((item) => (
          <BulletBar key={item.work_type_id} item={item} thresholds={thresholds} />
        ))}
      </Card>

      <Modal
        title="Настройка порогов загрузки"
        open={modalOpen}
        onOk={() => form.validateFields().then(v => { setThresholds(v); setModalOpen(false); })}
        onCancel={() => setModalOpen(false)}
        okText="Применить"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="Перегруз — выше, % (красный)" name="warnAbove"
            rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} addonAfter="%" />
          </Form.Item>
          <Form.Item label="Недозагрузка — ниже, % (жёлтый)" name="underBelow"
            rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} addonAfter="%" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
