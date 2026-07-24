import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CONTROLLER_PINS } from "./dropbear.js";

const ROW_A = ["EN", 36, 39, 34, 35, 32, 33, 25, 26, 27, 14, 12, 13, "GND", "VIN"];
const ROW_B = [23, 22, 1, 3, 21, 19, 18, 5, 17, 16, 4, 2, 15, "GND", "3V3"];

const BUS_TARGETS = {
  CAN: new THREE.Vector3(36, 5, -22),
  SPI: new THREE.Vector3(36, 4, -14),
  I2C: new THREE.Vector3(-36, 5, -18),
  ADC: new THREE.Vector3(-39, 4, 0),
  HX711: new THREE.Vector3(-34, 5, 21),
  UART: new THREE.Vector3(35, 5, 19),
};

function material(color, metalness = 0.1, roughness = 0.65) {
  return new THREE.MeshStandardMaterial({ color, metalness, roughness });
}

function addBox(parent, size, position, color, options = {}) {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(...size),
    material(color, options.metalness, options.roughness),
  );
  mesh.position.set(...position);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function pinX(index) {
  return -17.78 + index * 2.54;
}

export class Board3D {
  constructor(canvas, { onPin = () => {} } = {}) {
    this.canvas = canvas;
    this.onPin = onPin;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#0a0a0b");
    this.scene.fog = new THREE.Fog("#0a0a0b", 100, 190);
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.1, 500);
    this.camera.position.set(72, 60, 78);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);
    this.controls.minDistance = 46;
    this.controls.maxDistance = 180;
    this.controls.maxPolarAngle = Math.PI * 0.49;

    this.root = new THREE.Group();
    this.scene.add(this.root);
    this.pinMeshes = new Map();
    this.signalLines = [];
    this.active = false;
    this.activity = { running: true, playMode: false, time: 0 };
    this._pointer = new THREE.Vector2();
    this._raycaster = new THREE.Raycaster();

    this._buildLights();
    this._buildBoard();
    this._buildHarness();
    this._buildDimensionFrame();

    canvas.addEventListener("pointerdown", (event) => this._pick(event));
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.resize();
    this._animate();
  }

  _buildLights() {
    this.scene.add(new THREE.HemisphereLight("#ececec", "#111113", 2.1));
    const key = new THREE.DirectionalLight("#ffffff", 3);
    key.position.set(35, 70, 45);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    this.scene.add(key);
    const rim = new THREE.PointLight("#facc15", 42, 130);
    rim.position.set(-45, 18, -35);
    this.scene.add(rim);
  }

  _buildBoard() {
    // Nominal 30-pin ESP32 DevKit V1 envelope in millimetres.
    const pcb = addBox(this.root, [51.5, 1.6, 28.5], [0, 0, 0], "#0f5e43", { roughness: 0.72 });
    pcb.userData = { component: "PCB", detail: "51.5 × 28.5 × 1.6 mm nominal DevKit V1 reference envelope" };

    // ESP-WROOM module, antenna keepout, USB, regulator, bridge and buttons.
    addBox(this.root, [25.5, 3.2, 18], [-10.2, 2.4, 0], "#b7bdc4", { metalness: 0.72, roughness: 0.3 });
    addBox(this.root, [6.8, 1.1, 16.5], [-19.1, 4.05, 0], "#d7dadd", { metalness: 0.55, roughness: 0.35 });
    for (let i = 0; i < 6; i += 1) {
      const z = -6.2 + i * 2.45;
      const trace = addBox(this.root, [5.0 - Math.abs(i - 2.5) * 0.34, 0.12, 0.33], [-20, 4.65, z], "#8d7550", { metalness: 0.7 });
      trace.rotation.y = (i % 2 ? 1 : -1) * 0.08;
    }
    addBox(this.root, [7.8, 4.2, 8.2], [25.2, 2.1, 0], "#aeb6c0", { metalness: 0.82, roughness: 0.2 });
    addBox(this.root, [5.2, 1.6, 4.6], [15.1, 1.65, 0], "#171a1f");
    addBox(this.root, [5.5, 1.7, 4.4], [7.7, 1.65, 0], "#181b20");
    addBox(this.root, [3.8, 2.2, 4.6], [19.2, 1.9, -8.6], "#11151b");
    addBox(this.root, [3.8, 2.2, 4.6], [19.2, 1.9, 8.6], "#11151b");

    const led = new THREE.Mesh(new THREE.SphereGeometry(1.05, 20, 12), material("#34d399", 0, 0.25));
    led.position.set(12, 2.25, -9.5);
    led.name = "power-led";
    this.root.add(led);
    this.powerLed = led;

    const createRow = (row, z) => row.forEach((gpio, index) => {
      const x = pinX(index);
      const pin = addBox(this.root, [1.1, 6.2, 1.1], [x, 1.65, z], "#d5a92a", { metalness: 0.72, roughness: 0.3 });
      const known = typeof gpio === "number" ? CONTROLLER_PINS.find((p) => p.gpio === gpio) : null;
      pin.userData = {
        gpio,
        component: `GPIO ${gpio}`,
        detail: known ? `${known.bus} · ${known.role}` : "Unused by observed Dropbear firmware",
        pin: known || null,
      };
      if (known) {
        pin.material = material(known.color, 0.48, 0.3);
        this.pinMeshes.set(gpio, pin);
      }
    });
    createRow(ROW_A, -12.25);
    createRow(ROW_B, 12.25);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(180, 120),
      new THREE.MeshStandardMaterial({ color: "#0a0a0b", roughness: 0.92, metalness: 0.05 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -4.3;
    floor.receiveShadow = true;
    this.scene.add(floor);
    const grid = new THREE.GridHelper(170, 34, "#3a3a42", "#17171a");
    grid.position.y = -4.15;
    this.scene.add(grid);
  }

  _buildHarness() {
    for (const pinDef of CONTROLLER_PINS) {
      const pin = this.pinMeshes.get(pinDef.gpio);
      const target = BUS_TARGETS[pinDef.bus];
      if (!pin || !target) continue;
      const start = pin.position.clone();
      start.y = 5.0;
      const end = target.clone();
      end.z += (pinDef.gpio % 5 - 2) * 1.15;
      const mid = new THREE.Vector3(
        (start.x + end.x) / 2,
        9 + (pinDef.gpio % 4),
        start.z + (end.z - start.z) * 0.55,
      );
      const curve = new THREE.CatmullRomCurve3([start, mid, end]);
      const points = curve.getPoints(44);
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: pinDef.color,
        transparent: true,
        opacity: pinDef.optional ? 0.3 : 0.72,
      });
      const line = new THREE.Line(geometry, lineMaterial);
      this.root.add(line);

      const pulse = new THREE.Mesh(
        new THREE.SphereGeometry(0.72, 12, 8),
        new THREE.MeshBasicMaterial({ color: pinDef.color }),
      );
      this.root.add(pulse);
      this.signalLines.push({ pinDef, line, pulse, curve, phase: (pinDef.gpio * 0.17) % 1 });
    }

    const targets = [
      ["MCP2515 / CAN 1 Mbps", BUS_TARGETS.CAN, "#22d3ee"],
      ["SPI transport", BUS_TARGETS.SPI, "#38bdf8"],
      ["5 × AS5600 analog", BUS_TARGETS.ADC, "#fbbf24"],
      ["5 × IMU / I²C", BUS_TARGETS.I2C, "#34d399"],
      ["4 × HX711 (optional)", BUS_TARGETS.HX711, "#fb7185"],
      ["USB serial 115200", BUS_TARGETS.UART, "#a78bfa"],
    ];
    for (const [name, position, color] of targets) {
      const node = addBox(this.root, [9.4, 3, 6.2], [position.x, 1.5, position.z], color, { metalness: 0.22, roughness: 0.55 });
      node.userData = { component: name, detail: "Dropbear firmware signal endpoint" };
    }
  }

  _buildDimensionFrame() {
    const dimensionMaterial = new THREE.LineBasicMaterial({ color: "#718096", transparent: true, opacity: 0.65 });
    const line = (a, b) => {
      const geometry = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a), new THREE.Vector3(...b)]);
      this.root.add(new THREE.Line(geometry, dimensionMaterial));
    };
    line([-25.75, -2.3, 17.2], [25.75, -2.3, 17.2]);
    line([-25.75, -2.3, 15.5], [-25.75, -2.3, 18.9]);
    line([25.75, -2.3, 15.5], [25.75, -2.3, 18.9]);
    line([-29.1, -2.3, -14.25], [-29.1, -2.3, 14.25]);
    line([-30.8, -2.3, -14.25], [-27.4, -2.3, -14.25]);
    line([-30.8, -2.3, 14.25], [-27.4, -2.3, 14.25]);
  }

  setActivity(activity) {
    this.activity = { ...this.activity, ...activity };
  }

  setActive(on) {
    this.active = Boolean(on);
    if (this.active) this.resize();
  }

  focusPin(gpio) {
    const pin = this.pinMeshes.get(Number(gpio));
    if (!pin) return;
    this.controls.target.copy(pin.position);
    this.camera.position.set(pin.position.x + 23, 28, pin.position.z + 30);
  }

  resetView() {
    this.controls.target.set(0, 0, 0);
    this.camera.position.set(72, 60, 78);
  }

  _pick(event) {
    const bounds = this.canvas.getBoundingClientRect();
    this._pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
    this._pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
    this._raycaster.setFromCamera(this._pointer, this.camera);
    const hits = this._raycaster.intersectObjects(this.root.children, false);
    const hit = hits.find((entry) => entry.object.userData?.component);
    if (hit) this.onPin(hit.object.userData);
  }

  resize() {
    const parent = this.canvas.parentElement;
    const width = Math.max(320, parent.clientWidth);
    const height = Math.max(300, parent.clientHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  }

  _animate() {
    this.animationFrame = requestAnimationFrame(() => this._animate());
    if (!this.active) return;
    const now = performance.now() / 1000;
    const active = this.activity.running;
    const motion = this.activity.playMode;
    for (const item of this.signalLines) {
      const optionalOff = item.pinDef.optional && !this.activity.loadCellsEnabled;
      item.line.material.opacity = optionalOff ? 0.12 : motion ? 0.95 : 0.48;
      item.pulse.visible = active && !optionalOff;
      const rate = item.pinDef.bus === "ADC" ? 1.8 : item.pinDef.bus === "CAN" ? 3.7 : 1.1;
      const t = (now * rate + item.phase) % 1;
      item.pulse.position.copy(item.curve.getPoint(t));
      item.pulse.scale.setScalar(motion ? 1.15 : 0.7);
    }
    if (this.powerLed) {
      const glow = active ? 1 + Math.sin(now * 4) * 0.12 : 0.35;
      this.powerLed.scale.setScalar(glow);
      this.powerLed.material.emissive = new THREE.Color(active ? "#0f9f67" : "#08150f");
      this.powerLed.material.emissiveIntensity = active ? 1.6 : 0.1;
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
