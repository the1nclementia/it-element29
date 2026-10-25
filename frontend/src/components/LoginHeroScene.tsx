import { Canvas } from '@react-three/fiber';
import { useEffect, useRef } from 'react';

type Props = { onFallback: () => void; onReady: () => void };

function StaticComposition() {
  const seam = {
    color: '#ff6f1c',
    emissive: '#ff5a0a',
    emissiveIntensity: 2.6,
  };
  return (
    <>
      <color attach="background" args={['#eee7e2']} />
      <ambientLight intensity={1.8} color="#fff8f1" />
      <directionalLight position={[-4, 6, 5]} intensity={4} color="#fff4ea" />
      <pointLight
        position={[2, -1, 3]}
        intensity={18}
        distance={9}
        color="#ff7a2f"
      />
      <mesh position={[0, 0, -1.8]} rotation={[0, 0, -0.05]}>
        <boxGeometry args={[7.4, 3.2, 0.35]} />
        <meshStandardMaterial
          color="#e9e5e1"
          metalness={0.72}
          roughness={0.28}
        />
      </mesh>
      <mesh position={[2.4, -0.75, -0.4]} rotation={[0.08, -0.16, -0.02]}>
        <boxGeometry args={[3.2, 2.6, 1.5]} />
        <meshStandardMaterial
          color="#f4f0ec"
          metalness={0.82}
          roughness={0.24}
        />
      </mesh>
      <mesh position={[-2.2, 0.8, 0.2]} rotation={[-0.08, 0.22, 0.03]}>
        <boxGeometry args={[3.6, 1.5, 1.25]} />
        <meshStandardMaterial
          color="#faf8f4"
          metalness={0.76}
          roughness={0.26}
        />
      </mesh>
      <mesh position={[0.6, 0.1, 1.0]} rotation={[0, -0.12, 0.02]}>
        <boxGeometry args={[4.2, 1.7, 0.42]} />
        <meshStandardMaterial color="#e4dfda" metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[0.85, -0.76, 1.78]} rotation={[0, 0, 0.02]}>
        <boxGeometry args={[4.6, 0.045, 0.045]} />
        <meshStandardMaterial {...seam} />
      </mesh>
      <mesh position={[2.4, 0.03, 1.78]} rotation={[0, 0, Math.PI / 2]}>
        <boxGeometry args={[2.15, 0.045, 0.045]} />
        <meshStandardMaterial {...seam} />
      </mesh>
      <mesh position={[-1.25, 0.82, 1.78]} rotation={[0, 0, -0.02]}>
        <boxGeometry args={[2.8, 0.035, 0.035]} />
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
        camera={{ position: [0, 0.2, 8], fov: 34 }}
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
