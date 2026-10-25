import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { LoginHeroBackdrop } from '../components/LoginHeroBackdrop';

describe('login hero backdrop', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads only the clean decorative asset and exposes no form content', () => {
    const { container } = render(<LoginHeroBackdrop />);
    const image = container.querySelector('img')!;
    expect(image).toHaveAttribute('src', '/brand/login-hero-background.png');
    expect(screen.queryByText(/войти|логин|пароль/i)).not.toBeInTheDocument();
  });

  it('keeps a neutral fallback when the clean asset is unavailable', () => {
    const onFallback = vi.fn();
    const { container } = render(<LoginHeroBackdrop onFallback={onFallback} />);
    container.querySelector('img')!.dispatchEvent(new Event('error'));
    expect(onFallback).toHaveBeenCalledOnce();
  });

  it('pauses the light sweep while the document is hidden', async () => {
    const { container } = render(<LoginHeroBackdrop />);
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    document.dispatchEvent(new Event('visibilitychange'));
    await waitFor(() => {
      expect(container.firstElementChild).toHaveClass('login-hero-art-hidden');
    });
  });
});
