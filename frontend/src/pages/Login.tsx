import React, { useState, useEffect, useMemo } from 'react';
import { Activity, Lock, Mail, Shield, HardHat, Users, Terminal, Cpu, Clock, Zap, Globe, Database, Network } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis } from 'recharts';
import { authClient } from '../api/client';
import { useAuthStore } from '../store/useAuthStore';
import { Navigate } from 'react-router-dom';

// --- Mock Data Generators ---
const generateTimeSeries = () => [...Array(20)].map((_, i) => ({ time: i, value: 40 + Math.random() * 60 }));
const generateBarData = () => [
  { name: 'US-East', val: 80 + Math.random() * 20 },
  { name: 'EU-West', val: 70 + Math.random() * 30 },
  { name: 'AP-South', val: 60 + Math.random() * 40 },
  { name: 'SA-East', val: 40 + Math.random() * 60 }
];
const radarData = [
  { subject: 'Security', val: 120 },
  { subject: 'Integrity', val: 98 },
  { subject: 'Uptime', val: 110 },
  { subject: 'Shield', val: 85 },
  { subject: 'Nodes', val: 105 },
  { subject: 'Traffic', val: 115 },
];

export const Login: React.FC = () => {
  const { isAuthenticated } = useAuthStore();
  
  const [email, setEmail] = useState('');
  const [selectedRole, setSelectedRole] = useState<'admin' | 'analyst' | 'viewer'>('viewer');
  const [magicLinkSent, setMagicLinkSent] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [time, setTime] = useState(new Date());

  // Live Data State
  const [chartData, setChartData] = useState(generateTimeSeries());
  const [barData, setBarData] = useState(generateBarData());
  const [hexStream, setHexStream] = useState('');

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    
    // Live Streaming Data (Sliding Window)
    const dataTimer = setInterval(() => {
      setChartData(prev => {
        const nextTime = (prev[prev.length - 1]?.time || 0) + 1;
        const newVal = 40 + Math.random() * 60;
        return [...prev.slice(1), { time: nextTime, value: newVal }];
      });
      setBarData(generateBarData());
    }, 1000);
    
    // Generate constant hex stream
    const hexTimer = setInterval(() => {
      const chars = '0123456789ABCDEF';
      let str = '';
      for(let i=0; i<32; i++) str += chars[Math.floor(Math.random()*chars.length)];
      setHexStream(str);
    }, 80);

    return () => {
      clearInterval(timer);
      clearInterval(dataTimer);
      clearInterval(hexTimer);
    };
  }, []);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const handleMagicLink = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await authClient.post('/magic-link', { email, role: selectedRole });
      setMagicLinkSent(true);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to send magic link');
    } finally {
      setIsLoading(false);
    }
  };

  const accentColor = selectedRole === 'admin' ? 'blue' : selectedRole === 'analyst' ? 'cyan' : 'emerald';
  const roleLabel = selectedRole === 'admin' ? 'Administrator' : selectedRole === 'analyst' ? 'Data Analyst' : 'Observer';

  return (
    <div className="min-h-screen w-full flex bg-dark-bg text-white overflow-hidden font-sans">
      {/* Sidebar Control Panel */}
      <div className="w-full max-w-md h-screen relative z-30 flex flex-col border-r border-white/5 bg-black/60 backdrop-blur-3xl shadow-2xl animate-in slide-in-from-left duration-700">
        {/* Sidebar Header */}
        <div className="p-8 pb-4 border-b border-white/5">
          <div className="flex items-center space-x-3 mb-6">
            <div className={`p-2 rounded-lg bg-${accentColor}-500/10 border border-${accentColor}-500/20 transition-all duration-500`}>
              <Activity className={`w-6 h-6 text-${accentColor}-500`} />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tighter uppercase italic">NexusStream</h1>
              <div className="flex items-center space-x-2 text-[10px] text-gray-400 font-mono">
                <span className="animate-pulse text-emerald-500">●</span>
                <span>AUTHENTICATION_GATEWAY_V4.2</span>
              </div>
            </div>
          </div>
          
          <div className="space-y-1">
            <h2 className="text-2xl font-semibold tracking-tight">Identity Verification</h2>
            <p className="text-gray-400 text-xs">Initialize secure session for <span className={`text-${accentColor}-400 font-bold uppercase tracking-widest`}>{roleLabel}</span>.</p>
          </div>
        </div>

        {/* Sidebar Content (Scrollable) */}
        <div className="flex-1 overflow-y-auto p-8 space-y-10 custom-scrollbar">
          {error && (
            <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center animate-shake">
              <Lock className="w-4 h-4 mr-3 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {magicLinkSent ? (
            <div className="space-y-6 animate-fade-in text-center py-10">
              <div className="p-8 rounded-2xl bg-emerald-500/5 border border-emerald-500/20">
                <Mail className="w-16 h-16 text-emerald-400 mx-auto mb-6 opacity-80" />
                <h3 className="text-xl font-medium mb-3">Transmission Sent</h3>
                <p className="text-gray-400 text-sm leading-relaxed">
                  A verification beacon has been dispatched to <br/>
                  <span className={`text-${accentColor}-400 font-mono block mt-2 text-base`}>{email}</span>
                </p>
              </div>
              <button 
                onClick={() => setMagicLinkSent(false)}
                className="w-full py-4 text-xs text-gray-500 hover:text-white transition-colors uppercase tracking-widest font-bold"
              >
                ← Return to entry point
              </button>
            </div>
          ) : (
            <form onSubmit={handleMagicLink} className="space-y-8">
              {/* Role Selection */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Authority Level</span>
                  <span className={`text-[9px] px-2 py-0.5 rounded-full bg-${accentColor}-500/10 text-${accentColor}-400 border border-${accentColor}-500/20 font-bold uppercase transition-all duration-500`}>
                    {selectedRole}
                  </span>
                </div>
                
                <div className="grid grid-cols-3 gap-2 p-1.5 bg-white/5 rounded-2xl border border-white/5 relative">
                  {/* Sliding Highlight */}
                  <div 
                    className="absolute inset-y-1.5 bg-white/10 border border-white/10 rounded-xl transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] z-0"
                    style={{ 
                      width: 'calc(33.33% - 4px)',
                      left: selectedRole === 'admin' ? '2px' : selectedRole === 'analyst' ? '33.33%' : '66.66%' 
                    }}
                  />
                  
                  {[
                    { id: 'admin', icon: Shield, label: 'Admin' },
                    { id: 'analyst', icon: HardHat, label: 'Data' },
                    { id: 'viewer', icon: Users, label: 'View' }
                  ].map((role) => (
                    <button
                      key={role.id}
                      type="button"
                      onClick={() => setSelectedRole(role.id as any)}
                      className={`relative z-10 py-3.5 flex flex-col items-center transition-all duration-200 rounded-xl cursor-pointer ${selectedRole === role.id ? 'text-white scale-105' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}
                    >
                      <role.icon className={`w-4 h-4 mb-1.5 transition-colors ${selectedRole === role.id ? `text-${accentColor}-400` : ''}`} />
                      <span className="text-[9px] font-black uppercase tracking-tighter">{role.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Email Input */}
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Personnel Email</label>
                <div className="relative group">
                  <div className={`absolute inset-0 bg-${accentColor}-500/5 rounded-xl blur-lg transition-opacity opacity-0 group-focus-within:opacity-100 pointer-events-none`} />
                  <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500 group-focus-within:text-white transition-colors" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-xl py-4.5 pl-12 pr-4 text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-white/10 focus:bg-white/[0.07] transition-all text-sm font-medium"
                    placeholder="name@nexusstream.com"
                    required
                  />
                </div>
              </div>

              {/* Submit Action */}
              <button
                type="submit"
                disabled={isLoading}
                className="w-full relative group overflow-hidden py-4.5 rounded-xl bg-white text-black font-black uppercase tracking-widest text-[10px] transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
              >
                {isLoading ? (
                  <span className="flex items-center justify-center">
                    <Cpu className="w-4 h-4 mr-2 animate-spin" />
                    Initializing...
                  </span>
                ) : (
                  'Establish Connection'
                )}
                <div className="absolute inset-0 h-full w-full bg-gradient-to-r from-transparent via-black/10 to-transparent -translate-x-full group-hover:animate-[shimmer_1.5s_infinite]" />
              </button>
            </form>
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="p-8 pt-6 border-t border-white/5 bg-black/20 flex flex-col space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-[9px] text-gray-500 font-bold uppercase tracking-widest">System Clock</span>
              <span className="text-base font-mono text-white/90 tracking-tighter">{time.toLocaleTimeString()}</span>
            </div>
            <div className="h-10 w-px bg-white/10" />
            <div className="flex flex-col items-end text-right">
              <span className="text-[9px] text-gray-500 font-bold uppercase tracking-widest">Security Protocol</span>
              <span className={`text-[10px] text-${accentColor}-500 font-bold uppercase tracking-tight flex items-center transition-colors duration-500`}>
                <Shield className="w-3 h-3 mr-1" />
                RS256_ACTIVE
              </span>
            </div>
          </div>
          
          <div className="flex items-center justify-center space-x-2 pb-2">
            <div className="w-1 h-1 rounded-full bg-gray-800" />
            <span className="text-[8px] text-gray-700 font-mono tracking-widest">{hexStream}</span>
            <div className="w-1 h-1 rounded-full bg-gray-800" />
          </div>
        </div>
      </div>

      {/* --- Holographic Backdrop Section --- */}
      <div className="flex-1 relative h-screen overflow-hidden hidden md:block select-none bg-black">
        <div 
          className="absolute inset-0 bg-cover bg-center transition-all duration-[20000ms] hover:scale-110 opacity-60"
          style={{ backgroundImage: 'url("/login-bg.png")' }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-dark-bg via-dark-bg/20 to-transparent z-10" />
        <div className="absolute inset-0 bg-gradient-to-t from-dark-bg/80 via-transparent to-dark-bg/40 z-10" />

        {/* Floating Widgets Area */}
        <div className="absolute inset-0 z-20 px-32 flex flex-col items-end justify-center pointer-events-none">
          
          {/* Top Left Indicator (on Backdrop) */}
          <div className="absolute top-12 left-12 animate-in fade-in slide-in-from-top-4 duration-1000">
            <div className="flex items-center space-x-4 bg-white/5 backdrop-blur-md border border-white/10 p-4 rounded-2xl">
              <div className="relative">
                <div className={`absolute inset-0 bg-${accentColor}-500 blur-md animate-pulse opacity-20`} />
                <Globe className={`w-8 h-8 text-${accentColor}-400 relative z-10`} />
              </div>
              <div>
                <div className="text-[10px] text-gray-500 font-bold uppercase tracking-widest font-mono">Backbone_Status</div>
                <div className="text-sm font-mono text-emerald-400">0.0.0.0 // LISTENING</div>
              </div>
            </div>
          </div>

          {/* Role Intelligence Panel - With Reveal Animation */}
          <div 
            key={selectedRole}
            className="w-[450px] space-y-6 animate-in fade-in slide-in-from-bottom-8 zoom-in-95 duration-700 ease-out"
          >
            
            {/* Intel Header */}
            <div className="flex items-center space-x-4 border-l-4 border-brand-500 pl-4 py-2">
              <div className="bg-brand-500/10 p-3 rounded-xl border border-brand-500/20">
                {selectedRole === 'admin' ? <Shield className="w-6 h-6 text-brand-400" /> : 
                 selectedRole === 'analyst' ? <Database className="w-6 h-6 text-cyan-400" /> : 
                 <Network className="w-6 h-6 text-emerald-400" />}
              </div>
              <div>
                <h4 className="text-xl font-bold tracking-tight">{roleLabel} Intelligence</h4>
                <p className="text-xs text-gray-400">Establishing high-fidelity operational link...</p>
              </div>
            </div>

            {/* Dynamic Chart Widget */}
            <div className="bg-black/40 backdrop-blur-2xl border border-white/5 rounded-3xl p-6 h-[420px] relative overflow-hidden group shadow-2xl">
              <div className="absolute top-0 left-0 w-full h-[2px] bg-brand-500/20 animate-scanline z-30 opacity-40" />
              
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center space-x-2">
                  <Zap className={`w-4 h-4 text-${accentColor}-400`} />
                  <span className="text-[10px] font-bold uppercase tracking-[0.2em]">{selectedRole === 'admin' ? 'Strategic Overview' : selectedRole === 'analyst' ? 'Ingestion Flow' : 'Node Connectivity'}</span>
                </div>
                <span className="text-[10px] text-gray-500 font-mono">LIVE_FEED</span>
              </div>

              <div className="h-48 w-full opacity-90 overflow-visible">
                {selectedRole === 'analyst' ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={accentColor === 'cyan' ? '#06b6d4' : '#10b981'} stopOpacity={0.3}/>
                          <stop offset="95%" stopColor={accentColor === 'cyan' ? '#06b6d4' : '#10b981'} stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <Area 
                        type="monotone" 
                        dataKey="value" 
                        stroke={accentColor === 'cyan' ? '#06b6d4' : '#10b981'} 
                        fillOpacity={1} 
                        fill="url(#colorValue)" 
                        strokeWidth={3} 
                        isAnimationActive={true}
                        animationDuration={1000}
                        animationEasing="linear"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : selectedRole === 'viewer' ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={barData}>
                      <Bar 
                        dataKey="val" 
                        fill="#10b981" 
                        radius={[4, 4, 0, 0]} 
                        isAnimationActive={true}
                        animationDuration={800}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full w-full flex flex-col space-y-8 py-4 animate-in fade-in zoom-in-95 duration-1000">
                    
                    {/* Database Shard Authority */}
                    <div className="space-y-4">
                      <div className="flex items-center justify-between px-1">
                        <span className="text-[9px] font-bold text-gray-500 uppercase tracking-[0.3em]">DB_Cluster_Authority</span>
                        <span className="text-[9px] text-blue-500 font-mono">L4_CLEARANCE</span>
                      </div>
                      <div className="flex items-end justify-between h-16 px-2 gap-3 pb-2 border-b border-white/5">
                        {[70, 95, 82, 90, 65, 88].map((h, i) => (
                          <div key={i} className="flex-1 flex flex-col items-center group h-full">
                            <div className="w-full bg-white/5 rounded-t-sm relative overflow-hidden h-full">
                              <div 
                                className="absolute bottom-0 left-0 w-full bg-blue-500/40 group-hover:bg-blue-400 transition-all duration-1000" 
                                style={{ height: `${h}%` }} 
                              />
                            </div>
                            <span className="text-[7px] text-gray-600 font-mono mt-1 uppercase">S_0{i+1}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Security Scanning Core */}
                    <div className="relative flex-1 flex flex-col items-center justify-center group">
                      <div className="absolute inset-0 bg-blue-500/5 blur-3xl rounded-full" />
                      <div className="relative p-10 border-2 border-white/5 rounded-full overflow-hidden bg-black/20">
                        {/* Scanning Beam (Vertical) */}
                        <div className="absolute top-0 left-0 w-full h-[1px] bg-blue-400 shadow-[0_0_15px_rgba(59,130,246,0.8)] animate-[scanlineVertical_3s_infinite_linear] z-20" />
                        <Shield className="w-14 h-14 text-blue-400 stroke-[1px] opacity-80" />
                      </div>
                      <div className="mt-4 text-center">
                        <div className="text-[10px] font-black tracking-[0.4em] text-blue-400/80 uppercase">Authority Vault</div>
                        <div className="text-[8px] font-mono text-gray-600 mt-1 uppercase leading-relaxed">
                          Encryption: AES_256_GCM_VERIFIED <br/>
                          Defense_Status: THREAT_LEVEL_ZERO
                        </div>
                      </div>
                    </div>

                    {/* Authorized Commands */}
                    <div className="pt-4 border-t border-white/5">
                      <div className="text-[9px] font-bold text-gray-500 uppercase tracking-[0.2em] mb-4 px-1">System Action Protocols</div>
                      <div className="grid grid-cols-2 gap-4">
                        {[
                          { icon: Database, label: 'Flush DB' },
                          { icon: Lock, label: 'Sync Mesh' },
                          { icon: Activity, label: 'Node Load' },
                          { icon: Terminal, label: 'Intercept' }
                        ].map((cmd, i) => (
                          <div key={i} className="flex items-center space-x-2 group/cmd cursor-default">
                            <div className="p-1.5 rounded-md bg-white/5 border border-white/5 group-hover/cmd:bg-blue-500/10 group-hover/cmd:border-blue-500/20 transition-all duration-300">
                              <cmd.icon className="w-3 h-3 text-gray-600 group-hover/cmd:text-blue-400 transition-colors" />
                            </div>
                            <span className="text-[8px] text-gray-500 font-bold uppercase tracking-widest group-hover/cmd:text-white transition-colors">{cmd.label}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-4 grid grid-cols-2 gap-4">
                 <div className="p-3 bg-white/5 rounded-xl border border-white/5 group-hover:bg-white/10 transition-colors">
                    <div className="text-[8px] text-gray-500 uppercase tracking-widest mb-1">Response Time</div>
                    <div className="text-xs font-mono text-white">42ms <span className="text-[10px] text-emerald-500">OPTIMAL</span></div>
                 </div>
                 <div className="p-3 bg-white/5 rounded-xl border border-white/5 group-hover:bg-white/10 transition-colors">
                    <div className="text-[8px] text-gray-500 uppercase tracking-widest mb-1">Queue Depth</div>
                    <div className="text-xs font-mono text-white">0.04% <span className="text-[10px] text-brand-400">NOMINAL</span></div>
                 </div>
              </div>
            </div>

            {/* Bottom Utility Widgets */}
            <div className="grid grid-cols-2 gap-4">
               <div className="bg-black/60 backdrop-blur-xl border border-white/5 p-4 rounded-2xl flex items-center space-x-3 hover:bg-black/80 transition-colors">
                  <div className={`p-2 rounded-lg bg-${accentColor}-500/10`}>
                    <Clock className={`w-4 h-4 text-${accentColor}-400`} />
                  </div>
                  <div>
                    <div className="text-[9px] text-gray-500 uppercase tracking-tighter">Session Expiry</div>
                    <div className="text-[10px] font-bold text-white">15:00m STANDBY</div>
                  </div>
               </div>
               <div className="bg-black/60 backdrop-blur-xl border border-white/5 p-4 rounded-2xl flex items-center space-x-3 hover:bg-black/80 transition-colors">
                  <div className="p-2 rounded-lg bg-white/5">
                    <Zap className="w-4 h-4 text-brand-400" />
                  </div>
                  <div>
                    <div className="text-[9px] text-gray-500 uppercase tracking-tighter">System Load</div>
                    <div className="text-[10px] font-bold text-white">LOW_LATENCY</div>
                  </div>
               </div>
            </div>

          </div>

          <div className="absolute bottom-12 right-12 z-0 opacity-10 leading-none select-none">
            <div className={`text-[160px] font-black tracking-tighter uppercase italic`}>{selectedRole}</div>
          </div>
        </div>

        <div className="absolute -bottom-32 -right-32 w-128 h-128 border border-white/5 rounded-full pointer-events-none z-10">
          <div className="absolute inset-0 border border-white/5 rounded-full animate-ping-slow" />
          <div className="absolute inset-16 border border-white/5 rounded-full animate-ping-slow" style={{ animationDelay: '2s' }} />
          <div className="absolute inset-32 border border-white/5 rounded-full animate-ping-slow" style={{ animationDelay: '4s' }} />
        </div>
      </div>
    </div>
  );
};
