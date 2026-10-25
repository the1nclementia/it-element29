export type LoginHeroCapability = {
  width: number;
  coarsePointer: boolean;
  reducedMotion: boolean;
  webgl: boolean;
};

export function shouldUseLoginHero({
  width,
  coarsePointer,
  reducedMotion,
  webgl,
}: LoginHeroCapability): boolean {
  return width >= 1280 && !coarsePointer && !reducedMotion && webgl;
}
