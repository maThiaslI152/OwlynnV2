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
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-gray-800 pb-2">
        <h3 className="text-lg font-medium text-gray-200">Data Connectors</h3>
        <span className="text-xs text-gray-500">Attach external knowledge sources</span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <button 
          onClick={() => handleAddConnector('GitHub')}
          className="flex items-center gap-3 p-4 bg-gray-950 border border-gray-800 rounded-xl hover:border-blue-500 hover:bg-gray-900 transition-colors text-left"
        >
          <div className="bg-gray-800 p-2 rounded-lg text-gray-300">
            <GitBranch size={20} />
          </div>
          <div>
            <div className="text-sm font-medium text-gray-200">GitHub Repository</div>
            <div className="text-xs text-gray-500">Sync code and issues</div>
          </div>
        </button>

        <button 
          onClick={() => handleAddConnector('Confluence')}
          className="flex items-center gap-3 p-4 bg-gray-950 border border-gray-800 rounded-xl hover:border-blue-500 hover:bg-gray-900 transition-colors text-left"
        >
          <div className="bg-gray-800 p-2 rounded-lg text-blue-400">
            <FileText size={20} />
          </div>
          <div>
            <div className="text-sm font-medium text-gray-200">Confluence</div>
            <div className="text-xs text-gray-500">Sync wiki pages</div>
          </div>
        </button>

        <button 
          onClick={() => handleAddConnector('Web Scraper')}
          className="flex items-center gap-3 p-4 bg-gray-950 border border-gray-800 rounded-xl hover:border-blue-500 hover:bg-gray-900 transition-colors text-left"
        >
          <div className="bg-gray-800 p-2 rounded-lg text-green-400">
            <Globe size={20} />
          </div>
          <div>
            <div className="text-sm font-medium text-gray-200">Web Scraper</div>
            <div className="text-xs text-gray-500">Crawl websites</div>
          </div>
        </button>

        <button 
          onClick={() => handleAddConnector('Vector DB')}
          className="flex items-center gap-3 p-4 bg-gray-950 border border-gray-800 rounded-xl hover:border-blue-500 hover:bg-gray-900 transition-colors text-left"
        >
          <div className="bg-gray-800 p-2 rounded-lg text-purple-400">
            <Database size={20} />
          </div>
          <div>
            <div className="text-sm font-medium text-gray-200">Vector Database</div>
            <div className="text-xs text-gray-500">Configure Qdrant/Milvus</div>
          </div>
        </button>
      </div>

      <div className="mt-8">
        <h4 className="text-sm font-medium text-gray-400 mb-3">Active Connectors</h4>
        {connectors.length === 0 ? (
          <div className="text-sm text-gray-600 text-center py-6 bg-gray-950 rounded-lg border border-gray-800 border-dashed">
            No active connectors configured.
          </div>
        ) : (
          <div className="space-y-2">
            {/* List active connectors here */}
          </div>
        )}
      </div>
    </div>
  );
};
