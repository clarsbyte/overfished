/**
 * Polygon-drawing hook for react-globe.gl.
 *
 * State machine: idle → drawing → committed.
 *  - Single click on the globe: append a vertex.
 *  - Double-click (or Enter) once ≥3 vertices exist: close ring → commit.
 *  - Esc: discard.
 *
 * GeoJSON note: GeoJSON coordinates are [lng, lat]; globe.gl callbacks return
 * { lat, lng }. We flip exactly once at commit time. Don't flip elsewhere.
 */

import type { GlobeMethods } from "react-globe.gl";
import { useCallback, useEffect, useRef, useState } from "react";

export type DrawMode = "idle" | "drawing" | "committed";

export interface Vertex {
  lat: number;
  lng: number;
}

interface Options {
  globeRef: React.MutableRefObject<GlobeMethods | undefined>;
  onCommit: (polygon: GeoJSON.Polygon) => void;
}

interface DrawingPath {
  kind: "draft";
  pts: Vertex[];
}

interface CommittedPoly {
  kind: "committed";
  geometry: GeoJSON.Polygon;
}

export function useDrawController({ globeRef, onCommit }: Options) {
  const [mode, setMode] = useState<DrawMode>("idle");
  const [vertices, setVertices] = useState<Vertex[]>([]);
  const [committed, setCommitted] = useState<GeoJSON.Polygon | null>(null);
  const lastClickRef = useRef<{ t: number; lat: number; lng: number } | null>(null);

  const commit = useCallback(() => {
    if (vertices.length < 3) return;
    const ring: GeoJSON.Position[] = [
      ...vertices.map<GeoJSON.Position>((v) => [v.lng, v.lat]),
      [vertices[0].lng, vertices[0].lat],
    ];
    const polygon: GeoJSON.Polygon = { type: "Polygon", coordinates: [ring] };

    setCommitted(polygon);
    setVertices([]);
    setMode("committed");
    onCommit(polygon);

    // Camera fly-in to centroid (PRD §4.5.2 region fly-in)
    const c = centroid(polygon);
    globeRef.current?.pointOfView({ lat: c.lat, lng: c.lng, altitude: 0.6 }, 2500);
  }, [vertices, onCommit, globeRef]);

  // Keyboard: Esc cancels, Enter commits
  useEffect(() => {
    if (mode !== "drawing") return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMode("idle");
        setVertices([]);
      } else if (e.key === "Enter") {
        commit();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [mode, commit]);

  const onGlobeClick = useCallback(
    ({ lat, lng }: { lat: number; lng: number }) => {
      if (mode !== "drawing") return;

      // Manual double-click detection: same coord within 350 ms.
      const now = Date.now();
      const last = lastClickRef.current;
      if (last && now - last.t < 350 && Math.abs(last.lat - lat) < 0.5 && Math.abs(last.lng - lng) < 0.5) {
        if (vertices.length >= 2) {
          // Pretend the user clicked-to-commit on the existing vertex set;
          // commit synchronously without pushing a duplicate.
          commit();
          lastClickRef.current = null;
          return;
        }
      }

      lastClickRef.current = { t: now, lat, lng };
      setVertices((v) => [...v, { lat, lng }]);
    },
    [mode, vertices.length, commit],
  );

  const startDrawing = useCallback(() => {
    setMode("drawing");
    setVertices([]);
    setCommitted(null);
  }, []);

  const reset = useCallback(() => {
    setMode("idle");
    setVertices([]);
    setCommitted(null);
  }, []);

  // Outputs ready to spread into <Globe> props
  const drawingPathsData: DrawingPath[] = vertices.length >= 2 ? [{ kind: "draft", pts: vertices }] : [];
  const drawingPointsData = vertices;
  const committedPolygonsData: CommittedPoly[] = committed ? [{ kind: "committed", geometry: committed }] : [];

  return {
    mode,
    vertices,
    committed,
    onGlobeClick,
    startDrawing,
    commit,
    reset,
    drawingPathsData,
    drawingPointsData,
    committedPolygonsData,
  };
}

function centroid(poly: GeoJSON.Polygon): { lat: number; lng: number } {
  const ring = poly.coordinates[0];
  const lng = ring.reduce((s: number, p) => s + (p[0] as number), 0) / ring.length;
  const lat = ring.reduce((s: number, p) => s + (p[1] as number), 0) / ring.length;
  return { lat, lng };
}
