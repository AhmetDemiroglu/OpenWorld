import { useEffect, useState } from 'react';
import { OpenWorldLogo } from '../OpenWorldLogo';
import './SplashScreen.css';

interface SplashScreenProps {
  onComplete?: () => void;
  minimumDisplayTime?: number;
}

export function SplashScreen({ 
  onComplete, 
  minimumDisplayTime = 2000 
}: SplashScreenProps) {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('Başlatılıyor...');
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    const startTime = Date.now();
    
    const steps = [
      { progress: 10, status: 'Yapılandırma yükleniyor...' },
      { progress: 30, status: 'Veritabanı bağlanıyor...' },
      { progress: 50, status: 'Araçlar yükleniyor...' },
      { progress: 70, status: 'LLM servisi hazırlanıyor...' },
      { progress: 90, status: 'Arayüz başlatılıyor...' },
      { progress: 100, status: 'Hazır!' },
    ];

    let currentStep = 0;
    
    const interval = setInterval(() => {
      if (currentStep < steps.length) {
        const step = steps[currentStep];
        setProgress(step.progress);
        setStatus(step.status);
        currentStep++;
      } else {
        clearInterval(interval);
        
        // Ensure minimum display time
        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, minimumDisplayTime - elapsed);
        
        setTimeout(() => {
          setIsExiting(true);
          setTimeout(() => {
            onComplete?.();
          }, 500); // Exit animation time
        }, remaining);
      }
    }, minimumDisplayTime / steps.length);

    return () => clearInterval(interval);
  }, [minimumDisplayTime, onComplete]);

  return (
    <div className={`splash-screen ${isExiting ? 'splash-exit' : ''}`}>
      <div className="splash-content">
        <div className="splash-logo">
          <OpenWorldLogo size={120} />
        </div>
        
        <h1 className="splash-title">OpenWorld</h1>
        <p className="splash-subtitle">Yerel Yapay Zeka Asistanı</p>
        
        <div className="splash-progress-container">
          <div 
            className="splash-progress-bar" 
            style={{ width: `${progress}%` }}
          />
        </div>
        
        <p className="splash-status">{status}</p>
        
        <div className="splash-version">v0.1.0</div>
      </div>
    </div>
  );
}
