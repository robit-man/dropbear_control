import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const PREVIEW_ROOT = "/assets/cad";

export const CAD_EVIDENCE = Object.freeze({
  model: "RMD-X12-320 source candidate",
  sourceStepSha256: "9b1710aef09916c8da02b4e6b750da6bbfe2ba44cad6ba03cd1b53e3858e5eea",
  housingTriangles: 314848,
  outputTriangles: 109818,
  previewTriangles: 96640,
  acceptedAsset: false,
  semanticReviewComplete: false,
  note: "Exact tracked STEP-derived geometry; installed Dropbear joint binding remains unresolved.",
});

function cloneMaterial(source, fallback) {
  if (Array.isArray(source)) return source.map((m) => cloneMaterial(m, fallback));
  const next = source?.clone?.() || new THREE.MeshStandardMaterial({ color: fallback });
  if (next.color) next.color.set(fallback);
  next.metalness = 0.52;
  next.roughness = 0.43;
  return next;
}

export class CadViewer {
  constructor(canvas, { onStatus = () => {} } = {}) {
    this.canvas = canvas;
    this.onStatus = onStatus;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#0a0a0b");
    this.scene.fog = new THREE.Fog("#0a0a0b", 0.25, 0.55);
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.0005, 5);
    this.camera.position.set(0.15, 0.11, 0.15);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.78;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);
    this.controls.minDistance = 0.055;
    this.controls.maxDistance = 0.7;

    this.root = new THREE.Group();
    this.housingGroup = new THREE.Group();
    this.outputGroup = new THREE.Group();
    this.root.add(this.housingGroup, this.outputGroup);
    this.scene.add(this.root);
    this.wireframe = true;
    this.exploded = false;
    this.outputAngle = 0;
    this.ready = false;
    this.active = false;
    this.lastDrawAt = 0;

    this._buildStage();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.resize();
    this._animate();
    this.load();
  }

  _buildStage() {
    this.scene.add(new THREE.HemisphereLight("#ececec", "#111113", 1.35));
    const key = new THREE.DirectionalLight("#ffffff", 2.1);
    key.position.set(0.12, 0.18, 0.15);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    this.scene.add(key);
    const rim = new THREE.PointLight("#facc15", 1.35, 0.45);
    rim.position.set(-0.13, 0.08, -0.11);
    this.scene.add(rim);
    const fill = new THREE.PointLight("#ececec", 1.2, 0.45);
    fill.position.set(0.13, -0.02, 0.08);
    this.scene.add(fill);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(0.19, 96),
      new THREE.MeshStandardMaterial({ color: "#0d0d0f", roughness: 0.9, metalness: 0.12 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.065;
    floor.receiveShadow = true;
    this.scene.add(floor);
    const grid = new THREE.GridHelper(0.34, 34, "#3a3a42", "#17171a");
    grid.position.y = -0.064;
    this.scene.add(grid);
  }

  async load() {
    const loader = new GLTFLoader();
    this.onStatus("Loading exact STEP-derived housing…", "loading");
    try {
      const [housing, output] = await Promise.all([
        loader.loadAsync(`${PREVIEW_ROOT}/housing-step-preview.glb`),
        loader.loadAsync(`${PREVIEW_ROOT}/output-step-preview.glb`),
      ]);
      this._prepare(housing.scene, this.housingGroup, "#48545f", "housing");
      this._prepare(output.scene, this.outputGroup, "#b77a19", "output");
      this.ready = true;
      this._applyOutputPose();
      this.fit();
      this.onStatus("STEP-derived preview loaded · 96,640 triangles", "ok");
    } catch (error) {
      this.onStatus(`CAD load failed: ${error.message}`, "error");
    }
  }

  _prepare(scene, parent, fallbackColor, role) {
    // Snapshot source meshes before adding child overlays. Mutating the scene
    // during traverse would cause each overlay mesh to receive another overlay.
    const meshes = [];
    scene.traverse((node) => {
      if (node.isMesh && node.name !== "technical-line-overlay") meshes.push(node);
    });
    for (const node of meshes) {
      node.material = cloneMaterial(node.material, fallbackColor);
      node.castShadow = true;
      node.receiveShadow = true;
      node.userData.role = role;

      // Share the original geometry for a cheap technical-line overlay.
      const overlay = new THREE.Mesh(
        node.geometry,
        new THREE.MeshBasicMaterial({
          color: role === "housing" ? "#d7e3ef" : "#ffd375",
          wireframe: true,
          transparent: true,
          opacity: this.wireframe ? 0.085 : 0,
          depthWrite: false,
        }),
      );
      overlay.name = "technical-line-overlay";
      overlay.renderOrder = 3;
      node.add(overlay);
    }
    parent.add(scene);
  }

  setJointAngle(degrees) {
    this.outputAngle = Number(degrees) || 0;
    this._applyOutputPose();
  }

  setActive(on) {
    this.active = Boolean(on);
    if (this.active) this.resize();
  }

  setWireframe(on) {
    this.wireframe = Boolean(on);
    this.root.traverse((node) => {
      if (node.name === "technical-line-overlay") node.material.opacity = this.wireframe ? 0.085 : 0;
    });
  }

  setExploded(on) {
    this.exploded = Boolean(on);
    this._applyOutputPose();
  }

  setHousingVisible(on) {
    this.housingGroup.visible = Boolean(on);
  }

  setOutputVisible(on) {
    this.outputGroup.visible = Boolean(on);
  }

  _applyOutputPose() {
    this.outputGroup.rotation.z = THREE.MathUtils.degToRad(this.outputAngle - 180);
    this.outputGroup.position.z = this.exploded ? 0.055 : 0;
  }

  fit() {
    if (!this.ready) return;
    const box = new THREE.Box3().setFromObject(this.root);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const radius = Math.max(sphere.radius, 0.035);
    this.controls.target.copy(sphere.center);
    this.camera.position.copy(sphere.center).add(new THREE.Vector3(radius * 2.65, radius * 1.95, radius * 2.7));
    this.camera.near = radius / 100;
    this.camera.far = radius * 30;
    this.camera.updateProjectionMatrix();
  }

  resize() {
    const parent = this.canvas.parentElement;
    const width = Math.max(320, parent.clientWidth);
    const height = Math.max(320, parent.clientHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  }

  _animate() {
    this.animationFrame = requestAnimationFrame(() => this._animate());
    if (!this.active) return;
    const now = performance.now();
    if (now - this.lastDrawAt < 66) return;
    this.lastDrawAt = now;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
