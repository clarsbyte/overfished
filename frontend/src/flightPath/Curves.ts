/**
 * Curves — single-draw-call curve renderer for flight paths.
 *
 * Direct port of jeantimex/flight-path's `src/curves/Curves.ts`. All
 * curves are merged into ONE `THREE.LineSegments` mesh with per-vertex
 * colors and accumulated `lineDistance` attributes. `THREE.LineDashedMaterial`
 * handles the dash pattern natively — no shader needed.
 *
 * Adapted from MIT-licensed flight-path source. We've simplified the
 * gradient-color path: vessels use a single-color-per-curve gradient
 * (start dim, end bright) computed by the caller rather than the
 * lat/lng-derived HSL gradient the original used.
 */

import * as THREE from "three";

export interface CurvesOptions {
  maxCurves?: number;
  segmentsPerCurve?: number;
  dashSize?: number;
  gapSize?: number;
}

export interface CurveColorPair {
  start: THREE.Color;
  end: THREE.Color;
}

interface CurveSlot {
  controlPoints: THREE.Vector3[];
  startColor: THREE.Color;
  endColor: THREE.Color;
  visible: boolean;
}

export class Curves {
  private readonly scene: THREE.Scene;
  private readonly maxCurves: number;
  private readonly segmentsPerCurve: number;
  private readonly verticesPerSegment = 2;
  private readonly verticesPerCurve: number;
  private dashSize: number;
  private gapSize: number;

  private geometry: THREE.BufferGeometry | null = null;
  private material: THREE.Material | null = null;
  private mesh: THREE.LineSegments | null = null;

  private positions: Float32Array | null = null;
  private colors: Float32Array | null = null;
  private lineDistances: Float32Array | null = null;

  private currentCurveCount = 0;
  private needsPositionUpdate = false;
  private needsColorUpdate = false;
  private needsLineDistanceUpdate = false;

  private slots: CurveSlot[] = [];

  constructor(scene: THREE.Scene, options: CurvesOptions = {}) {
    this.scene = scene;
    this.maxCurves = options.maxCurves ?? 1000;
    this.segmentsPerCurve = options.segmentsPerCurve ?? 100;
    this.verticesPerCurve = this.segmentsPerCurve * this.verticesPerSegment;
    this.dashSize = options.dashSize ?? 0;
    this.gapSize = options.gapSize ?? 0;
    this.initialize();
  }

  private initialize(): void {
    const totalVertices = this.maxCurves * this.verticesPerCurve;
    this.positions = new Float32Array(totalVertices * 3);
    this.colors = new Float32Array(totalVertices * 3);
    this.lineDistances = new Float32Array(totalVertices);

    this.geometry = new THREE.BufferGeometry();
    this.geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(this.positions, 3),
    );
    this.geometry.setAttribute(
      "color",
      new THREE.BufferAttribute(this.colors, 3),
    );
    this.geometry.setAttribute(
      "lineDistance",
      new THREE.BufferAttribute(this.lineDistances, 1),
    );

    this.material = this.createMaterial();
    this.mesh = new THREE.LineSegments(this.geometry, this.material);
    this.geometry.setDrawRange(0, 0);
    this.scene.add(this.mesh);

