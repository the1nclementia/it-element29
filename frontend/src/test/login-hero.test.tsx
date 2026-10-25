import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoginHeroBackdrop } from '../components/LoginHeroBackdrop';

describe('login hero backdrop', () => {
  it('loads only the clean decorative asset and exposes no form content', () => {
    const { container } = render(<LoginHeroBackdrop />);
    const image = container.querySelector('img')!;
    expect(image).toHaveAttribute('src', '/brand/login-hero-background.webp');
    expect(screen.queryByText(/войти|логин|пароль/i)).not.toBeInTheDocument();
  });

  it('keeps a neutral fallback when the clean asset is unavailable', () => {
    const onFallback = vi.fn();
    const { container } = render(<LoginHeroBackdrop onFallback={onFallback} />);
    container.querySelector('img')!.dispatchEvent(new Event('error'));
    expect(onFallback).toHaveBeenCalledOnce();
  });
});
