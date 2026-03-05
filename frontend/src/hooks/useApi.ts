import { useState, useCallback } from 'react';
import { useToast } from './useToast';
import type { ChatRequest, ChatResponse, HealthStatus, SessionInfo, ToolStats } from '../types';

const API_BASE = '';

interface ApiError {
  message: string;
  status?: number;
}

export function useApi() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const { error: showError } = useToast();

  const request = useCallback(async <T,>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
        },
        ...options,
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw {
          message: errorText || `HTTP ${response.status}`,
          status: response.status,
        };
      }
      
      return await response.json() as T;
    } catch (err) {
      const apiError: ApiError = {
        message: err instanceof Error  err.message : 'Unknown error',
        status: (err as ApiError)?.status,
      };
      setError(apiError);
      showError('API Hatası', apiError.message);
      throw apiError;
    } finally {
      setLoading(false);
    }
  }, [showError]);

  const chat = useCallback(async (data: ChatRequest): Promise<ChatResponse> => {
    return request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }, [request]);

  const getSessions = useCallback(async (): Promise<SessionInfo[]> => {
    const response = await request<{ sessions: SessionInfo[] }>('/sessions');
    return response.sessions;
  }, [request]);

  const getHealth = useCallback(async (): Promise<HealthStatus> => {
    return request<HealthStatus>('/health');
  }, [request]);

  const getToolStats = useCallback(async (): Promise<ToolStats> => {
    return request<ToolStats>('/tools/audit?run_probes=false');
  }, [request]);

  const getMetrics = useCallback(async (): Promise<string> => {
    const response = await fetch(`${API_BASE}/metrics`);
    return response.text();
  }, []);

  return {
    loading,
    error,
    chat,
    getSessions,
    getHealth,
    getToolStats,
    getMetrics,
  };
}
