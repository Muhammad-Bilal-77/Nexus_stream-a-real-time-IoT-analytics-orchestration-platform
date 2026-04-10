import React, { useState } from 'react';
import { Activity, Lock, Mail, KeyRound, ScanFace } from 'lucide-react';
import { authClient } from '../api/client';
import { useAuthStore } from '../store/useAuthStore';
import { Navigate } from 'react-router-dom';

export const Login: React.FC = () => {
  const { isAuthenticated, login } = useAuthStore();
  
  // State for Magic Link
  const [email, setEmail] = useState('');
  const [magicLinkSent, setMagicLinkSent] = useState(false);
  
  // State for Legacy Login
  const [showDeveloperLogin, setShowDeveloperLogin] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const handleMagicLink = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await authClient.post('/magic-link', { email });
      setMagicLinkSent(true);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to send magic link');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLegacyLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const res = await authClient.post('/login', { username, password });
      login(res.data.access_token, res.data.refresh_token);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to authenticate');
    } finally {
      setIsLoading(false);
    }
  };

  const handleOAuth = (provider: 'google' | 'github') => {
    // Redirect entirely to backend OAuth initiation route
    window.location.href = `http://localhost:3002/auth/${provider}`;
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-dark-bg relative overflow-hidden">
      {/* Background aesthetics */}
      <div className="absolute top-1/4 left-1/4 w-[40vw] h-[40vw] bg-brand-600/20 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-[30vw] h-[30vw] bg-nexus-red/10 rounded-full blur-[100px] pointer-events-none" />

      {/* Login Card */}
      <div className="w-full max-w-md p-8 glass-card rounded-2xl z-10 mx-4 border border-white/10 glow-primary transition-all">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-brand-500/20 rounded-2xl flex items-center justify-center mb-4 border border-brand-500/30">
            <Activity className="w-8 h-8 text-brand-500" />
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">NexusStream</h1>
          <p className="text-gray-400 mt-2 text-center text-sm">Sign in to access your IoT telemetry workspace.</p>
        </div>

        {error && (
          <div className="p-3 mb-6 rounded-lg bg-red-500/10 border border-red-500/50 text-red-400 text-sm flex items-center animate-fade-in">
            <Lock className="w-4 h-4 mr-2" />
            {error}
          </div>
        )}

        {magicLinkSent ? (
          <div className="text-center bg-green-500/10 border border-green-500/30 p-6 rounded-xl animate-fade-in">
            <Mail className="w-10 h-10 text-green-400 mx-auto mb-3" />
            <h3 className="text-white font-medium text-lg mb-2">Check your inbox</h3>
            <p className="text-gray-400 text-sm mb-4">We've sent a magic login link to <strong>{email}</strong>.</p>
            <button 
              onClick={() => setMagicLinkSent(false)}
              className="text-brand-400 hover:text-brand-300 text-sm font-medium transition-colors"
            >
              Use a different email
            </button>
          </div>
        ) : !showDeveloperLogin ? (
          <>
            {/* Primary Magic Link Flow */}
            <form onSubmit={handleMagicLink} className="space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-300 ml-1">Email Address</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-xl py-2.5 pl-10 pr-4 text-white focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500 transition-all font-medium placeholder:text-gray-600"
                    placeholder="name@company.com"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 px-4 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded-xl transition-all shadow-[0_0_15px_rgba(37,99,235,0.4)] disabled:opacity-50 disabled:cursor-not-allowed group relative overflow-hidden"
              >
                <span className="relative z-10">{isLoading ? 'Sending...' : 'Continue with Email'}</span>
                <div className="absolute inset-0 h-full w-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:animate-[shimmer_1.5s_infinite]" />
              </button>
            </form>

            <div className="relative my-8">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/10"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-dark-bg/80 text-gray-500">Or continue with</span>
              </div>
            </div>

            {/* OAuth Buttons */}
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => handleOAuth('github')}
                className="flex items-center justify-center space-x-2 py-2.5 px-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-all text-gray-300 font-medium"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                <span>GitHub</span>
              </button>
              
              <button
                onClick={() => handleOAuth('google')}
                className="flex items-center justify-center space-x-2 py-2.5 px-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-all text-gray-300 font-medium"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
                <span>Google</span>
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleLegacyLogin} className="space-y-4 animate-fade-in">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-300 ml-1">Username (Developer)</label>
              <div className="relative">
                <ScanFace className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-xl py-2.5 pl-10 pr-4 text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500 transition-all font-medium"
                  placeholder="admin"
                  required
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-300 ml-1">Password</label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-xl py-2.5 pl-10 pr-4 text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500 transition-all font-medium"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 px-4 bg-cyan-600 hover:bg-cyan-500 focus:bg-cyan-500 text-white font-semibold rounded-xl transition-all disabled:opacity-50 mt-2"
            >
              {isLoading ? 'Authenticating...' : 'Developer Login'}
            </button>
          </form>
        )}

        <div className="mt-8 text-center">
          <button 
            type="button" 
            onClick={() => setShowDeveloperLogin(!showDeveloperLogin)}
            className="text-xs text-gray-600 hover:text-gray-400 transition-colors inline-block"
          >
            {showDeveloperLogin ? '← Back to secure login' : 'Developer Admin Login'}
          </button>
        </div>
      </div>
    </div>
  );
};
