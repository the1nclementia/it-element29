import { Canvas } from '@react-three/fiber';
import { useEffect, useRef } from 'react';

type Props = { onFallback: () => void; onReady: () => void };

function StaticComposition() {
  const seam = {
    color: '#ff6f1c',
    emissive: '#ff5a0a',
    emissiveIntensity: 0.72,
  };
  return (
    <>
      <color attach="background" args={['#f4eeea']} />
      <ambientLight intensity={2.1} color="#fffaf6" />
      <directionalLight position={[-4, 6, 5]} intensity={2.2} color="#fff8f2" />
      <pointLight
        position={[1.8, -1, 2.2]}
        intensity={5}
        distance={7}
        color="#ff7a2f"
      />
      <mesh position={[-0.45, 1.25, -1.8]} rotation={[0, 0, -0.16]}>
        <boxGeometry args={[8.2, 1.35, 0.42]} />
        <meshStandardMaterial
          color="#eee9e5"
          metalness={0.42}
          roughness={0.42}
        />
      </mesh>
      <mesh position={[-0.1, -1.5, -1.1]} rotation={[0.02, -0.16, -0.16]}>
        <boxGeometry args={[8.6, 1.95, 1.0]} />
        <meshStandardMaterial
          color="#e9e4e0"
          metalness={0.55}
          roughness={0.36}
        />
      </mesh>
      <mesh position={[0.2, -0.05, -0.25]} rotation={[-0.04, -0.2, -0.06]}>
        <boxGeometry args={[4.5, 1.95, 1.45]} />
        <meshStandardMaterial
          color="#f7f4f1"
          metalness={0.48}
          roughness={0.34}
        />
      </mesh>
      <mesh position={[-2.75, -0.15, -0.2]} rotation={[0, -0.2, -0.06]}>
        <boxGeometry args={[4.5, 2.7, 0.5]} />
        <meshStandardMaterial
          color="#ede8e4"
          metalness={0.42}
          roughness={0.42}
        />
      </mesh>
      <mesh position={[-0.15, -1.45, 0.02]} rotation={[0, 0, -0.12]}>
        <boxGeometry args={[7.5, 0.026, 0.026]} />
        <meshStandardMaterial {...seam} />
      </mesh>
      <mesh position={[1.95, -0.1, 0.03]} rotation={[0, 0, Math.PI / 2 - 0.08]}>
        <boxGeometry args={[2.55, 0.025, 0.025]} />
        <meshStandardMaterial {...seam} />
      </mesh>
      <mesh position={[-1.8, 1.25, 0.04]} rotation={[0, 0, -0.16]}>
        <boxGeometry args={[2.9, 0.022, 0.022]} />
        <meshStandardMaterial {...seam} />
      </mesh>
    </>
  );
}

export function LoginHeroScene({ onFallback, onReady }: Props) {
  const failed = useRef(false);
  useEffect(
    () => () => {
      failed.current = true;
    },
    [],
  );
  return (
    <div
      className="login-hero-scene"
      data-testid="login-hero-scene"
      aria-hidden="true"
    >
      <Canvas
        dpr={[1, 1.25]}
        frameloop="demand"
        camera={{ position: [0, 0.05, 8.5], fov: 40 }}
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: 'high-performance',
        }}
        onCreated={({ gl }) => {
          const canvas = gl.domElement;
          canvas.addEventListener(
            'webglcontextlost',
            (event: Event) => {
              event.preventDefault();
              if (!failed.current) {
                failed.current = true;
                onFallback();
              }
            },
            { once: true },
          );
          requestAnimationFrame(() => {
            if (!failed.current) onReady();
          });
        }}
      >
        <StaticComposition />
      </Canvas>
    </div>
  );
}
