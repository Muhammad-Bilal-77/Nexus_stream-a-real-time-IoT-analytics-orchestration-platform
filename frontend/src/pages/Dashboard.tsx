import React, { useMemo } from 'react';
import { useWebSocketFeed } from '../hooks/useWebSocketFeed';
import { useAuthStore } from '../store/useAuthStore';
import { Activity, AlertTriangle, Cpu, Radio, MapPin, Search } from 'lucide-react';
import { 
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, 
  CartesianGrid, Legend
} from 'recharts';

export const Dashboard: React.FC = () => {
  const { user } = useAuthStore();
  const { feed, isConnected } = useWebSocketFeed(100);
  
  // Isolate feeds by sensor type for specific multidimensional charts
  const chartData = useMemo(() => {
    // We reverse so time goes left-to-right
    const raw = [...feed].reverse();
    
    // Process unified points that have time mapping
    return raw.map(f => ({
      time: new Date(f.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      temperature: f.device_type === 'temperature_sensor' ? f.raw_value : undefined,
      humidity: f.device_type === 'humidity_sensor' ? f.raw_value : undefined,
      vibration: f.device_type === 'vibration_sensor' ? f.raw_value : undefined,
      power: f.device_type === 'power_meter' ? f.raw_value : undefined,
      movingAvg: f.moving_avg || 0,
      isAnomaly: f.is_anomaly,
      fullMessage: f
    }));
  }, [feed]);

  // Aggregate stats
  const stats = useMemo(() => {
    const anomalies = feed.filter(f => f.is_anomaly).length;
    // Map devices unique by ID across the buffer
    const activeMapping = new Set(feed.map(f => f.device_id));
    return {
      messages: feed.length,
      anomalies,
      anomalyRate: feed.length ? Math.round((anomalies / feed.length) * 100) : 0,
      activeDevices: activeMapping.size
    };
  }, [feed]);

  // Generate topology grid (IoT MAP mock layout)
  const mapNodes = useMemo(() => {
    const uniqueDevices = new Map();
    feed.forEach(f => {
      if (!uniqueDevices.has(f.device_id) || f.is_anomaly) {
        uniqueDevices.set(f.device_id, f);
      }
    });
    return Array.from(uniqueDevices.values()).slice(0, 10); // Display up to 10 nodes geographically
  }, [feed]);

  return (
    <div className="space-y-6 pb-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center">
            Command Center
            <span className="ml-3 flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-white/5 border border-white/10">
              <span className={`w-2 h-2 rounded-full mr-2 ${isConnected ? 'bg-nexus-green animate-pulse' : 'bg-red-500'}`}></span>
              {isConnected ? 'LIVE' : 'DISCONNECTED'}
            </span>
          </h1>
          <p className="text-gray-400 mt-1">Multivariate Telemetry and Geographic Topology</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatsCard title="Stream Buffer" value={stats.messages} icon={Activity} color="text-brand-500" />
        <StatsCard title="Trace Anomalies" value={stats.anomalies} icon={AlertTriangle} color={stats.anomalies > 0 ? "text-nexus-red animate-pulse" : "text-gray-400"} />
        <StatsCard title="Anomaly Rate" value={`${stats.anomalyRate}%`} icon={Radio} color="text-purple-500" />
        <StatsCard title="Active Sensors" value={stats.activeDevices || '~'} icon={Cpu} color="text-nexus-green" />
      </div>

      {user?.effectiveRole !== 'viewer' && (
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        
        {/* Main Area Chart - Moving Averages (Span 2 Cols) */}
        <div className="glass-card p-6 rounded-xl border border-white/5 xl:col-span-2">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Aggregated Bandwidth (Global Moving Avg)</h2>
          </div>
          <div className="h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorAvg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="time" stroke="#71717a" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#71717a" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: 'rgba(24, 24, 27, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} itemStyle={{ color: '#e4e4e7' }} />
                <Area type="monotone" dataKey="movingAvg" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorAvg)" name="Moving Avg" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* IoT Map Topology */}
        <div className="glass-card p-6 rounded-xl border border-white/5 relative overflow-hidden flex flex-col">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center">
            <MapPin className="w-5 h-5 text-gray-400 mr-2" /> Geographic Topology
          </h2>
          <div className="flex-grow bg-black/40 rounded-lg relative border border-white/5">
            {/* Grid background styling */}
            <div className="absolute inset-0 z-0 opacity-20" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.2) 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
            
            {/* Render Nodes pseudorandomly based on hash of ID to simulate static placement */}
            {mapNodes.map((node, i) => {
              const hash = node.device_id.split('').reduce((a, b) => { a = ((a << 5) - a) + b.charCodeAt(0); return a & a }, 0);
              const x = Math.abs(hash % 80) + 10;
              const y = Math.abs((hash * 7) % 80) + 10;
              return (
                <div key={node.device_id} className="absolute z-10 flex flex-col items-center group cursor-pointer" style={{ left: `${x}%`, top: `${y}%` }}>
                  <div className={`w-3 h-3 rounded-full relative ${node.is_anomaly ? 'bg-nexus-red' : 'bg-brand-500'}`}>
                    <div className={`absolute inset-0 rounded-full animate-ping opacity-75 ${node.is_anomaly ? 'bg-nexus-red' : 'bg-brand-500'}`}></div>
                  </div>
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute top-4 whitespace-nowrap bg-zinc-800 text-xs px-2 py-1 flex flex-col rounded border border-white/10 z-20">
                     <span className="font-bold text-white">{node.device_id}</span>
                     <span className={node.is_anomaly ? 'text-nexus-red' : 'text-gray-400'}>{node.raw_value?.toFixed(2)}</span>
                  </div>
                </div>
              );
            })}
            {mapNodes.length === 0 && <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500 font-mono">Awaiting Spatial Data...</div>}
          </div>
        </div>
        
        {/* Specific Metrics: Temperature Line Chart */}
        <div className="glass-card p-6 rounded-xl border border-white/5">
          <h2 className="text-md font-semibold text-white mb-4 text-orange-400">Temperature Flux</h2>
          <div className="h-[200px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData.filter(d => d.temperature !== undefined)} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis stroke="#71717a" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: 'rgba(24, 24, 27, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} />
                <Line type="monotone" dataKey="temperature" stroke="#fb923c" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Specific Metrics: Vibration Bar Chart */}
        <div className="glass-card p-6 rounded-xl border border-white/5">
          <h2 className="text-md font-semibold text-white mb-4 text-purple-400">Vibration Vectors</h2>
          <div className="h-[200px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData.filter(d => d.vibration !== undefined)} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis stroke="#71717a" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: 'rgba(24, 24, 27, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} cursor={{fill: 'rgba(255,255,255,0.05)'}} />
                <Bar dataKey="vibration" fill="#c084fc" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        
        {/* Specific Metrics: Humidity Line Chart */}
        <div className="glass-card p-6 rounded-xl border border-white/5">
          <h2 className="text-md font-semibold text-white mb-4 text-cyan-400">Humidity Levels</h2>
          <div className="h-[200px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData.filter(d => d.humidity !== undefined)} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis stroke="#71717a" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ backgroundColor: 'rgba(24, 24, 27, 0.9)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }} />
                <Line type="step" dataKey="humidity" stroke="#22d3ee" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      )}

      {/* Telemetry Log Dump Table */}
      <div className="glass-card rounded-xl border border-white/5 overflow-hidden flex flex-col">
        <div className="p-4 border-b border-white/5 flex justify-between items-center bg-white/[0.02]">
          <h2 className="text-lg font-semibold text-white flex items-center"><Search className="w-4 h-4 mr-2 text-gray-400"/> Diagnostic Pipeline Log</h2>
          <span className="text-xs text-gray-400">Matrix Filtering applied for: <strong className="text-brand-400 uppercase">{user?.effectiveRole}</strong></span>
        </div>
        <div className="overflow-x-auto max-h-[400px]">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-black/40 text-gray-400 text-xs uppercase font-semibold sticky top-0 z-10 backdrop-blur-md">
              <tr>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Location / Device</th>
                <th className="px-4 py-3">Telemetry Focus</th>
                <th className="px-4 py-3">Health Status</th>
                {user?.effectiveRole !== 'viewer' && <th className="px-4 py-3">Value</th>}
                <th className="px-4 py-3 text-right">Raw Dump (Truncated)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {feed.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Awaiting stream...</td></tr>
              ) : (
                feed.map((msg, idx) => (
                  <tr key={`${msg.timestamp}-${idx}`} className={`transition-colors hover:bg-white/5 ${msg.is_anomaly ? 'bg-nexus-red/10 border-l-2 border-nexus-red' : 'border-l-2 border-transparent'}`}>
                    <td className="px-4 py-3 text-gray-400 font-mono text-xs">{msg.timestamp}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col">
                        <span className="font-medium text-white">{msg.device_id}</span>
                        <span className="text-[10px] text-gray-500">{msg.location || 'Unknown GPS'}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-white/10 text-gray-300 tracking-wider ring-1 ring-white/5">{msg.device_type.split('_')[0]}</span>
                    </td>
                    <td className="px-4 py-3">
                      {msg.is_anomaly 
                        ? <span className="inline-flex items-center text-xs font-medium text-red-400"><AlertTriangle className="w-3 h-3 mr-1"/> FAULT</span>
                        : <span className="inline-flex items-center text-xs font-medium text-green-400">NOMINAL</span>
                      }
                    </td>
                    {user?.effectiveRole !== 'viewer' && (
                      <td className="px-4 py-3 font-mono text-gray-300 font-bold">{msg.raw_value ? msg.raw_value.toFixed(2) : '--'}</td>
                    )}
                    <td className="px-4 py-3 font-mono text-gray-500 text-[10px] text-right truncate max-w-[200px]">
                      {JSON.stringify(msg).substring(0, 100)}...
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      
    </div>
  );
};

// Helper card component
function StatsCard({ title, value, icon: Icon, color }: { title: string, value: string | number, icon: any, color: string }) {
  return (
    <div className="glass-card rounded-xl border border-white/5 p-5 flex items-center justify-between shadow-lg">
      <div>
        <p className="text-sm font-medium text-gray-400 mb-1">{title}</p>
        <p className="text-2xl font-bold text-white tracking-widest">{value}</p>
      </div>
      <div className={`p-3 rounded-lg bg-black/30 ring-1 ring-white/10 ${color}`}>
        <Icon className="w-6 h-6" />
      </div>
    </div>
  );
}
