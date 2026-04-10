import React, { useState } from 'react';
import { apiClient } from '../api/client';
import { Database, Trash2, CheckCircle2, AlertTriangle } from 'lucide-react';
import { useAuthStore } from '../store/useAuthStore';
import { Navigate } from 'react-router-dom';

export const AdminPanel: React.FC = () => {
  const { user } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  if (user?.effectiveRole !== 'admin') {
    return <Navigate to="/" replace />;
  }

  const handleClearCache = async () => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await apiClient.delete('/admin/cache');
      setMsg({ text: res.data.message || 'Cache reset successfully.', type: 'success' });
    } catch (err: any) {
      setMsg({ text: err.response?.data?.error || 'Failed to clear cache.', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center">
          Administration
        </h1>
        <p className="text-gray-400 mt-1">Platform management and danger zones.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Cache Management Box */}
        <div className="glass-card rounded-xl border border-red-500/20 p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center mb-2">
              <Database className="w-5 h-5 text-red-400 mr-2" />
              <h2 className="text-lg font-semibold text-white">System Cache</h2>
            </div>
            <p className="text-sm text-gray-400 mb-6">
              Force clear all dashboard Redis caches. InfluxDB queries will be freshly executed on the next request. This may temporarily spike database latency.
            </p>
            
            {msg && (
              <div className={`p-3 mb-4 rounded-lg text-sm flex items-center border ${
                msg.type === 'success' ? 'bg-green-500/10 border-green-500/20 text-green-400' : 'bg-red-500/10 border-red-500/20 text-red-400'
              }`}>
                {msg.type === 'success' ? <CheckCircle2 className="w-4 h-4 mr-2" /> : <AlertTriangle className="w-4 h-4 mr-2" />}
                {msg.text}
              </div>
            )}
            
          </div>
          <button
            onClick={handleClearCache}
            disabled={loading}
            className="self-start flex items-center px-4 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-500 rounded-lg transition-colors disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4 mr-2" />
            {loading ? 'Clearing...' : 'Wipe Redis Cache'}
          </button>
        </div>
      </div>
    </div>
  );
};
