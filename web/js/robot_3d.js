import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  DROPBEAR_USD_BINDINGS,
  DROPBEAR_USD_SOURCE,
  dropbearUsdBinding,
} from "./dropbear_usd.js";

const ROBOT_ROOT = "/assets/robot";
const AXES = Object.freeze({
  X: new THREE.Vector3(1, 0, 0),
  Y: new THREE.Vector3(0, 1, 0),
  Z: new THREE.Vector3(0, 0, 1),
});

function quaternionFromUsd([w, x, y, z]) {
  return new THREE.Quaternion(x, y, z, w).normalize();
}

function jointAxis(joint, reverse = false) {
  // The mirrored right outer X8 is authored as X in this USD revision while
  // the same physical shaft and the other three calf drivers are Z. Using the
  // mirrored Z basis is required for its crank/rod/ankle contacts to close.
  const authoredAxis = joint.name === "RL_Revolute81" ? "Z" : joint.axis;
  const basis = AXES[authoredAxis] || AXES.X;
  const rotation = quaternionFromUsd(reverse ? joint.localRot1 : joint.localRot0);
  return basis.clone().applyQuaternion(rotation).normalize();
}

function jointDeltaMatrix(joint, radians) {
  const reverse = Boolean(joint.reverse);
  const anchor = new THREE.Vector3(...(reverse ? joint.localPos1 : joint.localPos0));
  const axis = jointAxis(joint, reverse);
  const rotation = new THREE.Matrix4().makeRotationAxis(axis, reverse ? -radians : radians);
  return new THREE.Matrix4()
    .makeTranslation(anchor.x, anchor.y, anchor.z)
    .multiply(rotation)
    .multiply(new THREE.Matrix4().makeTranslation(-anchor.x, -anchor.y, -anchor.z));
}

function normalizeMaterials(mesh) {
  const source = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  const materials = source.map((material) => {
    const next = material.clone();
    if ("metalness" in next) next.metalness = Math.min(0.72, Math.max(0.18, next.metalness ?? 0.3));
    if ("roughness" in next) next.roughness = Math.min(0.78, Math.max(0.26, next.roughness ?? 0.5));
    if ("emissive" in next) next.emissive.set("#000000");
    next.side = THREE.FrontSide;
    return next;
  });
  mesh.material = Array.isArray(mesh.material) ? materials : materials[0];
  mesh.userData.baseMaterials = materials.map((material) => ({
    emissive: material.emissive?.clone?.(),
    emissiveIntensity: material.emissiveIntensity,
  }));
}

function solveSymmetric(matrix, vector) {
  const size = vector.length;
  const augmented = matrix.map((row, index) => [...row, vector[index]]);
  for (let pivot = 0; pivot < size; pivot += 1) {
    let best = pivot;
    for (let row = pivot + 1; row < size; row += 1) {
      if (Math.abs(augmented[row][pivot]) > Math.abs(augmented[best][pivot])) best = row;
    }
    [augmented[pivot], augmented[best]] = [augmented[best], augmented[pivot]];
    const divisor = augmented[pivot][pivot];
    if (Math.abs(divisor) < 1e-10) continue;
    for (let column = pivot; column <= size; column += 1) augmented[pivot][column] /= divisor;
    for (let row = 0; row < size; row += 1) {
      if (row === pivot) continue;
      const factor = augmented[row][pivot];
      for (let column = pivot; column <= size; column += 1) {
        augmented[row][column] -= factor * augmented[pivot][column];
      }
    }
  }
  return augmented.map((row) => row[size]);
}

