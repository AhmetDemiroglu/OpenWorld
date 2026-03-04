import { useEffect, useCallback, useRef } from 'react';
import { useStore } from '../store';

interface ShortcutConfig {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean;
  handler: () => void | Promise<void>;
  preventDefault?: boolean;
  target?: 'document' | 'input';
}

export function useKeyboard(shortcuts: ShortcutConfig[]) {
  const shortcutsRef = useRef(shortcuts);
  shortcutsRef.current = shortcuts;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      for (const shortcut of shortcutsRef.current) {
        if (matchesShortcut(event, shortcut)) {
          if (shortcut.preventDefault !== false) {
            event.preventDefault();
          }
          
          // Don't trigger if typing in input (unless target is 'input')
          const target = event.target as HTMLElement;
          const isInput = target.tagName === 'INPUT' || 
                         target.tagName === 'TEXTAREA' || 
                         target.isContentEditable;
          
          if (shortcut.target === 'input' && !isInput) continue;
          if (shortcut.target !== 'input' && isInput) continue;
          
          shortcut.handler();
          break;
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);
}

function matchesShortcut(event: KeyboardEvent, shortcut: ShortcutConfig): boolean {
  const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase() ||
                   event.code.toLowerCase() === shortcut.key.toLowerCase();
  
  return (
    keyMatch &&
    !!event.ctrlKey === !!shortcut.ctrl &&
    !!event.shiftKey === !!shortcut.shift &&
    !!event.altKey === !!shortcut.alt &&
    !!event.metaKey === !!shortcut.meta
  );
}

// Predefined shortcuts hook
export function useAppShortcuts({
  onNewChat,
  onToggleSidebar,
  onSearch,
  onSettings,
  onSendMessage,
}: {
  onNewChat?: () => void;
  onToggleSidebar?: () => void;
  onSearch?: () => void;
  onSettings?: () => void;
  onSendMessage?: () => void;
}) {
  const { setSidebarOpen, sidebarOpen } = useStore();

  const shortcutConfigs: ShortcutConfig[] = [
    {
      key: 'n',
      ctrl: true,
      handler: () => onNewChat?.(),
      description: 'Yeni sohbet başlat',
    },
    {
      key: 'b',
      ctrl: true,
      handler: () => {
        setSidebarOpen(!sidebarOpen);
        onToggleSidebar?.();
      },
      description: 'Kenar çubuğunu aç/kapat',
    },
    {
      key: 'k',
      ctrl: true,
      handler: () => onSearch?.(),
      description: 'Ara',
    },
    {
      key: ',',
      ctrl: true,
      handler: () => onSettings?.(),
      description: 'Ayarları aç',
    },
    {
      key: 'Enter',
      handler: () => onSendMessage?.(),
      target: 'input',
      description: 'Mesaj gönder',
    },
    {
      key: 'Escape',
      handler: () => {
        // Close modals, panels, etc.
        document.dispatchEvent(new CustomEvent('closeModal'));
      },
      description: 'Kapat',
    },
  ].filter(Boolean) as ShortcutConfig[];

  useKeyboard(shortcutConfigs);

  return { shortcuts: shortcutConfigs };
}

// Hook for input shortcuts
export function useInputShortcuts(
  _textareaRef: React.RefObject<HTMLTextAreaElement>,
  {
    onSubmit,
    onNewline,
  }: {
    onSubmit: () => void;
    onNewline?: () => void;
  }
) {
  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    // Submit on Enter (without Shift)
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
      return;
    }
    
    // Newline on Shift+Enter
    if (event.key === 'Enter' && event.shiftKey) {
      onNewline?.();
      return;
    }
    
    // History navigation with Arrow keys (when at start/end)
    if (event.key === 'ArrowUp' && !event.shiftKey) {
      const target = event.target as HTMLTextAreaElement;
      const isAtStart = target.selectionStart === 0 && target.selectionEnd === 0;
      if (isAtStart) {
        // Could trigger history navigation
        document.dispatchEvent(new CustomEvent('navigateHistory', { detail: 'up' }));
      }
    }
    
    if (event.key === 'ArrowDown' && !event.shiftKey) {
      const target = event.target as HTMLTextAreaElement;
      const isAtEnd = target.selectionStart === target.value.length;
      if (isAtEnd) {
        document.dispatchEvent(new CustomEvent('navigateHistory', { detail: 'down' }));
      }
    }
  }, [onSubmit, onNewline]);

  return { handleKeyDown };
}
