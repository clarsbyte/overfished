/**
 * PlanesShader — GPU-instanced "vessels flying along curves" renderer.
 *
 * Direct port of jeantimex/flight-path's `src/planes/PlanesShader.ts`. The
 * load-bearing trick: a SINGLE `THREE.InstancedMesh` renders all vessels
 * in one draw call. The vertex shader evaluates each vessel's CatmullRom
 * curve on the GPU and positions the billboarded quad along it. CPU does
 * one uniform increment per frame — that's it.
 *
 * Per-instance attributes pack 4 control points (3 × vec4) plus animation
 * metadata (`phase`, `speed`, `tiltMode`, `visible`). Phase is randomized
 * so vessels don't all start synchronized.
 *
 * Adapted from MIT-licensed flight-path source. We've dropped:
 *   - The texture-atlas UV unpack (we use a single-color material, no SVG
 *     atlas of vessel variants).
 *   - The `setReturnMode` reconciliation bookkeeping (we don't expose
 *     return-flight mode in our UI yet).
 *
 * The shader files (`panes.vert`, `panes.frag`) are byte-identical to the
 * upstream copies.
 */

import * as THREE from "three";
import fragmentShader from "./shaders/panes.frag";
import vertexShader from "./shaders/panes.vert";

export type TiltMode = "Perpendicular" | "Tangent";

export interface PlanesShaderOptions {
  maxPanes?: number;
  baseSize?: number;
  baseElevation?: number;
}

export class PlanesShader {
  private scene: THREE.Scene;
  private maxPanes: number;
  private baseSize: number;
  private defaultElevation: number;

  private instancedMesh: THREE.InstancedMesh | null = null;
  private geometry: THREE.PlaneGeometry | null = null;
  private material: THREE.ShaderMaterial | null = null;

  // Per-instance curve control points (4 points = 12 floats, packed into 3 vec4 attrs)
  private controlPointsPack1: Float32Array;
  private controlPointsPack2: Float32Array;
  private controlPointsPack3: Float32Array;

  private instanceColors: Float32Array;
  private instanceScales: Float32Array;
  private instanceElevations: Float32Array;
  private instanceUvTransforms: Float32Array;
  private animationParams: Float32Array;

  private planesVisible: boolean = true;

  constructor(scene: THREE.Scene, options: PlanesShaderOptions = {}) {
    this.scene = scene;
    this.maxPanes = options.maxPanes ?? 1000;
    this.baseSize = options.baseSize ?? 100;
    this.defaultElevation =
      options.baseElevation !== undefined ? options.baseElevation : 0;

    this.controlPointsPack1 = new Float32Array(this.maxPanes * 4);
    this.controlPointsPack2 = new Float32Array(this.maxPanes * 4);
    this.controlPointsPack3 = new Float32Array(this.maxPanes * 4);
    this.instanceColors = new Float32Array(this.maxPanes * 3);
    this.instanceScales = new Float32Array(this.maxPanes);
    this.instanceElevations = new Float32Array(this.maxPanes);
    this.instanceUvTransforms = new Float32Array(this.maxPanes * 4);
    this.animationParams = new Float32Array(this.maxPanes * 4);

    this.initialize();
  }

  private initialize(): void {
    this.geometry = new THREE.PlaneGeometry(this.baseSize, this.baseSize);

    const setAttr = (name: string, arr: Float32Array, itemSize: number) => {
      this.geometry!.setAttribute(
        name,
        new THREE.InstancedBufferAttribute(arr, itemSize),
      );
    };

    setAttr("controlPointsPack1", this.controlPointsPack1, 4);
    setAttr("controlPointsPack2", this.controlPointsPack2, 4);
    setAttr("controlPointsPack3", this.controlPointsPack3, 4);
    setAttr("instanceColor", this.instanceColors, 3);
    setAttr("instanceScale", this.instanceScales, 1);
    setAttr("instanceElevation", this.instanceElevations, 1);
    setAttr("instanceUVTransform", this.instanceUvTransforms, 4);
    setAttr("animationParams", this.animationParams, 4);

    this.material = new THREE.ShaderMaterial({
      uniforms: {
        time: { value: 0.0 },
        baseSize: { value: this.baseSize },
        paneMap: { value: null },
        useTexture: { value: 0.0 },
        returnMode: { value: 0.0 },
        paneVisibility: { value: 1.0 },
      },
      vertexShader,
      fragmentShader,
      side: THREE.DoubleSide,
      transparent: true,
    });

    this.instancedMesh = new THREE.InstancedMesh(
      this.geometry,
      this.material,
      this.maxPanes,
    );

    for (let i = 0; i < this.maxPanes; i++) {
      this.instanceColors[i * 3] = 1.0;
      this.instanceColors[i * 3 + 1] = 1.0;
      this.instanceColors[i * 3 + 2] = 1.0;
      this.instanceScales[i] = 0.0; // hidden until setCurveControlPoints is called
      this.instanceElevations[i] = this.defaultElevation;

      this.animationParams[i * 4] = Math.random(); // phase
      this.animationParams[i * 4 + 1] = 0.1; // speed
      this.animationParams[i * 4 + 2] = 0.0; // tiltMode (0=Perpendicular)
      this.animationParams[i * 4 + 3] = 0.0; // visible (0=hidden)

      const uvIndex = i * 4;
      this.instanceUvTransforms[uvIndex] = 0.0;
      this.instanceUvTransforms[uvIndex + 1] = 0.0;
      this.instanceUvTransforms[uvIndex + 2] = 1.0;
      this.instanceUvTransforms[uvIndex + 3] = 1.0;
    }

    this.markAllAttributesNeedUpdate();
    this.scene.add(this.instancedMesh);
  }

