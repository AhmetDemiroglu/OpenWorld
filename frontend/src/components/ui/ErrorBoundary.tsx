import { Component, ErrorInfo, ReactNode } from 'react';
import { OpenWorldLogo } from '../OpenWorldLogo';
import './ErrorBoundary.css';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
    this.setState({ error, errorInfo });
    
    // Could send to error tracking service here
    // reportError(error, errorInfo);
  }

  private handleReload = () => {
    window.location.reload();
  };

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  private handleGoHome = () => {
    window.location.href = '/';
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="error-boundary">
          <div className="error-content">
            <div className="error-logo">
              <OpenWorldLogo size={80} />
            </div>
            
            <h1 className="error-title">Bir Hata Oluştu</h1>
            <p className="error-description">
              Üzgünüz, beklenmeyen bir hata ile karşılaştık. 
              Lütfen sayfayı yenileyin veya ana sayfaya dönün.
            </p>

            {this.state.error && (
              <details className="error-details">
                <summary>Hata Detayları</summary>
                <pre className="error-stack">
                  {this.state.error.toString()}
                  {this.state.errorInfo?.componentStack}
                </pre>
              </details>
            )}

            <div className="error-actions">
              <button 
                className="error-btn error-btn-primary" 
                onClick={this.handleReload}
              >
                🔄 Sayfayı Yenile
              </button>
              <button 
                className="error-btn error-btn-secondary" 
                onClick={this.handleReset}
              >
                🔄 Sıfırla
              </button>
              <button 
                className="error-btn error-btn-secondary" 
                onClick={this.handleGoHome}
              >
                🏠 Ana Sayfa
              </button>
            </div>

            <div className="error-footer">
              <p>Sorun devam ederse lütfen destek ile iletişime geçin.</p>
              <a 
                href="https://github.com/AhmetDemiroglu/OpenWorld/issues" 
                target="_blank" 
                rel="noopener noreferrer"
                className="error-link"
              >
                GitHub'da Sorun Bildir →
              </a>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

// Hook for async error boundaries
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: ReactNode
) {
  return function WithErrorBoundary(props: P) {
    return (
      <ErrorBoundary fallback={fallback}>
        <Component {...props} />
      </ErrorBoundary>
    );
  };
}
