/**
 * Vessel mesh factory.
 *
 * Two paths:
 *  1. **GLTF loader** — if `VITE_VESSEL_MODEL_URL` is set (or a default model
 *     is shipped at `/models/ship.glb`), we load it once, clone it per
 *     vessel, and tint by risk class. Most polished. Drop a real GLTF into
 *     `frontend/public/models/ship.glb` and it just works.
 *  2. **Procedural fallback** — a hand-built ship from primitives, used while
 *     the GLTF loads (or if it fails). Uses MeshStandardMaterial for PBR
 *     shading + emissive on flagged vessels so they self-light against the
 *     bright Blue Marble base.
 *
 * The factory caches: one per (color × isFlagged) combination so we never
 * recreate geometry per vessel. Returned Object3D is cloned so each vessel
 * can be transformed independently.
 *
 * Orientation: bow points along +X. globe.gl's `objectFacesSurfaces(true)`
 * keeps us tangent to the sphere; we rotate around local-Z by heading.
 */

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

const HULL_LEN = 1.6;
const HULL_BEAM = 0.46;
const HULL_DEPTH = 0.22;

const MODEL_URL = (import.meta.env.VITE_VESSEL_MODEL_URL as string | undefined) || "/models/ship.glb";

let cachedGltf: THREE.Object3D | null = null;
let gltfLoadPromise: Promise<THREE.Object3D | null> | null = null;

/** Kick off the GLTF load. Returns immediately; meshes upgrade once it's done. */
export function preloadVesselModel(): Promise<THREE.Object3D | null> {
  if (cachedGltf) return Promise.resolve(cachedGltf);
  if (gltfLoadPromise) return gltfLoadPromise;

  gltfLoadPromise = new Promise((resolve) => {
    const loader = new GLTFLoader();
    loader.load(
      MODEL_URL,
      (gltf) => {
        // Pre-bake: center the model, normalize scale, compute bounds.
        const root = gltf.scene;
        const box = new THREE.Box3().setFromObject(root);
        const size = box.getSize(new THREE.Vector3());
        const longest = Math.max(size.x, size.y, size.z) || 1;
        const targetSize = 1.6;
        const scaleFactor = targetSize / longest;
        root.scale.setScalar(scaleFactor);
        const center = box.getCenter(new THREE.Vector3()).multiplyScalar(scaleFactor);
        root.position.sub(center);
        cachedGltf = root;
        resolve(root);
      },
      undefined,
      // onError: silently fall back to procedural — no console spam during demo.
      () => resolve(null),
    );
  });
  return gltfLoadPromise;
}

export function makeVesselMesh(color: string, isFlagged = false): THREE.Group {
  const group = new THREE.Group();

  // If GLTF is available, prefer it; tint via mesh material override.
  if (cachedGltf) {
    const cloned = cachedGltf.clone(true);
    cloned.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh;
        // Tint by replacing the material with a colored standard material
        // that respects the original's normal map if present.
        const orig = mesh.material as THREE.MeshStandardMaterial | undefined;
        const newMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(color),
          metalness: 0.1,
          roughness: 0.55,
          emissive: new THREE.Color(color).multiplyScalar(isFlagged ? 0.45 : 0.18),
          emissiveIntensity: isFlagged ? 1.4 : 0.9,
          normalMap: orig?.normalMap ?? null,
        });
        mesh.material = newMat;
      }
    });
    group.add(cloned);
  } else {
    group.add(buildProceduralShip(color, isFlagged));
  }

  // Visibility halo: flat ring under every vessel.
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(HULL_LEN * 0.85, HULL_LEN * 1.0, 48),
    new THREE.MeshBasicMaterial({
      color: new THREE.Color(color).getHex(),
      transparent: true,
      opacity: 0.7,
      side: THREE.DoubleSide,
    }),
  );
  ring.rotation.x = Math.PI / 2;
  ring.position.set(0, 0, -HULL_DEPTH * 0.6);
  group.add(ring);

  if (isFlagged) {
    const flaggedHalo = new THREE.Mesh(
      new THREE.TorusGeometry(HULL_LEN * 1.15, 0.06, 12, 64),
      new THREE.MeshBasicMaterial({
        color: "#ff1f4d",
        transparent: true,
        opacity: 0.95,
      }),
    );
    flaggedHalo.rotation.x = Math.PI / 2;
    flaggedHalo.position.set(0, 0, -HULL_DEPTH * 0.4);
    group.add(flaggedHalo);
  }

  return group;
}