  /** Set the 4 CatmullRom control points for one vessel. Called once per setup. */
  public setCurveControlPoints(
    index: number,
    controlPoints: THREE.Vector3[],
  ): void {
    if (index < 0 || index >= this.maxPanes) return;
    if (controlPoints.length < 4) {
      console.warn("PlanesShader requires 4 control points");
      return;
    }

    this.controlPointsPack1[index * 4] = controlPoints[0].x;
    this.controlPointsPack1[index * 4 + 1] = controlPoints[0].y;
    this.controlPointsPack1[index * 4 + 2] = controlPoints[0].z;
    this.controlPointsPack1[index * 4 + 3] = controlPoints[1].x;

    this.controlPointsPack2[index * 4] = controlPoints[1].y;
    this.controlPointsPack2[index * 4 + 1] = controlPoints[1].z;
    this.controlPointsPack2[index * 4 + 2] = controlPoints[2].x;
    this.controlPointsPack2[index * 4 + 3] = controlPoints[2].y;

    this.controlPointsPack3[index * 4] = controlPoints[2].z;
    this.controlPointsPack3[index * 4 + 1] = controlPoints[3].x;
    this.controlPointsPack3[index * 4 + 2] = controlPoints[3].y;
    this.controlPointsPack3[index * 4 + 3] = controlPoints[3].z;

    this.animationParams[index * 4 + 3] = 1.0; // mark visible

    if (this.geometry) {
      this.geometry.attributes.controlPointsPack1.needsUpdate = true;
      this.geometry.attributes.controlPointsPack2.needsUpdate = true;
      this.geometry.attributes.controlPointsPack3.needsUpdate = true;
      this.geometry.attributes.animationParams.needsUpdate = true;
    }
  }

  public setPaneColor(
    index: number,
    color: THREE.Color | THREE.ColorRepresentation,
  ): void {
    if (index < 0 || index >= this.maxPanes) return;
    const c = color instanceof THREE.Color ? color : new THREE.Color(color);
    this.instanceColors[index * 3] = c.r;
    this.instanceColors[index * 3 + 1] = c.g;
    this.instanceColors[index * 3 + 2] = c.b;
    if (this.geometry) {
      this.geometry.attributes.instanceColor.needsUpdate = true;
    }
  }

  public setPaneSize(index: number, size: number): void {
    if (index < 0 || index >= this.maxPanes) return;
    this.instanceScales[index] = size / this.baseSize;
    if (this.geometry) {
      this.geometry.attributes.instanceScale.needsUpdate = true;
    }
  }

  public setElevationOffset(index: number, offset: number): void {
    if (index < 0 || index >= this.maxPanes) return;
    this.instanceElevations[index] = offset;
    if (this.geometry?.attributes.instanceElevation) {
      this.geometry.attributes.instanceElevation.needsUpdate = true;
    }
  }

  public setAnimationSpeed(index: number, speed: number): void {
    if (index < 0 || index >= this.maxPanes) return;
    this.animationParams[index * 4 + 1] = speed;
    if (this.geometry) {
      this.geometry.attributes.animationParams.needsUpdate = true;
    }
  }

  public setTiltMode(index: number, mode: TiltMode): void {
    if (index < 0 || index >= this.maxPanes) return;
    this.animationParams[index * 4 + 2] = mode === "Tangent" ? 1.0 : 0.0;
    if (this.geometry) {
      this.geometry.attributes.animationParams.needsUpdate = true;
    }
  }

  public hidePane(index: number): void {
    if (index < 0 || index >= this.maxPanes) return;
    this.animationParams[index * 4 + 3] = 0.0;
    if (this.geometry) {
      this.geometry.attributes.animationParams.needsUpdate = true;
    }
  }

  /** The ONLY method that needs calling every frame. Increments uTime. */
  public update(deltaTime: number): void {
    if (!this.material?.uniforms) return;
    this.material.uniforms.time.value += deltaTime;
  }

  public setPlanesVisible(visible: boolean): void {
    this.planesVisible = !!visible;
    if (this.material?.uniforms?.paneVisibility) {
      this.material.uniforms.paneVisibility.value = this.planesVisible
        ? 1.0
        : 0.0;
    }
  }

  public getMaxPanes(): number {
    return this.maxPanes;
  }

  public remove(): void {
    if (this.instancedMesh) {
      this.scene.remove(this.instancedMesh);
      this.geometry?.dispose();
      this.material?.dispose();
      this.instancedMesh = null;
    }
  }

  private markAllAttributesNeedUpdate(): void {
    if (!this.geometry) return;
    for (const key of [
      "controlPointsPack1",
      "controlPointsPack2",
      "controlPointsPack3",
      "instanceColor",
      "instanceScale",
      "instanceElevation",
      "instanceUVTransform",
      "animationParams",
    ]) {
      const attr = this.geometry.attributes[key];
      if (attr) attr.needsUpdate = true;
    }
  }
}
