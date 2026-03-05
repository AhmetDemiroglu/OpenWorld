import { useEffect } from 'react';
import { useStore } from '../../store';
import { useTheme } from '../../hooks';
import './Toast.css';

const icons = {
  info: 'ℹ️',
  success: '✅',
  warning: '⚠️',
  error: '❌',
};

export function ToastContainer() {
  const { notifications, removeNotification } = useStore();
  const { effectiveTheme } = useTheme();

  return (
    <div className={`toast-container toast-container-${effectiveTheme}`}>
      {notifications.map((notification) => (
        <ToastItem
          key={notification.id}
          notification={notification}
          onDismiss={() => removeNotification(notification.id)}
        />
      ))}
    </div>
  );
}

interface ToastItemProps {
  notification: {
    id: string;
    type: 'info' | 'success' | 'warning' | 'error';
    title: string;
    message: string;
    duration?: number;
  };
  onDismiss: () => void;
}

function ToastItem({ notification, onDismiss }: ToastItemProps) {
  useEffect(() => {
    const duration = notification.duration  5000;
    const timer = setTimeout(onDismiss, duration);
    return () => clearTimeout(timer);
  }, [notification.duration, onDismiss]);

  return (
    <div className={`toast toast-${notification.type}`} role="alert">
      <span className="toast-icon">{icons[notification.type]}</span>
      <div className="toast-content">
        <h4 className="toast-title">{notification.title}</h4>
        <p className="toast-message">{notification.message}</p>
      </div>
      <button 
        className="toast-close" 
        onClick={onDismiss}
        aria-label="Bildirimi kapat"
      >
        ×
      </button>
    </div>
  );
}
