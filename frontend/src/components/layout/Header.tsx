import React from 'react';
import { useAuthStore } from '../../store/useAuthStore';
import { LogOut, Bell } from 'lucide-react';

export const Header: React.FC = () => {
  const { logout } = useAuthStore();

  return (
    <header className="h-16 glass z-20 flex items-center justify-between px-6 border-b border-dark-border">
      <div className="flex items-center">
        {/* Breadcrumb spacing / Mobile menu toggle could go here */}
      </div>
      
      <div className="flex items-center space-x-4">
        <button className="p-2 text-gray-400 hover:text-white transition-colors relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-nexus-red rounded-full"></span>
        </button>
        <div className="h-6 w-px bg-white/10 mx-2"></div>
        <button 
          onClick={logout}
          className="flex items-center text-sm font-medium text-gray-400 hover:text-white transition-colors"
        >
          <LogOut className="w-4 h-4 mr-2" />
          Sign Out
        </button>
      </div>
    </header>
  );
};
