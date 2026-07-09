import React, { useState, useEffect } from 'react';
import { fetchWithAuth } from '../utils/api';
import { Save, X } from 'lucide-react';
import toast from 'react-hot-toast';

interface SettingsPanelProps {
  onClose: () => void;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ onClose }) => {
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchWithAuth('/api/config')
      .then(res => res.json())
      .then(data => {
        setConfig(data);
        setLoading(false);
      })
      .catch(err => {
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

  if (loading) return <div className="p-8 text-center text-gray-400">Loading settings...</div>;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[80vh]">
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white">System Settings</h2>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors">
            <X size={20} />
          </button>
        </div>
        
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Models */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-200 border-b border-gray-800 pb-2">Models</h3>
            
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-400">Small Model</label>
              <input 
                type="text" 
                value={config?.models?.small?.model_name || ''} 
                onChange={e => updateConfig(['models', 'small', 'model_name'], e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-400">Complex LLM Route</label>
              <select
                value={config?.routing?.complex_llm_route || 'complex-cloud'}
                onChange={e => updateConfig(['routing', 'complex_llm_route'], e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="complex-cloud">Cloud (High Capability)</option>
                <option value="complex-local">Local (Privacy/Offline)</option>
                <option value="complex-default">Default Hybrid</option>
              </select>
            </div>
          </div>
          
          {/* Security */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-200 border-b border-gray-800 pb-2">Security & HITL</h3>
            
            <div className="flex items-center gap-3">
              <input 
                type="checkbox" 
                id="hitl_enabled"
                checked={config?.routing?.hitl_enabled ?? true}
                onChange={e => updateConfig(['routing', 'hitl_enabled'], e.target.checked)}
                className="w-4 h-4 rounded border-gray-800 bg-gray-950 focus:ring-2 focus:ring-blue-500 text-blue-500"
              />
              <label htmlFor="hitl_enabled" className="text-sm font-medium text-gray-300">
                Enable Human-In-The-Loop (HITL) Interrupts
              </label>
            </div>
            <p className="text-xs text-gray-500 pl-7">
              When enabled, destructive or sensitive tools will pause execution and request your approval.
            </p>
          </div>
        </div>
        
        <div className="p-4 border-t border-gray-800 flex justify-end gap-3 bg-gray-900/50">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-800 transition-colors">
            Cancel
          </button>
          <button onClick={handleSave} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 transition-colors">
            <Save size={16} />
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
};
