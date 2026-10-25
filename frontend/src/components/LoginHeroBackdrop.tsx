import { useEffect, useState } from 'react';

type Props = {
  onFallback?: () => void;
  onReady?: () => void;
};

/** Loads only the clean decorative asset; a missing asset stays neutral. */
export function LoginHeroBackdrop({ onFallback, onReady }: Props) {
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading');
  const [visible, setVisible] = useState(
    () => document.visibilityState === 'visible',
  );

  useEffect(() => {
    const updateVisibility = () =>
      setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', updateVisibility);
    return () =>
      document.removeEventListener('visibilitychange', updateVisibility);
  }, []);

  return (
    <div
      className={`login-hero-art login-hero-art-${state}${visible ? '' : ' login-hero-art-hidden'}`}
      aria-hidden="true"
      data-testid="login-hero-backdrop"
    >
      <img
        className="login-hero-art-image"
        src="/brand/login-hero-background.png"
        alt=""
        decoding="async"
        fetchPriority="high"
        onLoad={() => {
          setState('ready');
          onReady?.();
        }}
        onError={() => {
          setState('failed');
          onFallback?.();
        }}
      />
      <div className="login-hero-light-sweep" />
    </div>
  );
}