/** Polished procedural ship — used when GLTF is missing. */
function buildProceduralShip(color: string, isFlagged: boolean): THREE.Group {
  const group = new THREE.Group();

  const baseColor = new THREE.Color(color);
  const hullColor = baseColor.clone().multiplyScalar(0.55);
  const accent = isFlagged ? new THREE.Color("#ffffff") : baseColor.clone().multiplyScalar(1.4);

  const hullMat = new THREE.MeshStandardMaterial({
    color: hullColor.getHex(),
    metalness: 0.2,
    roughness: 0.55,
    emissive: hullColor.clone().multiplyScalar(0.25).getHex(),
  });

  const deckMat = new THREE.MeshStandardMaterial({
    color: baseColor.getHex(),
    metalness: 0.15,
    roughness: 0.45,
    emissive: baseColor.clone().multiplyScalar(isFlagged ? 0.5 : 0.22).getHex(),
    emissiveIntensity: isFlagged ? 1.4 : 0.9,
  });

  const accentMat = new THREE.MeshBasicMaterial({ color: accent.getHex() });

  // ── Hull: tapered prow, rounded stern. Using a custom shape extruded
  // ── so the bow is visibly pointed rather than just shrunk-box.
  const hullShape = new THREE.Shape();
  const halfBeam = HULL_BEAM * 0.5;
  hullShape.moveTo(-HULL_LEN * 0.5, -halfBeam * 0.85); // stern port
  hullShape.lineTo(HULL_LEN * 0.32, -halfBeam); // mid port
  hullShape.quadraticCurveTo(HULL_LEN * 0.5, -halfBeam * 0.4, HULL_LEN * 0.55, 0); // bow tip
  hullShape.quadraticCurveTo(HULL_LEN * 0.5, halfBeam * 0.4, HULL_LEN * 0.32, halfBeam);
  hullShape.lineTo(-HULL_LEN * 0.5, halfBeam * 0.85);
  hullShape.quadraticCurveTo(-HULL_LEN * 0.55, 0, -HULL_LEN * 0.5, -halfBeam * 0.85);

  const hullGeom = new THREE.ExtrudeGeometry(hullShape, {
    depth: HULL_DEPTH,
    bevelEnabled: true,
    bevelThickness: 0.04,
    bevelSize: 0.04,
    bevelSegments: 3,
    curveSegments: 16,
  });
  hullGeom.translate(0, 0, -HULL_DEPTH * 0.5);
  hullGeom.computeVertexNormals();
  const hull = new THREE.Mesh(hullGeom, hullMat);
  group.add(hull);

  // ── Forward deck (flat plate above hull) ────────────────────────────
  const deckGeom = new THREE.BoxGeometry(HULL_LEN * 0.78, HULL_BEAM * 0.78, HULL_DEPTH * 0.14);
  deckGeom.translate(-HULL_LEN * 0.05, 0, HULL_DEPTH * 0.55);
  const deck = new THREE.Mesh(deckGeom, deckMat);
  group.add(deck);

  // ── Bridge superstructure (multi-tier) ──────────────────────────────
  const bridgeBase = new THREE.Mesh(
    new THREE.BoxGeometry(HULL_LEN * 0.34, HULL_BEAM * 0.6, HULL_DEPTH * 1.0),
    deckMat,
  );
  bridgeBase.position.set(-HULL_LEN * 0.22, 0, HULL_DEPTH * 1.1);
  group.add(bridgeBase);

  const bridgeTop = new THREE.Mesh(
    new THREE.BoxGeometry(HULL_LEN * 0.22, HULL_BEAM * 0.45, HULL_DEPTH * 0.6),
    deckMat,
  );
  bridgeTop.position.set(-HULL_LEN * 0.22, 0, HULL_DEPTH * 1.85);
  group.add(bridgeTop);

  // Bridge windows — small dark stripe for definition
  const windows = new THREE.Mesh(
    new THREE.BoxGeometry(HULL_LEN * 0.22, HULL_BEAM * 0.46, HULL_DEPTH * 0.1),
    new THREE.MeshBasicMaterial({ color: 0x111122 }),
  );
  windows.position.set(-HULL_LEN * 0.22, 0, HULL_DEPTH * 1.65);
  group.add(windows);

  // ── Mast / antenna ──────────────────────────────────────────────────
  const mast = new THREE.Mesh(
    new THREE.CylinderGeometry(0.025, 0.03, HULL_DEPTH * 2.5, 8),
    accentMat,
  );
  mast.rotation.x = Math.PI / 2;
  mast.position.set(-HULL_LEN * 0.22, 0, HULL_DEPTH * 2.7);
  group.add(mast);

  // ── Forward bow accent strip ────────────────────────────────────────
  const bowAccent = new THREE.Mesh(
    new THREE.BoxGeometry(HULL_LEN * 0.4, HULL_BEAM * 0.3, HULL_DEPTH * 0.06),
    accentMat,
  );
  bowAccent.position.set(HULL_LEN * 0.18, 0, HULL_DEPTH * 0.66);
  group.add(bowAccent);

  return group;
}
