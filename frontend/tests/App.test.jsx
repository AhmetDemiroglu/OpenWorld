import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from '../src/App';

// Mock fetch
global.fetch = vi.fn();

describe('App', () => {
  beforeEach(() => {
    fetch.mockClear();
  });

  it('renders welcome screen initially', () => {
    render(<App />);
    
    expect(screen.getAllByText('OpenWorld').length).toBeGreaterThan(0);
    expect(screen.getByText(/Yerel otonom asistanınız/)).toBeInTheDocument();
  });

  it('renders chat input', () => {
    render(<App />);
    
    expect(screen.getByPlaceholderText('Mesajınızı yazın...')).toBeInTheDocument();
  });

  it('sends message on button click', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'web_main',
        reply: 'Merhaba!',
        steps: 1,
        used_tools: [],
        media: [],
      }),
    });

    render(<App />);
    
    const input = screen.getByPlaceholderText('Mesajınızı yazın...');
    const sendButton = screen.getByLabelText('Gonder');
    
    fireEvent.change(input, { target: { value: 'Merhaba' } });
    fireEvent.click(sendButton);
    
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith('/chat', expect.any(Object));
    });
  });

  it('sends message on Enter key', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'web_main',
        reply: 'Merhaba!',
        steps: 1,
        used_tools: [],
        media: [],
      }),
    });

    render(<App />);
    
    const input = screen.getByPlaceholderText('Mesajınızı yazın...');
    
    fireEvent.change(input, { target: { value: 'Merhaba' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    
    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
  });

  it('toggles sidebar', () => {
    render(<App />);
    
    const toggleButton = screen.getByTitle('Paneli Kapat');
    fireEvent.click(toggleButton);
    
    expect(screen.getByTitle('Paneli Aç')).toBeInTheDocument();
  });
});
