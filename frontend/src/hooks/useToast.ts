import { useCallback } from 'react';
import { useStore, type Notification } from '../store';

export function useToast() {
  const { addNotification, removeNotification } = useStore();

  const toast = useCallback((
    type: Notification['type'],
    title: string,
    message: string,
    duration: number = 5000
  ) => {
    addNotification({ type, title, message, duration });
  }, [addNotification]);

  const success = useCallback((
    title: string,
    message: string,
    duration?: number
  ) => {
    toast('success', title, message, duration);
  }, [toast]);

  const error = useCallback((
    title: string,
    message: string,
    duration?: number
  ) => {
    toast('error', title, message, duration);
  }, [toast]);

  const warning = useCallback((
    title: string,
    message: string,
    duration?: number
  ) => {
    toast('warning', title, message, duration);
  }, [toast]);

  const info = useCallback((
    title: string,
    message: string,
    duration?: number
  ) => {
    toast('info', title, message, duration);
  }, [toast]);

  const dismiss = useCallback((id: string) => {
    removeNotification(id);
  }, [removeNotification]);

  return {
    toast,
    success,
    error,
    warning,
    info,
    dismiss,
  };
}
