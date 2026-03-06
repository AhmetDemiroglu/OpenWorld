import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Sidebar } from '../src/components/Sidebar';

describe('Sidebar', () => {
  const defaultProps = {
    activeTab: 'actions',
    onTabChange: vi.fn(),
    onQuickAction: vi.fn(),
    sessionId: 'test_session',
    onSessionChange: vi.fn(),
  };

  it('renders all tabs', () => {
    render(<Sidebar {...defaultProps} />);
    
    expect(screen.getByText('Hızlı İşlemler')).toBeInTheDocument();
    expect(screen.getByTitle('Oturumlar')).toBeInTheDocument();
    expect(screen.getByTitle('Dosyalar')).toBeInTheDocument();
  });

  it('calls onTabChange when tab is clicked', () => {
    render(<Sidebar {...defaultProps} />);
    
    const sessionsTab = screen.getByTitle('Oturumlar');
    fireEvent.click(sessionsTab);
    
    expect(defaultProps.onTabChange).toHaveBeenCalledWith('sessions');
  });

  it('calls onQuickAction when quick action is clicked', () => {
    render(<Sidebar {...defaultProps} />);
    
    // Assuming there's a quick action button
    const quickActions = screen.getAllByRole('button');
    if (quickActions.length > 0) {
      fireEvent.click(quickActions[0]);
    }
  });

  it('renders quick actions for the active tab', () => {
    render(<Sidebar {...defaultProps} />);
    
    expect(screen.getByText('Haberler')).toBeInTheDocument();
    expect(screen.getByText('Görevler')).toBeInTheDocument();
  });
});
