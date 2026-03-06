import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChatMessage, MediaPreview } from '../src/components/ChatMessage';

describe('ChatMessage', () => {
  it('renders user message correctly', () => {
    render(
      <ChatMessage
        role="user"
        content="Merhaba!"
        timestamp="14:30"
      />
    );
    
    expect(screen.getByText('Sen')).toBeInTheDocument();
    expect(screen.getByText('Merhaba!')).toBeInTheDocument();
    expect(screen.getByText('14:30')).toBeInTheDocument();
  });

  it('renders assistant message with markdown', () => {
    render(
      <ChatMessage
        role="assistant"
        content="**Kalın** metin"
        timestamp="14:31"
        toolsUsed={['search_news']}
      />
    );
    
    expect(screen.getByText('OpenWorld')).toBeInTheDocument();
    expect(document.querySelector('strong')).toHaveTextContent('Kalın');
  });

  it('displays tool badges', () => {
    render(
      <ChatMessage
        role="assistant"
        content="Sonuç"
        toolsUsed={['screenshot_desktop', 'search_news']}
      />
    );
    
    const badges = screen.getAllByText(/Haber Arama|screenshot_desktop/);
    expect(badges.length).toBe(2);
  });

  it('renders media attachments', () => {
    const media = [
      { type: 'image', url: '/test.png', filename: 'test.png' }
    ];
    
    const { container } = render(<MediaPreview media={media} />);
    
    expect(container.querySelector('img')).toBeInTheDocument();
  });
});
