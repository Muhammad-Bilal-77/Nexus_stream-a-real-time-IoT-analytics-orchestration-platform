import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { jwtDecode } from 'jwt-decode';

export type Role = 'viewer' | 'analyst' | 'admin';

interface TokenPayload {
  sub: string;
  username: string;
  roles: string[];
  exp: number;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: {
    username: string;
    effectiveRole: Role;
  } | null;
  isAuthenticated: boolean;
  
  // Actions
  login: (access: string, refresh: string) => void;
  logout: () => void;
  setAccessToken: (access: string) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      login: (access: string, refresh: string) => {
        try {
          const decoded = jwtDecode<TokenPayload>(access);
          const rawRoles = decoded.roles.map(r => r.toLowerCase());
          
          let effectiveRole: Role = 'viewer';
          if (rawRoles.includes('admin')) effectiveRole = 'admin';
          else if (rawRoles.includes('analyst')) effectiveRole = 'analyst';

          set({
            accessToken: access,
            refreshToken: refresh,
            user: { username: decoded.username, effectiveRole },
            isAuthenticated: true,
          });
        } catch (error) {
          console.error("Failed to decode token on login", error);
        }
      },

      logout: async () => {
        const { accessToken } = useAuthStore.getState();
        if (accessToken) {
          try {
            await fetch('http://localhost:3002/auth/logout', {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${accessToken}`
              }
            });
          } catch (error) {
            console.warn("Backend logout failed, clearing local state anyway", error);
          }
        }
        
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        });
      },

      setAccessToken: (access: string) => set({ accessToken: access }),
    }),
    {
      name: 'nexusstream-auth',
    }
  )
);
