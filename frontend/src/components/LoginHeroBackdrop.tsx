import { useState } from 'react';

type Props = {
  onFallback?: () => void;
  onReady?: () => void;
};

/** Loads only the clean decorative asset; a missing asset stays neutral. */
export function LoginHeroBackdrop({ onFallback, onReady }: Props) {
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading');
  return (
    <div
      className={`login-hero-art login-hero-art-${state}`}
      aria-hidden="true"
      data-testid="login-hero-backdrop"
    >
      <img
        className="login-hero-art-image"
        src="/brand/login-hero-background.png"
        alt=""
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
