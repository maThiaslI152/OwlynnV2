import React, { useState, useEffect } from 'react';
import { fetchWithAuth } from '../../lib/localRunToken';
import { DataConnectorsPanel } from './DataConnectorsPanel';
import { Save, X, Eye, EyeOff } from 'lucide-react';
import toast from 'react-hot-toast';

interface SettingsPanelProps {
  onClose: () => void;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ onClose }) => {
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'general' | 'cloud' | 'connectors'>('general');
  const [cloudKey, setCloudKey] = useState('');
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchWithAuth('/api/config').then((r: any) => r.json()),
      fetchWithAuth('/api/unified-settings').then((r: any) => r.json()),
    ])
      .then(([cfg, unified]: [any, any]) => {
        setConfig(cfg);
        // Show masked placeholder if key already stored
        if (unified?.deepseek_api_key) setCloudKey(unified.deepseek_api_key);
        setLoading(false);
      })
      .catch((err: any) => {
        console.error(err);
        toast.error('Failed to load settings');
        setLoading(false);
      });
  }, []);

  const handleSave = async () => {
    try {
      await fetchWithAuth('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      // Save cloud key if changed (skip masked placeholder)
      if (cloudKey && cloudKey !== '••••••••') {
        await fetchWithAuth('/api/unified-settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ deepseek_api_key: cloudKey }),
        });
      } else if (cloudKey === '') {
        await fetchWithAuth('/api/unified-settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ deepseek_api_key: '' }),
        });
      }
      toast.success('Settings saved successfully');
      onClose();
    } catch (err) {
      console.error(err);
      toast.error('Failed to save settings');
    }
  };

  const updateConfig = (path: string[], value: any) => {
    const newConfig = { ...config };
    let current = newConfig;
    for (let i = 0; i < path.length - 1; i++) {
      if (!current[path[i]]) current[path[i]] = {};
      current = current[path[i]];
    }
    current[path[path.length - 1]] = value;
    setConfig(newConfig);
  };

  if (loading) {
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(16px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 99999,
          WebkitAppRegion: 'no-drag',
        } as React.CSSProperties}
      >
        <div
          style={{
            background: 'var(--bg-elevated, #162438)',
            border: '1px solid var(--border-default)',
            borderRadius: '12px',
            padding: '32px 48px',
            color: 'var(--text-muted)',
            fontSize: '14px',
          }}
        >
          Loading settings...
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(16px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 99999,
        WebkitAppRegion: 'no-drag',
        padding: '20px',
      } as React.CSSProperties}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-elevated, #142032)',
          border: '1px solid var(--border-default)',
          borderRadius: '14px',
          boxShadow: '0 25px 60px rgba(0, 0, 0, 0.8)',
          width: '100%',
          maxWidth: '640px',
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          WebkitAppRegion: 'no-drag',
        } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>System Settings</h2>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '4px',
              borderRadius: '6px',
              display: 'inline-flex',
              alignItems: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div
          style={{
            padding: '8px 20px 0',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            gap: '16px',
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab('general')}
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'general' ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === 'general' ? 'var(--accent)' : 'var(--text-muted)',
              fontWeight: activeTab === 'general' ? 600 : 400,
              fontSize: '13px',
              padding: '6px 2px 10px',
              cursor: 'pointer',
            }}
          >
            General
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('cloud')}
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'cloud' ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === 'cloud' ? 'var(--accent)' : 'var(--text-muted)',
              fontWeight: activeTab === 'cloud' ? 600 : 400,
              fontSize: '13px',
              padding: '6px 2px 10px',
              cursor: 'pointer',
            }}
          >
            Cloud
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('connectors')}
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === 'connectors' ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === 'connectors' ? 'var(--accent)' : 'var(--text-muted)',
              fontWeight: activeTab === 'connectors' ? 600 : 400,
              fontSize: '13px',
              padding: '6px 2px 10px',
              cursor: 'pointer',
            }}
          >
            Data Connectors
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'cloud' && (
          <div style={{ padding: '20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <h3
                style={{
                  fontSize: '13px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--text-muted)',
                  borderBottom: '1px solid var(--border-subtle)',
                  paddingBottom: '6px',
                  marginBottom: '14px',
                }}
              >
                Cloud API
              </h3>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                  DeepSeek API Key
                </label>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px', lineHeight: 1.4 }}>
                  Stored securely in macOS Keychain. Used for cloud-routed complex queries.
                </p>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={cloudKey}
                    onChange={(e) => setCloudKey(e.target.value)}
                    placeholder="sk-..."
                    autoComplete="off"
                    style={{
                      width: '100%',
                      background: 'rgba(0, 0, 0, 0.35)',
                      border: '1px solid var(--border-default)',
                      borderRadius: '8px',
                      padding: '8px 40px 8px 12px',
                      color: 'var(--text-primary)',
                      fontSize: '13px',
                      outline: 'none',
                      fontFamily: 'var(--font-mono)',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    style={{
                      position: 'absolute',
                      right: 10,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: 0,
                    }}
                    aria-label={showKey ? 'Hide key' : 'Show key'}
                  >
                    {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                {cloudKey === '••••••••' && (
                  <p style={{ fontSize: '11px', color: 'var(--green)', marginTop: '6px' }}>
                    Key already saved. Enter a new value to replace it, or clear to remove.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
        {activeTab === 'general' ? (
          <div style={{ padding: '20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Models Section */}
            <div>
              <h3
                style={{
                  fontSize: '13px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--text-muted)',
                  borderBottom: '1px solid var(--border-subtle)',
                  paddingBottom: '6px',
                  marginBottom: '14px',
                }}
              >
                Models
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                    Main Model
                  </label>
                  <input
                    type="text"
                    value={config?.models?.main?.model_name || config?.models?.small?.model_name || ''}
                    onChange={(e) => updateConfig(['models', 'main', 'model_name'], e.target.value)}
                    style={{
                      width: '100%',
                      background: 'rgba(0, 0, 0, 0.35)',
                      border: '1px solid var(--border-default)',
                      borderRadius: '8px',
                      padding: '8px 12px',
                      color: 'var(--text-primary)',
                      fontSize: '13px',
                      outline: 'none',
                      fontFamily: 'var(--font-mono)',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                    Complex LLM Route
                  </label>
                  <select
                    value={config?.routing?.complex_llm_route || 'complex-cloud'}
                    onChange={(e) => updateConfig(['routing', 'complex_llm_route'], e.target.value)}
                    style={{
                      width: '100%',
                      background: 'var(--bg-surface, #0f1a2a)',
                      border: '1px solid var(--border-default)',
                      borderRadius: '8px',
                      padding: '8px 12px',
                      color: 'var(--text-primary)',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                  >
                    <option value="complex-cloud">Cloud (High Capability)</option>
                    <option value="complex-local">Local (Privacy/Offline)</option>
                    <option value="complex-default">Default Hybrid</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Security Section */}
            <div>
              <h3
                style={{
                  fontSize: '13px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--text-muted)',
                  borderBottom: '1px solid var(--border-subtle)',
                  paddingBottom: '6px',
                  marginBottom: '14px',
                }}
              >
                Security & HITL
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    id="hitl_enabled"
                    checked={config?.routing?.hitl_enabled ?? true}
                    onChange={(e) => updateConfig(['routing', 'hitl_enabled'], e.target.checked)}
                    style={{ accentColor: 'var(--accent)', width: '16px', height: '16px', cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
                    Enable Human-In-The-Loop (HITL) Interrupts
                  </span>
                </label>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', paddingLeft: '26px', lineHeight: 1.4 }}>
                  When enabled, destructive or sensitive tools will pause execution and request your approval.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
            <DataConnectorsPanel />
          </div>
        )}

        {/* Footer */}
        <div
          style={{
            padding: '14px 20px',
            borderTop: '1px solid var(--border-subtle)',
            background: 'rgba(0, 0, 0, 0.25)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              borderRadius: '8px',
              padding: '8px 16px',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            style={{
              background: 'var(--accent)',
              border: 'none',
              color: '#000',
              fontWeight: 600,
              borderRadius: '8px',
              padding: '8px 18px',
              fontSize: '13px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Save size={15} />
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};
