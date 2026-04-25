/**
 * Load /sprites/vessel.svg, rasterize it to a canvas, and return a
 * `THREE.Texture` for the PlanesShader's `paneMap` uniform.
 *
 * Pattern adapted from flight-path-study/src/App.ts:563-669, simplified to
 * a single SVG (no atlas of 8 plane variants).
 */

import * as THREE from "three";

const SVG_URL = "/sprites/vessel.svg";
const RASTER_W = 256;
const RASTER_H = 1024;

let cached: Promise<THREE.Texture> | null = null;

export function loadVesselTexture(): Promise<THREE.Texture> {
  if (cached) return cached;
  cached = (async () => {
    const res = await fetch(SVG_URL);
    if (!res.ok) throw new Error(`Failed to fetch ${SVG_URL}: ${res.status}`);
    const svgText = await res.text();
    const blob = new Blob([svgText], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);

    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const im = new Image();
      im.onload = () => resolve(im);
      im.onerror = (e) => reject(e);
      im.src = url;
    });

    const canvas = document.createElement("canvas");
    canvas.width = RASTER_W;
    canvas.height = RASTER_H;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, RASTER_W, RASTER_H);
    ctx.drawImage(img, 0, 0, RASTER_W, RASTER_H);
    URL.revokeObjectURL(url);

    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    return texture;
  })();
  return cached;
}
