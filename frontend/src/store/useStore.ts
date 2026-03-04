import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  toolsUsed?: string[];
  media?: MediaAttachment[];
}

export interface MediaAttachment {
  type: 'image' | 'audio' | 'video' | 'document';
  url: string;
  filename: string;
  caption?: string;
}

export interface Theme {
  mode: 'light' | 'dark' | 'system';
  primaryColor: string;
  fontSize: 'small' | 'medium' | 'large';
}

export interface Session {
  id: string;
  name: string;
  createdAt: string;
  lastMessageAt: string;
  messageCount: number;
}

interface AppState {
  // Session
  currentSessionId: string;
  sessions: Session[];
  setCurrentSession: (sessionId: string) => void;
  addSession: (session: Session) => void;
  removeSession: (sessionId: string) => void;
  
  // Messages
  messages: Record<string, Message[]>;
  addMessage: (sessionId: string, message: Message) => void;
  clearMessages: (sessionId: string) => void;
  
  // UI State
  sidebarOpen: boolean;
  sidebarTab: 'actions' | 'sessions' | 'settings';
  setSidebarOpen: (open: boolean) => void;
  setSidebarTab: (tab: 'actions' | 'sessions' | 'settings') => void;
  
  // Theme
  theme: Theme;
  setTheme: (theme: Partial<Theme>) => void;
  
  // Loading
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  
  // Notifications
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  
  // Shortcuts
  shortcuts: Record<string, string>;
  setShortcut: (action: string, key: string) => void;
}

export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  duration?: number;
}

export const useStore = create<AppState>()(
  persist(
    (set, _get) => ({
      // Session
      currentSessionId: 'web_main',
      sessions: [],
      setCurrentSession: (sessionId) => set({ currentSessionId: sessionId }),
      addSession: (session) => set((state) => ({
        sessions: [session, ...state.sessions]
      })),
      removeSession: (sessionId) => set((state) => ({
        sessions: state.sessions.filter(s => s.id !== sessionId),
        messages: Object.fromEntries(
          Object.entries(state.messages).filter(([key]) => key !== sessionId)
        )
      })),
      
      // Messages
      messages: {},
      addMessage: (sessionId, message) => set((state) => ({
        messages: {
          ...state.messages,
          [sessionId]: [...(state.messages[sessionId] || []), message]
        }
      })),
      clearMessages: (sessionId) => set((state) => ({
        messages: {
          ...state.messages,
          [sessionId]: []
        }
      })),
      
      // UI State
      sidebarOpen: true,
      sidebarTab: 'actions',
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setSidebarTab: (tab) => set({ sidebarTab: tab }),
      
      // Theme
      theme: {
        mode: 'system',
        primaryColor: '#3b82f6',
        fontSize: 'medium'
      },
      setTheme: (theme) => set((state) => ({
        theme: { ...state.theme, ...theme }
      })),
      
      // Loading
      isLoading: false,
      setIsLoading: (loading) => set({ isLoading: loading }),
      
      // Notifications
      notifications: [],
      addNotification: (notification) => set((state) => ({
        notifications: [
          ...state.notifications,
          { ...notification, id: Math.random().toString(36).substring(7) }
        ]
      })),
      removeNotification: (id) => set((state) => ({
        notifications: state.notifications.filter(n => n.id !== id)
      })),
      
      // Shortcuts
      shortcuts: {
        newChat: 'ctrl+n',
        sendMessage: 'enter',
        toggleSidebar: 'ctrl+b',
        search: 'ctrl+k',
        settings: 'ctrl+,',
      },
      setShortcut: (action, key) => set((state) => ({
        shortcuts: { ...state.shortcuts, [action]: key }
      })),
    }),
    {
      name: 'openworld-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        theme: state.theme,
        shortcuts: state.shortcuts,
        currentSessionId: state.currentSessionId,
        sessions: state.sessions,
      }),
    }
  )
);

// Selectors
export const selectCurrentMessages = (state: AppState) => 
  state.messages[state.currentSessionId] || [];

export const selectSessionById = (sessionId: string) => (state: AppState) =>
  state.sessions.find(s => s.id === sessionId);