export class Robot3D {
  constructor(canvas, { onJoint = () => {}, onStatus = () => {} } = {}) {
    this.canvas = canvas;
    this.onJoint = onJoint;
    this.onStatus = onStatus;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#080809");
    this.scene.fog = new THREE.Fog("#0a0a0b", 3.4, 8.5);
    this.camera = new THREE.PerspectiveCamera(31, 1, 0.005, 30);
    this.camera.up.set(0, 0, 1);
    this.camera.position.set(2.6, -3.7, 2.4);

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
      preserveDrawingBuffer: true,
    });
    this.resolutionScale = 1;
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.7));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.92;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.target.set(0, 0, 0.95);
    this.controls.minDistance = 0.65;
    this.controls.maxDistance = 8;

    this.root = new THREE.Group();
    this.root.name = "dropbear-usd-articulation";
    this.scene.add(this.root);
    this.bodyGroups = new Map();
    this.initialMatrices = new Map();
    this.currentMatrices = new Map();
    this.relativeMatrices = new Map();
    this.bodyMeshes = new Map();
    this.bindingMarkers = new Map();
    this.bindingByBody = new Map();
    this.raycastMeshes = [];
    this.manifest = null;
    this.ready = false;
    this.active = true;
    this.selectedCanId = 0x141;
    this.poseVersion = 0;
    this.lastDrawAt = 0;
    this.pendingJoints = [];
    this.passiveAngles = new Map();
    this.closureResidualMm = 0;

    this._buildStage();
    this._bindPicking();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.resize();
    this._animate();
    this.load();
  }

  _buildStage() {
    this.scene.add(new THREE.HemisphereLight("#ececec", "#111113", 1.65));
    const key = new THREE.DirectionalLight("#ffffff", 3.0);
    key.position.set(-2.5, -3.2, 5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.near = 0.1;
    key.shadow.camera.far = 12;
    key.shadow.camera.left = -2.2;
    key.shadow.camera.right = 2.2;
    key.shadow.camera.top = 2.2;
    key.shadow.camera.bottom = -2.2;
    this.scene.add(key);
    const cyan = new THREE.PointLight("#ececec", 6, 4.5);
    cyan.position.set(-1.25, -0.8, 1.35);
    this.scene.add(cyan);
    const amber = new THREE.PointLight("#facc15", 7, 4.5);
    amber.position.set(1.35, 0.6, 1.15);
    this.scene.add(amber);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(3.4, 96),
      new THREE.MeshStandardMaterial({ color: "#0a0a0b", roughness: 0.96, metalness: 0.04 }),
    );
    floor.position.z = -0.012;
    floor.receiveShadow = true;
    this.scene.add(floor);
    const grid = new THREE.GridHelper(6.8, 48, "#3a3a42", "#17171a");
    grid.rotation.x = Math.PI / 2;
    grid.position.z = -0.006;
    grid.material.opacity = 0.48;
    grid.material.transparent = true;
    this.scene.add(grid);

    const axis = new THREE.AxesHelper(0.32);
    axis.position.set(-1.05, 0.75, 0.03);
    this.scene.add(axis);
  }

  async load() {
    this.onStatus("Loading Dropbear USD body cache…", "loading");
    try {
      const [manifestResponse, gltf] = await Promise.all([
        fetch(`${ROBOT_ROOT}/dropbear-articulation.json`),
        new GLTFLoader().loadAsync(`${ROBOT_ROOT}/dropbear-usd-browser.glb`),
      ]);
      if (!manifestResponse.ok) throw new Error(`articulation manifest HTTP ${manifestResponse.status}`);
      this.manifest = await manifestResponse.json();
      this._validateManifest();
      this._buildBodies(gltf.scene);
      this._buildKinematicGraph();
      this._buildJointMarkers();
      this.setJointStates(this.pendingJoints, this.selectedCanId);
      this.fit();
      if (this.renderer.compileAsync) await this.renderer.compileAsync(this.scene, this.camera);
      this.renderer.render(this.scene, this.camera);
      this.ready = true;
      const stats = this.manifest.statistics;
      this.onStatus(`USD loaded · ${stats.renderedBodies} bodies · ${stats.browserTriangles.toLocaleString()} triangles`, "ok");
    } catch (error) {
      console.error(error);
      this.onStatus(`USD load failed: ${error.message}`, "error");
    }
  }

  _validateManifest() {
    if (this.manifest.source.commit !== DROPBEAR_USD_SOURCE.commit) throw new Error("USD revision mismatch");
    if (this.manifest.canBindings.length !== 12) throw new Error("expected 12 CAN/USD bindings");
    for (const expected of DROPBEAR_USD_BINDINGS) {
      const actual = this.manifest.canBindings.find((binding) => binding.canIdNumber === expected.canId);
      if (!actual || actual.usdJoint !== expected.usdJoint) throw new Error(`binding mismatch at ${expected.canLabel}`);
    }
  }

  _buildBodies(gltfScene) {
    gltfScene.updateMatrixWorld(true);
    const prefixes = [...this.manifest.bodies].sort((a, b) => b.meshNodePrefix.length - a.meshNodePrefix.length);

    for (const body of this.manifest.bodies) {
      const matrix = new THREE.Matrix4().fromArray(body.matrix);
      const group = new THREE.Group();
      group.name = `USD_BODY:${body.path}`;
      group.matrixAutoUpdate = false;
      group.matrix.copy(matrix);
      this.root.add(group);
      this.bodyGroups.set(body.path, group);
      this.initialMatrices.set(body.path, matrix.clone());
      this.currentMatrices.set(body.path, matrix.clone());
      this.bodyMeshes.set(body.path, []);
    }

    const meshes = [];
    gltfScene.traverse((node) => {
      if (node.isMesh) meshes.push(node);
    });
    for (const mesh of meshes) {
      const body = prefixes.find((candidate) => mesh.name.startsWith(candidate.meshNodePrefix));
      if (!body) continue;
      mesh.updateMatrix();
      const bodyInitial = this.initialMatrices.get(body.path);
      const local = bodyInitial.clone().invert().multiply(mesh.matrix.clone());
      mesh.removeFromParent();
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(local);
      normalizeMaterials(mesh);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.userData.bodyPath = body.path;
      this.bodyGroups.get(body.path).add(mesh);
      this.bodyMeshes.get(body.path).push(mesh);
      this.raycastMeshes.push(mesh);
    }

    for (const binding of this.manifest.canBindings) {
      this.bindingByBody.set(binding.body1, binding.canIdNumber);
      if (!this.bindingByBody.has(binding.body0)) this.bindingByBody.set(binding.body0, binding.canIdNumber);
    }
    for (const [bodyPath, canId] of this.bindingByBody) {
      for (const mesh of this.bodyMeshes.get(bodyPath) || []) mesh.userData.canId = canId;
    }
  }

  _buildKinematicGraph() {
    this.treeJoints = this.manifest.joints.filter((joint) => joint.tree);
    this.treeChildren = new Map();
    for (const joint of this.treeJoints) {
      if (!this.initialMatrices.has(joint.parent) || !this.initialMatrices.has(joint.child)) continue;
      const siblings = this.treeChildren.get(joint.parent) || [];
      siblings.push(joint);
      this.treeChildren.set(joint.parent, siblings);
      const relative = this.initialMatrices.get(joint.parent).clone().invert().multiply(this.initialMatrices.get(joint.child));
      this.relativeMatrices.set(joint.path, relative);
    }
    this.jointByName = new Map(this.manifest.joints.map((joint) => [joint.name, joint]));
    this.bindingByCan = new Map(this.manifest.canBindings.map((binding) => [binding.canIdNumber, binding]));
    this.treeRoots = this.manifest.bodies
      .map((body) => body.path)
      .filter((path) => !this.treeJoints.some((joint) => joint.child === path));
    this.legClosures = new Map(["LL_", "RL_"].map((side) => [
      side,
      this.manifest.joints.filter((joint) => joint.closure && joint.name.startsWith(side)),
    ]));
    const passiveNames = [
      "Revolute33", "Revolute46", "Revolute47", "Revolute57",
      "Revolute112", "Revolute111", "Revolute87", "Revolute88",
      "Revolute48", "Revolute49", "Revolute37",
    ];
    this.legPassiveJoints = new Map(["LL_", "RL_"].map((side) => [
      side,
      passiveNames.map((name) => this.jointByName.get(`${side}${name}`)).filter(Boolean),
    ]));
  }

  _buildJointMarkers() {
    const sphereGeometry = new THREE.SphereGeometry(0.018, 18, 12);
    const ringGeometry = new THREE.RingGeometry(0.027, 0.033, 40);
    for (const binding of this.manifest.canBindings) {
      const joint = this.manifest.joints.find((candidate) => candidate.name === binding.usdJoint);
      const isClosure = Boolean(joint?.closure);
      const color = binding.side === "left" ? "#facc15" : "#ececec";
      const group = new THREE.Group();
      group.userData.canId = binding.canIdNumber;
      const sphere = new THREE.Mesh(
        sphereGeometry,
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.78, depthTest: false }),
      );
      sphere.renderOrder = 8;
      sphere.userData.canId = binding.canIdNumber;
      const ring = new THREE.Mesh(
        ringGeometry,
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: isClosure ? 0.95 : 0.55, side: THREE.DoubleSide, depthTest: false }),
      );
      ring.renderOrder = 8;
      ring.userData.canId = binding.canIdNumber;
      group.add(sphere, ring);
      this.root.add(group);
      this.bindingMarkers.set(binding.canIdNumber, { group, sphere, ring, binding: { ...binding, closure: isClosure } });
      this.raycastMeshes.push(sphere, ring);
    }
  }

  setJointStates(joints, selectedCanId = this.selectedCanId) {
    this.pendingJoints = joints || [];
    this.selectedCanId = Number(selectedCanId);
    if (!this.manifest || !this.bodyGroups.size) return;
    const radiansByUsdJoint = new Map();
    for (const state of this.pendingJoints) {
      const binding = this.bindingByCan.get(state.id);
      if (binding) radiansByUsdJoint.set(binding.usdJoint, THREE.MathUtils.degToRad(state.angle - 180));
    }
    this._solveLegClosures(radiansByUsdJoint);
    this.currentMatrices = this._calculateMatrices(radiansByUsdJoint);
    for (const [path, group] of this.bodyGroups) group.matrix.copy(this.currentMatrices.get(path));

    this._updateMarkers(radiansByUsdJoint);
    this._updateHighlight();
    this.poseVersion += 1;
  }

  _calculateMatrices(commandedAngles) {
    const matrices = new Map([...this.initialMatrices].map(([path, matrix]) => [path, matrix.clone()]));
    const visit = (parentPath) => {
      const parentMatrix = matrices.get(parentPath) || this.initialMatrices.get(parentPath);
      for (const joint of this.treeChildren.get(parentPath) || []) {
        const radians = commandedAngles.get(joint.name) ?? this.passiveAngles.get(joint.name) ?? 0;
        const next = parentMatrix.clone()
          .multiply(Math.abs(radians) > 1e-12 ? jointDeltaMatrix(joint, radians) : new THREE.Matrix4())
          .multiply(this.relativeMatrices.get(joint.path));
        matrices.set(joint.child, next);
        visit(joint.child);
      }
    };
    for (const root of this.treeRoots) visit(root);
    return matrices;
  }

  _closureVector(side, matrices, weighted = false) {
    const residual = [];
    for (const joint of this.legClosures.get(side) || []) {
      const body0 = matrices.get(joint.body0);
      const body1 = matrices.get(joint.body1);
      if (!body0 || !body1) continue;
      const point0 = new THREE.Vector3(...joint.localPos0).applyMatrix4(body0);
      const point1 = new THREE.Vector3(...joint.localPos1).applyMatrix4(body1);
      const isCalfRodContact = joint.name.endsWith("Revolute115") || joint.name.endsWith("Revolute117");
      const weight = weighted && isCalfRodContact ? 5 : 1;
      residual.push(
        (point0.x - point1.x) * weight,
        (point0.y - point1.y) * weight,
        (point0.z - point1.z) * weight,
      );
    }
    return residual;
  }

  _solveLegClosures(commandedAngles) {
    const epsilon = 1e-4;
    let worst = 0;
    for (const side of ["LL_", "RL_"]) {
      const variables = this.legPassiveJoints.get(side) || [];
      if (!variables.length) continue;
      for (const joint of variables) {
        if (!this.passiveAngles.has(joint.name)) this.passiveAngles.set(joint.name, 0);
      }
      for (let iteration = 0; iteration < 10; iteration += 1) {
        const base = this._closureVector(side, this._calculateMatrices(commandedAngles), true);
        const baseNorm = Math.sqrt(base.reduce((sum, value) => sum + value * value, 0));
        if (baseNorm < 2e-5) break;
        const jacobian = Array.from({ length: base.length }, () => Array(variables.length).fill(0));
        variables.forEach((joint, column) => {
          const before = this.passiveAngles.get(joint.name) || 0;
          this.passiveAngles.set(joint.name, before + epsilon);
          const shifted = this._closureVector(side, this._calculateMatrices(commandedAngles), true);
          this.passiveAngles.set(joint.name, before);
          for (let row = 0; row < base.length; row += 1) {
            jacobian[row][column] = (shifted[row] - base[row]) / epsilon;
          }
        });
        const normal = Array.from({ length: variables.length }, () => Array(variables.length).fill(0));
        const rhs = Array(variables.length).fill(0);
        for (let column = 0; column < variables.length; column += 1) {
          for (let row = 0; row < base.length; row += 1) rhs[column] -= jacobian[row][column] * base[row];
          for (let other = 0; other < variables.length; other += 1) {
            for (let row = 0; row < base.length; row += 1) {
              normal[column][other] += jacobian[row][column] * jacobian[row][other];
            }
          }
          normal[column][column] += 2e-6;
        }
        const delta = solveSymmetric(normal, rhs);
        const before = variables.map((joint) => this.passiveAngles.get(joint.name) || 0);
        let accepted = false;
        for (const scale of [1, 0.5, 0.25, 0.125]) {
          variables.forEach((joint, index) => {
            const raw = Number.isFinite(delta[index]) ? delta[index] : 0;
            const step = Math.max(-0.28, Math.min(0.28, raw * scale));
            this.passiveAngles.set(joint.name, before[index] + step);
          });
          const trial = this._closureVector(side, this._calculateMatrices(commandedAngles), true);
          const trialNorm = Math.sqrt(trial.reduce((sum, value) => sum + value * value, 0));
          if (trialNorm < baseNorm) {
            accepted = true;
            break;
          }
        }
        if (!accepted) {
          variables.forEach((joint, index) => this.passiveAngles.set(joint.name, before[index]));
          break;
        }
      }
      const residual = this._closureVector(side, this._calculateMatrices(commandedAngles));
      for (let index = 0; index < residual.length; index += 3) {
        worst = Math.max(worst, Math.hypot(residual[index], residual[index + 1], residual[index + 2]));
      }
    }
    this.closureResidualMm = worst * 1000;
  }

  _updateMarkers(radiansByUsdJoint) {
    for (const { group, sphere, ring, binding } of this.bindingMarkers.values()) {
      const joint = this.jointByName.get(binding.usdJoint);
      const bodyMatrix = this.currentMatrices.get(joint.body0) || this.initialMatrices.get(joint.body0);
      if (!joint || !bodyMatrix) continue;
      const anchor = new THREE.Vector3(...joint.localPos0).applyMatrix4(bodyMatrix);
      const bodyRotation = new THREE.Quaternion().setFromRotationMatrix(bodyMatrix);
      const axis = jointAxis(joint).applyQuaternion(bodyRotation).normalize();
      group.position.copy(anchor);
      ring.quaternion.setFromUnitVectors(AXES.Z, axis);
      const selected = binding.canIdNumber === this.selectedCanId;
      group.scale.setScalar(selected ? 1.75 : 1);
      sphere.material.opacity = selected ? 1 : 0.7;
      ring.material.opacity = selected ? 1 : binding.closure ? 0.88 : 0.42;
      ring.rotation.z = radiansByUsdJoint.get(binding.usdJoint) || 0;
    }
  }

  _updateHighlight() {
    for (const [bodyPath, meshes] of this.bodyMeshes) {
      const active = this.bindingByBody.get(bodyPath) === this.selectedCanId;
      for (const mesh of meshes) {
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        materials.forEach((material, index) => {
          if (!material.emissive) return;
          const base = mesh.userData.baseMaterials[index];
          material.emissive.copy(base.emissive);
          material.emissiveIntensity = base.emissiveIntensity;
          if (active) {
            material.emissive.set(dropbearUsdBinding(this.selectedCanId)?.side === "left" ? "#6f5b00" : "#626268");
            material.emissiveIntensity = 0.46;
          }
        });
      }
    }
  }

  _bindPicking() {
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.canvas.addEventListener("pointerup", (event) => {
      if (!this.ready || event.button !== 0) return;
      const rect = this.canvas.getBoundingClientRect();
      this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      this.raycaster.setFromCamera(this.pointer, this.camera);
      const hit = this.raycaster.intersectObjects(this.raycastMeshes, false)
        .find((entry) => entry.object.userData.canId);
      if (hit) this.onJoint(hit.object.userData.canId);
    });
  }

  bindingForCan(canId) {
    return this.bindingByCan?.get(Number(canId)) || dropbearUsdBinding(canId);
  }

  setActive(on) {
    this.active = Boolean(on);
    if (this.active) this.resize();
  }

  fit() {
    if (!this.bodyGroups.size) return;
    const box = new THREE.Box3().setFromObject(this.root);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const radius = Math.max(0.6, sphere.radius);
    this.controls.target.copy(sphere.center).add(new THREE.Vector3(0, 0, radius * 0.1));
    this.camera.position.copy(sphere.center).add(new THREE.Vector3(radius * 2.4, -radius * 3.15, radius * 1.4));
    this.camera.near = radius / 120;
    this.camera.far = radius * 25;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  resize() {
    const parent = this.canvas.parentElement;
    const width = Math.max(320, parent.clientWidth);
    const height = Math.max(360, parent.clientHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(Math.min(devicePixelRatio * this.resolutionScale, 3));
    this.renderer.setSize(width, height, false);
  }

  setResolutionScale(scale) {
    this.resolutionScale = Math.max(0.5, Math.min(2, Number(scale) || 1));
    this.resize();
    this.renderer.render(this.scene, this.camera);
  }

  _animate() {
    requestAnimationFrame(() => this._animate());
    if (!this.active) return;
    const now = performance.now();
    if (now - this.lastDrawAt < 34) return;
    this.lastDrawAt = now;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
