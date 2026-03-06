import { useEffect, useCallback } from 'react';
import { useStore } from '../store';
import type { ThemeMode } from '../types';

export function useTheme() {
  const { theme, setTheme } = useStore();

  // Detect system preference
  const getSystemTheme = useCallback((): 'light' | 'dark' => {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }, []);

  // Get effective theme (resolve 'system' to actual theme)
  const effectiveTheme = theme.mode === 'system' ? getSystemTheme() : theme.mode;

  // Apply theme to document
  useEffect(() => {
    const root = document.documentElement;
    
    // Remove existing theme classes
    root.classList.remove('light', 'dark');
    
    // Add current theme class
    root.classList.add(effectiveTheme);
    
    // Set color scheme
    root.style.colorScheme = effectiveTheme;
    
    // Apply CSS variables
    const colors = effectiveTheme === 'dark' ? darkColors : lightColors;
    Object.entries(colors).forEach(([key, value]) => {
      root.style.setProperty(`--color-${key}`, value);
    });
    
    // Apply font size
    root.style.setProperty('--font-size-base', fontSizeMap[theme.fontSize]);
  }, [effectiveTheme, theme.fontSize]);

  // Listen for system theme changes
  useEffect(() => {
    if (theme.mode !== 'system') return;
    
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      // Force re-render by setting theme again
      setTheme({ mode: 'system' });
    };
    
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, [theme.mode, setTheme]);

  const toggleTheme = useCallback(() => {
    const modes: ThemeMode[] = ['light', 'dark', 'system'];
    const currentIndex = modes.indexOf(theme.mode);
    const nextMode = modes[(currentIndex + 1) % modes.length];
    setTheme({ mode: nextMode });
  }, [theme.mode, setTheme]);

  const setMode = useCallback((mode: ThemeMode) => {
    setTheme({ mode });
  }, [setTheme]);

  return {
    theme,
    effectiveTheme,
    setTheme,
    toggleTheme,
    setMode,
    isDark: effectiveTheme === 'dark',
  };
}

const lightColors = {
  background: '#ffffff',
  surface: '#f8fafc',
  'surface-hover': '#f1f5f9',
  border: '#e2e8f0',
  text: '#0f172a',
  'text-muted': '#64748b',
  primary: '#3b82f6',
  'primary-hover': '#2563eb',
  secondary: '#64748b',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
};

const darkColors = {
  background: '#0f172a',
  surface: '#1e293b',
  'surface-hover': '#334155',
  border: '#334155',
  text: '#f8fafc',
  'text-muted': '#94a3b8',
  primary: '#60a5fa',
  'primary-hover': '#3b82f6',
  secondary: '#94a3b8',
  success: '#4ade80',
  warning: '#fbbf24',
  error: '#f87171',
};

const fontSizeMap = {
  small: '14px',
  medium: '16px',
  large: '18px',
};