    for (let i = 0; i < this.maxCurves; i++) {
      this.slots.push({
        controlPoints: [],
        startColor: new THREE.Color(0x4488ff),
        endColor: new THREE.Color(0xffffff),
        visible: false,
      });
    }
  }

  /** Set / update a curve at the given slot. */
  public setCurve(
    curveIndex: number,
    controlPoints: THREE.Vector3[],
    colors: CurveColorPair,
  ): void {
    if (curveIndex < 0 || curveIndex >= this.maxCurves) return;
    if (!controlPoints || controlPoints.length < 2) return;

    const slot = this.slots[curveIndex];
    slot.controlPoints = controlPoints;
    slot.startColor = colors.start;
    slot.endColor = colors.end;
    slot.visible = true;

    const curve = new THREE.CatmullRomCurve3(controlPoints);
    const points = curve.getPoints(this.segmentsPerCurve);

    const vertexOffset = curveIndex * this.verticesPerCurve;
    let distance = 0;

    for (let s = 0; s < this.segmentsPerCurve; s++) {
      const a = points[s];
      const b = points[s + 1];
      const vIdx = vertexOffset + s * this.verticesPerSegment;
      const bIdx = vIdx * 3;

      if (this.positions) {
        this.positions[bIdx] = a.x;
        this.positions[bIdx + 1] = a.y;
        this.positions[bIdx + 2] = a.z;
        this.positions[bIdx + 3] = b.x;
        this.positions[bIdx + 4] = b.y;
        this.positions[bIdx + 5] = b.z;
      }
      if (this.lineDistances) {
        this.lineDistances[vIdx] = distance;
        distance += a.distanceTo(b);
        this.lineDistances[vIdx + 1] = distance;
      }
    }

    this.applyColorToCurve(curveIndex);

    this.needsPositionUpdate = true;
    this.needsLineDistanceUpdate = true;

    if (curveIndex >= this.currentCurveCount) {
      this.currentCurveCount = curveIndex + 1;
      this.updateDrawRange();
    }
  }

  private applyColorToCurve(curveIndex: number): void {
    const slot = this.slots[curveIndex];
    if (!slot.visible || !this.colors) return;

    const vertexOffset = curveIndex * this.verticesPerCurve;
    const tmp = new THREE.Color();

    for (let s = 0; s < this.segmentsPerCurve; s++) {
      const vIdx = vertexOffset + s * this.verticesPerSegment;
      const bIdx = vIdx * 3;

      const tStart = s / this.segmentsPerCurve;
      const tEnd = (s + 1) / this.segmentsPerCurve;

      tmp.copy(slot.startColor).lerp(slot.endColor, tStart);
      this.colors[bIdx] = tmp.r;
      this.colors[bIdx + 1] = tmp.g;
      this.colors[bIdx + 2] = tmp.b;

      tmp.copy(slot.startColor).lerp(slot.endColor, tEnd);
      this.colors[bIdx + 3] = tmp.r;
      this.colors[bIdx + 4] = tmp.g;
      this.colors[bIdx + 5] = tmp.b;
    }

    this.needsColorUpdate = true;
  }

  public hideCurve(curveIndex: number): void {
    if (curveIndex < 0 || curveIndex >= this.maxCurves) return;
    const slot = this.slots[curveIndex];
    slot.visible = false;

    if (!this.positions || !this.lineDistances) return;
    const vOff3 = curveIndex * this.verticesPerCurve * 3;
    const totalV3 = this.verticesPerCurve * 3;
    for (let i = 0; i < totalV3; i++) this.positions[vOff3 + i] = 0;
    const dOff = curveIndex * this.verticesPerCurve;
    for (let i = 0; i < this.verticesPerCurve; i++) this.lineDistances[dOff + i] = 0;

    this.needsPositionUpdate = true;
    this.needsLineDistanceUpdate = true;
  }

  public setVisibleCurveCount(count: number): void {
    this.currentCurveCount = Math.min(count, this.maxCurves);
    this.updateDrawRange();
  }

  private updateDrawRange(): void {
    if (!this.geometry) return;
    this.geometry.setDrawRange(0, this.currentCurveCount * this.verticesPerCurve);
  }

  /** Call once per frame after batched updates. */
  public applyUpdates(): void {
    if (!this.geometry) return;
    if (this.needsPositionUpdate) {
      this.geometry.attributes.position.needsUpdate = true;
      this.needsPositionUpdate = false;
    }
    if (this.needsColorUpdate) {
      this.geometry.attributes.color.needsUpdate = true;
      this.needsColorUpdate = false;
    }
    if (this.dashSize > 0 && this.needsLineDistanceUpdate) {
      if (this.geometry.attributes.lineDistance) {
        this.geometry.attributes.lineDistance.needsUpdate = true;
      }
      this.needsLineDistanceUpdate = false;
    } else if (this.dashSize === 0) {
      this.needsLineDistanceUpdate = false;
    }
  }

  public setDashPattern(dashSize: number, gapSize: number): void {
    const nextDash = Math.max(0, dashSize);
    const nextGap = Math.max(0, gapSize);
    if (this.dashSize === nextDash && this.gapSize === nextGap) return;
    this.dashSize = nextDash;
    this.gapSize = nextGap;
    this.updateMaterial();
  }

  public setVisible(visible: boolean): void {
    if (this.mesh) this.mesh.visible = visible;
  }

  public remove(): void {
    if (this.mesh && this.geometry && this.material) {
      this.scene.remove(this.mesh);
      this.geometry.dispose();
      this.material.dispose();
      this.mesh = null;
    }
    this.slots = [];
  }

  private createMaterial(): THREE.Material {
    if (this.dashSize > 0) {
      return new THREE.LineDashedMaterial({
        vertexColors: true,
        dashSize: this.dashSize,
        gapSize: Math.max(this.gapSize, 1e-4),
      });
    }
    return new THREE.LineBasicMaterial({ vertexColors: true });
  }

  private updateMaterial(): void {
    if (!this.mesh) return;
    if (this.material) this.material.dispose();
    this.material = this.createMaterial();
    this.mesh.material = this.material;
    this.mesh.material.needsUpdate = true;
    if (this.dashSize > 0) {
      this.needsLineDistanceUpdate = true;
    }
  }
}
