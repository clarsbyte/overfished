/**
 * useAnimatedFleet — interpolate vessel positions along their tracks.
 *
 * Performance contract:
 *   - The hook re-renders at most ~30 Hz (every 33ms), not every animation
 *     frame. globe.gl re-lays out objects when ``objectsData`` ref changes;
 *     30 Hz looks smooth and halves the React reconciliation cost vs 60 Hz.
 *   - Vessel positions are mutated *in place* inside a stable
 *     ``AnimatedVessel[]`` array. The array ref is bumped on each tick so
 *     globe.gl picks up the new positions.
 *   - The hook does NOT clone or rebuild the array per frame. It writes
 *     ``v.lat = …; v.lng = …; v.heading = …`` and bumps a tick counter to
 *     produce a new stable reference for React.
 *
 * This means the parent ``<OverfishGlobe>`` re-renders 30 times/sec, but
 * each re-render does no per-vessel work beyond globe.gl's internal
 * position update.
 */

import { useEffect, useRef, useState } from "react";

export interface FleetVessel {
  mmsi: string;
  name: string;
  flag: string;
  risk: "confirmed_iuu" | "high_risk" | "suspect" | "safe";
  points: [number, number][];
}

export interface AnimatedVessel extends FleetVessel {
  lat: number;
  lng: number;
  heading: number; // degrees clockwise from north
}

const FULL_LOOP_SECONDS = 90;
const TICK_HZ = 15; // re-render rate; 15 fps still reads as smooth motion at this scale

export function useAnimatedFleet(fleet: FleetVessel[] | undefined): AnimatedVessel[] {
  // Stable per-vessel object array. Mutated in place; only reseeded when the
  // ``fleet`` input changes. We bump a React state to nudge re-render at
  // TICK_HZ; globe.gl picks up new positions on each render.
  const animatedRef = useRef<AnimatedVessel[]>([]);
  const startRef = useRef<number>(performance.now());
  const [, setTick] = useState(0);

  // Re-seed the AnimatedVessel array when the fleet input changes.
  useEffect(() => {
    if (!fleet) {
      animatedRef.current = [];
      return;
    }
    animatedRef.current = fleet.map((v) => {
      const [lat, lng] = v.points[0] ?? [0, 0];
      return { ...v, lat, lng, heading: 0 };
    });
    setTick((t) => t + 1);
  }, [fleet]);

  // RAF + interval combo: animate in lock-step but only nudge React at TICK_HZ.
  // Also pauses entirely while the tab is hidden (no point burning CPU when
  // nobody is watching the globe).
  useEffect(() => {
    if (!fleet || fleet.length === 0) return;

    let raf = 0;
    let lastReact = 0;
    const reactInterval = 1000 / TICK_HZ;

    const tick = () => {
      const now = performance.now();
      const elapsedMs = now - startRef.current;
      const animated = animatedRef.current;
      const n = animated.length;

      for (let idx = 0; idx < n; idx++) {
        const v = animated[idx];
        const points = v.points;
        const trackLen = points.length;
        if (trackLen < 2) continue;

        const phase = (idx / n) * FULL_LOOP_SECONDS * 1000;
        const t = ((elapsedMs + phase) % (FULL_LOOP_SECONDS * 1000)) / (FULL_LOOP_SECONDS * 1000);

        const segCount = trackLen - 1;
        const segIdx = Math.min(segCount - 1, Math.floor(t * segCount));
        const segT = t * segCount - segIdx;

        const a = points[segIdx];
        const b = points[segIdx + 1];
        v.lat = a[0] + (b[0] - a[0]) * segT;
        v.lng = a[1] + (b[1] - a[1]) * segT;
        v.heading = bearing(a[0], a[1], b[0], b[1]);
      }

      if (now - lastReact >= reactInterval) {
        lastReact = now;
        setTick((tk) => tk + 1);
      }

      raf = requestAnimationFrame(tick);
    };

    const start = () => {
      if (raf) return;
      raf = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (raf) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") stop();
      else start();
    };

    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fleet]);

  return animatedRef.current;
}

function bearing(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const φ1 = (lat1 * Math.PI) / 180;
  const φ2 = (lat2 * Math.PI) / 180;
  const Δλ = ((lng2 - lng1) * Math.PI) / 180;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}
