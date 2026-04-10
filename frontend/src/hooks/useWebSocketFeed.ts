import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuthStore } from '../store/useAuthStore';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8002/ws/dashboard';

export interface FeedMessage {
  event: string;
  device_id: string;
  device_type: string;
  status: string;
  is_anomaly: boolean;
  timestamp: string;
  // Analyst+
  raw_value?: number;
  moving_avg?: number;
  minimum?: number;
  maximum?: number;
  anomaly_source?: string;
  // Admin+
  packet_count?: number;
  location?: string;
}

export function useWebSocketFeed(maxBufferLimit: number = 50) {
  const { accessToken } = useAuthStore();
  const [isConnected, setIsConnected] = useState(false);
  
  // We use a React ref to buffer incoming messages without triggering re-renders for every single message.
  const bufferRef = useRef<FeedMessage[]>([]);
  // The state that the UI actually binds to, which is updated on an interval
  const [feed, setFeed] = useState<FeedMessage[]>([]);
  
  const wsRef = useRef<WebSocket | null>(null);
  const flushIntervalRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (!accessToken) return;
    
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(`${WS_URL}?token=${accessToken}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        console.log('Dashboard WS Connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event === 'ping') return;
          
          // Push to immediate un-rendered buffer
          bufferRef.current.unshift(data);
          
          // Truncate buffer if it grows too large
          if (bufferRef.current.length > maxBufferLimit * 2) {
            bufferRef.current = bufferRef.current.slice(0, maxBufferLimit * 2);
          }
        } catch (e) {
          /* malformed JSON */
        }
      };

      ws.onclose = (e) => {
        setIsConnected(false);
        console.log('Dashboard WS Disconnected', e.reason);
        // Automatic reconnect logic could go here
      };
      
      ws.onerror = () => {
        setIsConnected(false);
      };
    } catch (e) {
      setIsConnected(false);
    }
  }, [accessToken, maxBufferLimit]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  // Set up the flush interval to periodically sync the hidden buffer to the React state
  useEffect(() => {
    flushIntervalRef.current = window.setInterval(() => {
      // Only set state if the buffer actually changed
      if (bufferRef.current.length > 0) {
        setFeed(bufferRef.current.slice(0, maxBufferLimit));
      }
    }, 1000); // Flush buffer every 1 second (1 FPS for tables is readable)

    return () => {
      if (flushIntervalRef.current) clearInterval(flushIntervalRef.current);
    };
  }, [maxBufferLimit]);

  useEffect(() => {
    if (accessToken) connect();
    return () => disconnect();
  }, [accessToken, connect, disconnect]);

  return { isConnected, feed, connect, disconnect };
}
