/**
 * TypeScript type definitions for OpenWorld Frontend
 */

// API Types
export interface ChatRequest {
  session_id: string;
  message: string;
  source: 'web' | 'telegram';
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  steps: number;
  used_tools: string[];
  media: MediaAttachment[];
}

export interface MediaAttachment {
  type: 'image' | 'audio' | 'video' | 'document';
  url: string;
  filename: string;
  caption: string;
}

export interface SessionInfo {
  session_id: string;
  message_count: number;
  first_message: string;
  last_message: string;
}

export interface HealthStatus {
  ok: boolean;
  llm_backend: string;
  model: string;
  llama_model_path: string;
  workspace: string;
  shell_tool: boolean;
}

export interface ToolStats {
  period_days: number;
  tools: {
    name: string;
    count: number;
    success_rate: number;
    avg_duration_ms: number;
  }[];
}

// UI Types
export interface ToastMessage {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  duration?: number;
}

export interface KeyboardShortcut {
  action: string;
  key: string;
  description: string;
  global?: boolean;
}

// Component Props
export interface ChatMessageProps {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
  toolsUsed?: string[];
  media?: MediaAttachment[];
}

export interface SidebarProps {
  activeTab: 'actions' | 'sessions' | 'settings';
  onTabChange: (tab: 'actions' | 'sessions' | 'settings') => void;
  onQuickAction: (message: string) => void;
  sessionId: string;
  onSessionChange: (sessionId: string) => void;
}

// Theme Types
export type ThemeMode = 'light' | 'dark' | 'system';

export interface ThemeConfig {
  mode: ThemeMode;
  colors: {
    primary: string;
    secondary: string;
    background: string;
    surface: string;
    text: string;
    textMuted: string;
    border: string;
    success: string;
    warning: string;
    error: string;
  };
  fontSize: 'small' | 'medium' | 'large';
}

// Tool Types
export interface ToolDefinition {
  name: string;
  description: string;
  category: string;
  parameters: ToolParameter[];
}

export interface ToolParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
}

// Error Types
export interface ApiError {
  error: boolean;
  error_code: string;
  message: string;
  details?: Record<string, unknown>;
}

// User Preferences
export interface UserPreferences {
  theme: ThemeMode;
  language: string;
  notifications: boolean;
  soundEnabled: boolean;
  autoSave: boolean;
}
