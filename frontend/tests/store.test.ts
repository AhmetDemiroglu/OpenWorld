import { describe, it, expect, beforeEach } from 'vitest';
import { useStore } from '../src/store';

// Reset store before each test
beforeEach(() => {
  useStore.setState({
    currentSessionId: 'web_main',
    messages: {},
    notifications: [],
  });
});

describe('Store', () => {
  describe('Session', () => {
    it('should set current session', () => {
      const store = useStore.getState();
      store.setCurrentSession('new_session');
      
      expect(useStore.getState().currentSessionId).toBe('new_session');
    });

    it('should add session', () => {
      const store = useStore.getState();
      const newSession = {
        id: 'test',
        name: 'Test Session',
        createdAt: new Date().toISOString(),
        lastMessageAt: new Date().toISOString(),
        messageCount: 0,
      };
      
      store.addSession(newSession);
      
      expect(useStore.getState().sessions).toContainEqual(newSession);
    });
  });

  describe('Messages', () => {
    it('should add message to session', () => {
      const store = useStore.getState();
      const message = {
        role: 'user' as const,
        content: 'Test',
        timestamp: '14:30',
      };
      
      store.addMessage('web_main', message);
      
      expect(useStore.getState().messages['web_main']).toContainEqual(message);
    });

    it('should clear messages', () => {
      const store = useStore.getState();
      store.addMessage('web_main', {
        role: 'user',
        content: 'Test',
        timestamp: '14:30',
      });
      
      store.clearMessages('web_main');
      
      expect(useStore.getState().messages['web_main']).toEqual([]);
    });
  });

  describe('Theme', () => {
    it('should set theme mode', () => {
      const store = useStore.getState();
      store.setTheme({ mode: 'dark' });
      
      expect(useStore.getState().theme.mode).toBe('dark');
    });

    it('should set font size', () => {
      const store = useStore.getState();
      store.setTheme({ fontSize: 'large' });
      
      expect(useStore.getState().theme.fontSize).toBe('large');
    });
  });

  describe('Notifications', () => {
    it('should add notification', () => {
      const store = useStore.getState();
      store.addNotification({
        type: 'info',
        title: 'Test',
        message: 'Test message',
      });
      
      expect(useStore.getState().notifications.length).toBe(1);
    });

    it('should remove notification', () => {
      const store = useStore.getState();
      store.addNotification({
        type: 'info',
        title: 'Test',
        message: 'Test message',
      });
      
      const notification = useStore.getState().notifications[0];
      store.removeNotification(notification.id);
      
      expect(useStore.getState().notifications.length).toBe(0);
    });
  });
});
