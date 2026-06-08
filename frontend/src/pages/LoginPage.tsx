import { Button, Form, Input, Typography } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { getMe, login as apiLogin } from '../api/auth';
import { useAuth } from '../hooks/useAuth';
import { trackAction } from '../lib/usage/track';
import HelpDrawer from '../components/shared/HelpDrawer';
import loginHelp from '../../../docs/help/login.md?raw';
import { useAppTheme } from '../contexts/ThemeContext';
import { GlassCard } from '../aurora/primitives/GlassCard';

const { Title } = Typography;

interface LoginForm {
  email: string;
  password: string;
}

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const { isAurora } = useAppTheme();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  async function onFinish(values: LoginForm) {
    setLoading(true);
    setError(null);
    try {
      await apiLogin(values.email, values.password);
      const profile = await getMe();
      login(profile);
      trackAction('login');
      const redirect =
        profile.role === 'manager' && profile.default_team
          ? `/?teams=${encodeURIComponent(profile.default_team)}`
          : '/';
      navigate(redirect, { replace: true });
    } catch {
      setError('Неверный email или пароль');
    } finally {
      setLoading(false);
    }
  }

  const formInner = (
    <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
      <Form.Item name="email" label="Email" rules={[{ required: true, message: 'Введите email' }]}>
        <Input type="email" size="large" />
      </Form.Item>
      <Form.Item name="password" label="Пароль" rules={[{ required: true, message: 'Введите пароль' }]}>
        <Input.Password size="large" />
      </Form.Item>
      {error && (
        <div style={{ color: isAurora ? 'var(--bad)' : '#ff4d4f', marginBottom: 16, textAlign: 'center' }}>
          {error}
        </div>
      )}
      <Form.Item>
        <Button type="primary" htmlType="submit" size="large" block loading={loading}>
          Войти
        </Button>
      </Form.Item>
    </Form>
  );

  if (isAurora) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 20,
        }}
      >
        <GlassCard style={{ width: 380 }} padding={28}>
          <div
            className="serif"
            style={{ fontSize: 26, fontWeight: 600, textAlign: 'center', marginBottom: 6 }}
          >
            Jira Analytics
          </div>
          <div className="eyebrow" style={{ textAlign: 'center', marginBottom: 24 }}>
            Вход в сервис
          </div>
          {formInner}
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <Button
              type="text"
              size="small"
              icon={<QuestionCircleOutlined />}
              onClick={() => setHelpOpen(true)}
              style={{ color: 'var(--text-muted)' }}
            >
              Справка
            </Button>
          </div>
        </GlassCard>
        <HelpDrawer
          open={helpOpen}
          onClose={() => setHelpOpen(false)}
          title="Вход в сервис"
          content={loginHelp}
          imageBase="/help-assets/"
        />
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#141414',
      }}
    >
      <div style={{ width: 360 }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 32, color: '#fff' }}>
          Jira Analytics
        </Title>
        {formInner}
        <div style={{ textAlign: 'center', marginTop: 8 }}>
          <Button
            type="text"
            size="small"
            icon={<QuestionCircleOutlined />}
            onClick={() => setHelpOpen(true)}
            style={{ color: 'rgba(255,255,255,0.55)' }}
          >
            Справка
          </Button>
        </div>
      </div>
      <HelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title="Вход в сервис"
        content={loginHelp}
        imageBase="/help-assets/"
      />
    </div>
  );
}
