import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { Server, Activity, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../store/useAuthStore';

interface Device {
  device_id: string;
  device_type: string;
  status: string;
  last_value: number | null;
  is_anomaly: boolean;
  last_seen_at: string;
  location?: string;
  moving_avg?: number;
}

export const Devices: React.FC = () => {
  const { user } = useAuthStore();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const res = await apiClient.get('devices?page=1&size=50');
        setDevices(res.data.devices || []);
      } catch (err) {
        console.error("Failed to fetch devices", err);
      } finally {
        setLoading(false);
      }
    };
    fetchDevices();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center">
          Device Registry
        </h1>
        <p className="text-gray-400 mt-1">Historical state of all connected sensors.</p>
      </div>

      <div className="glass-card rounded-xl border border-white/5 overflow-hidden">
        {loading ? (
          <div className="p-12 flex justify-center items-center">
            <Activity className="w-8 h-8 text-brand-500 animate-spin" />
          </div>
        ) : (
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-black/20 text-gray-400 text-xs uppercase font-semibold">
              <tr>
                <th className="px-6 py-4">Device ID</th>
                <th className="px-6 py-4">Type</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Last Value</th>
                {user?.effectiveRole !== 'viewer' && <th className="px-6 py-4">Moving Avg</th>}
                {user?.effectiveRole !== 'viewer' && <th className="px-6 py-4">Location</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {devices.map((d) => (
                <tr key={d.device_id} className="hover:bg-white/5 transition-colors">
                  <td className="px-6 py-4 font-medium text-white flex items-center">
                    <Server className="w-4 h-4 mr-2 text-brand-400" />
                    {d.device_id}
                  </td>
                  <td className="px-6 py-4">
                    <span className="bg-white/10 text-gray-300 px-2 py-1 rounded text-xs">
                      {d.device_type}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    {d.is_anomaly ? (
                      <span className="text-nexus-red flex items-center"><AlertCircle className="w-4 h-4 mr-1"/> Anomaly</span>
                    ) : ( d.status === 'active' ? (
                      <span className="text-nexus-green flex items-center"><span className="w-2 h-2 rounded-full bg-nexus-green mr-2"></span> Active</span>
                    ) : (
                      <span className="text-gray-400">Offline</span>
                    ))}
                  </td>
                  <td className="px-6 py-4 font-mono text-gray-300">{d.last_value?.toFixed(2) ?? '--'}</td>
                  {user?.effectiveRole !== 'viewer' && (
                    <td className="px-6 py-4 font-mono text-gray-400">{d.moving_avg?.toFixed(2) ?? '--'}</td>
                  )}
                  {user?.effectiveRole !== 'viewer' && (
                    <td className="px-6 py-4 text-gray-400">{d.location || 'N/A'}</td>
                  )}
                </tr>
              ))}
              {devices.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">No devices found.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
