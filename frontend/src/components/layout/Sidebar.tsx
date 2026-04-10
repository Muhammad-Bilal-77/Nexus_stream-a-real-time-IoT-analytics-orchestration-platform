import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Server, Settings, Activity } from 'lucide-react';
import { useAuthStore } from '../../store/useAuthStore';

export const Sidebar: React.FC = () => {
  const { user } = useAuthStore();
  
  const navItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard', access: ['viewer', 'analyst', 'admin'] },
    { to: '/devices', icon: Server, label: 'Device Registry', access: ['viewer', 'analyst', 'admin'] },
    { to: '/admin', icon: Settings, label: 'Administration', access: ['admin'] },
  ];

  return (
    <aside className="w-64 glass border-r border-dark-border flex flex-col z-20">
      <div className="h-16 flex items-center px-6 border-b border-white/5">
        <Activity className="w-6 h-6 text-brand-500 mr-3" />
        <span className="font-bold text-lg tracking-tight">NexusStream</span>
      </div>
      
      <div className="flex-1 py-6 px-4 space-y-1">
        {navItems.map((item) => {
          if (!user || !item.access.includes(user.effectiveRole)) return null;
          
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => 
                `flex items-center px-3 py-2.5 rounded-lg transition-all duration-200 group ${
                  isActive 
                    ? 'bg-brand-500/10 text-brand-500 font-medium' 
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }`
              }
            >
              <item.icon className="w-5 h-5 mr-3 opacity-70 group-hover:opacity-100 transition-opacity" />
              {item.label}
            </NavLink>
          );
        })}
      </div>
      
      <div className="p-4 border-t border-white/5">
        <div className="glass-card rounded-lg p-3 flex flex-col">
          <span className="text-xs text-gray-500 uppercase tracking-wider mb-1">Current User</span>
          <span className="font-medium truncate">{user?.username}</span>
          <div className="flex mt-2">
            <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
              user?.effectiveRole === 'admin' ? 'border-brand-500 text-brand-500 bg-brand-500/10' :
              user?.effectiveRole === 'analyst' ? 'border-purple-500 text-purple-400 bg-purple-500/10' :
              'border-gray-500 text-gray-400 bg-gray-500/10'
            }`}>
              {user?.effectiveRole}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
};
