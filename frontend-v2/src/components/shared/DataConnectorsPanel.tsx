import React from 'react';
import { Database, GitBranch, FileText, Globe } from 'lucide-react';
import toast from 'react-hot-toast';


export const DataConnectorsPanel: React.FC = () => {
  const connectors = [] as any[];

  const handleAddConnector = (type: string) => {
    toast.success(`Started setup for ${type} connector. Check backend logs.`);
    // Stub for adding a connector
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Data Connectors</h3>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Attach external knowledge sources</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <button 
          type="button"
          onClick={() => handleAddConnector('GitHub')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '14px',
            background: 'var(--bg-surface, rgba(0,0,0,0.3))',
            border: '1px solid var(--border-default)',
            borderRadius: '10px',
            textAlign: 'left',
            cursor: 'pointer',
            color: 'inherit',
          }}
        >
          <div style={{ background: 'rgba(255, 255, 255, 0.08)', padding: '8px', borderRadius: '8px', color: 'var(--text-secondary)', display: 'flex' }}>
            <GitBranch size={18} />
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>GitHub Repository</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Sync code and issues</div>
          </div>
        </button>

        <button 
          type="button"
          onClick={() => handleAddConnector('Confluence')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '14px',
            background: 'var(--bg-surface, rgba(0,0,0,0.3))',
            border: '1px solid var(--border-default)',
            borderRadius: '10px',
            textAlign: 'left',
            cursor: 'pointer',
            color: 'inherit',
          }}
        >
          <div style={{ background: 'rgba(59, 130, 246, 0.15)', padding: '8px', borderRadius: '8px', color: '#60a5fa', display: 'flex' }}>
            <FileText size={18} />
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Confluence</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Sync wiki pages</div>
          </div>
        </button>

        <button 
          type="button"
          onClick={() => handleAddConnector('Web Scraper')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '14px',
            background: 'var(--bg-surface, rgba(0,0,0,0.3))',
            border: '1px solid var(--border-default)',
            borderRadius: '10px',
            textAlign: 'left',
            cursor: 'pointer',
            color: 'inherit',
          }}
        >
          <div style={{ background: 'rgba(34, 197, 94, 0.15)', padding: '8px', borderRadius: '8px', color: '#4ade80', display: 'flex' }}>
            <Globe size={18} />
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Web Scraper</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Crawl websites</div>
          </div>
        </button>

        <button 
          type="button"
          onClick={() => handleAddConnector('Vector DB')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '14px',
            background: 'var(--bg-surface, rgba(0,0,0,0.3))',
            border: '1px solid var(--border-default)',
            borderRadius: '10px',
            textAlign: 'left',
            cursor: 'pointer',
            color: 'inherit',
          }}
        >
          <div style={{ background: 'rgba(168, 85, 247, 0.15)', padding: '8px', borderRadius: '8px', color: '#c084fc', display: 'flex' }}>
            <Database size={18} />
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>Vector Database</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Configure Qdrant/Milvus</div>
          </div>
        </button>
      </div>

      <div style={{ marginTop: '16px' }}>
        <h4 style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: '10px' }}>Active Connectors</h4>
        {connectors.length === 0 ? (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', textAlign: 'center', padding: '24px', background: 'rgba(0, 0, 0, 0.2)', borderRadius: '8px', border: '1px dashed var(--border-subtle)' }}>
            No active connectors configured.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {/* List active connectors here */}
          </div>
        )}
      </div>
    </div>
  );
};
