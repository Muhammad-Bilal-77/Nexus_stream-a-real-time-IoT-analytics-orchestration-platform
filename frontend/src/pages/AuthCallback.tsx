import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/useAuthStore';
import { authClient } from '../api/client';
import { Loader } from 'lucide-react';

export const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuthStore();
  const [error, setError] = useState('');

  useEffect(() => {
    const processCallback = async () => {
      // Parse parameters from query string
      const searchParams = new URLSearchParams(location.search);
      const token = searchParams.get('token');
      const accessToken = searchParams.get('access_token');
      const refreshToken = searchParams.get('refresh_token');
      
      try {
        if (accessToken && refreshToken) {
          // OAuth callback case: Tokens already provided in URL
          login(accessToken, refreshToken);
          navigate('/', { replace: true });
        } else if (token) {
          // Magic link case: Token provided to exchange
          const res = await authClient.post('/magic-link/verify', { token });
          login(res.data.access_token, res.data.refresh_token);
          navigate('/', { replace: true });
        } else {
          // Invalid call
          setError('Invalid authentication request. No token provided.');
        }
      } catch (err: any) {
        setError(err.response?.data?.error || 'Authentication failed. Link may be expired.');
      }
    };

    processCallback();
  }, [location, login, navigate]);

  if (error) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-dark-bg p-4">
        <div className="glass-card p-6 rounded-2xl max-w-sm w-full text-center border border-red-500/30">
          <div className="w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Authentication Error</h2>
          <p className="text-gray-400 mb-6">{error}</p>
          <button 
            onClick={() => navigate('/login')}
            className="px-4 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-white transition-colors"
          >
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-center bg-dark-bg">
      <Loader className="w-8 h-8 text-brand-500 animate-spin mb-4" />
      <p className="text-gray-400 font-medium animate-pulse">Authenticating securely...</p>
    </div>
  );
};
