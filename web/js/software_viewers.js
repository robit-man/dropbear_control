const SIDES = ["left", "right"];

function emptyFoot() {
  return {
    contact: false,
    heelContact: false,
    toeContact: false,
    footHeightMm: 0,
    heelHeightMm: 0,
    toeHeightMm: 0,
    loadKg: 0,
    heelLoadKg: 0,
    toeLoadKg: 0,
  };
}

function prepareCanvas(canvas) {
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D is unavailable");
  const parent = canvas.parentElement;
  const width = Math.max(480, parent?.clientWidth || canvas.clientWidth || 900);
  const height = Math.max(420, parent?.clientHeight || canvas.clientHeight || 650);
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

export function supportsWebGL2() {
  try {
    const probe = document.createElement("canvas");
    const context = probe.getContext("webgl2", {
      alpha: false,
      antialias: false,
      failIfMajorPerformanceCaveat: false,
    });
    context?.getExtension("WEBGL_lose_context")?.loseContext();
    return Boolean(context);
  } catch (_error) {
    return false;
  }
}

export class SoftwarePanelViewer {
  constructor(canvas, { title = "ENGINEERING VIEW", onStatus = () => {} } = {}) {
    this.canvas = canvas;
    this.title = title;
    this.active = false;
    this.value = "";
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    onStatus("2D fallback · WebGL unavailable", "warn");
    this.resize();
  }

  _draw() {
    const { context, width, height } = prepareCanvas(this.canvas);
    context.fillStyle = "#080809";
    context.fillRect(0, 0, width, height);
    context.strokeStyle = "#24252a";
    context.lineWidth = 1;
    for (let x = 0; x < width; x += 32) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
    }
    for (let y = 0; y < height; y += 32) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }
    context.textAlign = "center";
    context.fillStyle = "#facc15";
    context.font = '700 12px "IBM Plex Mono", monospace';
    context.fillText(this.title, width / 2, height / 2 - 12);
    context.fillStyle = "#8a929d";
    context.font = '500 10px "IBM Plex Mono", monospace';
    context.fillText("2D FALLBACK · WEBGL CONTEXT UNAVAILABLE", width / 2, height / 2 + 12);
    if (this.value) context.fillText(this.value, width / 2, height / 2 + 35);
  }

  setActive(active) { this.active = Boolean(active); }
  resize() { this._draw(); }
  fit() { this._draw(); }
  resetView() { this._draw(); }
  focusPin(gpio) { this.value = `GPIO ${gpio}`; this._draw(); }
  setActivity() {}
  setWireframe() {}
  setExploded() {}
  setHousingVisible() {}
  setOutputVisible() {}
  setModel(model) { this.value = String(model || "").toUpperCase(); this._draw(); }
  setJointAngle(angle) { this.value = `SHAFT ${Number(angle || 0).toFixed(1)}°`; this._draw(); }
}

export class SoftwareRobotViewer {
  constructor(canvas, { onStatus = () => {} } = {}) {
    this.canvas = canvas;
    this.ready = true;
    this.active = true;
    this.verticalConstraintEnabled = true;
    this.selectedCanId = 0x141;
    this.selectedArmMotorId = null;
    this.joints = [];
    this.legClosureResidualMm = 0;
    this.armClosureResidualMm = 0;
    this.closureResidualMm = 0;
    this.groundContact = {
      valid: false,
      guide: "2D_FALLBACK",
      offsetZ: 0,
      velocityZ: 0,
      normalForceN: 0,
      left: emptyFoot(),
      right: emptyFoot(),
    };
    this.legTelemetry = {
      left: { ...emptyFoot(), ankleDeg: 0, outerCalfDeg: 180, innerCalfDeg: 180 },
      right: { ...emptyFoot(), ankleDeg: 0, outerCalfDeg: 180, innerCalfDeg: 180 },
    };
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    onStatus("Live measured-state 2D fallback · WebGL unavailable", "warn");
    this.resize();
  }

  _joint(side, key) {
    return this.joints.find((joint) => joint.side === side && joint.key === key);
  }

  _drawJoint(context, x, y, joint, label, align = "left") {
    const measured = joint?.observationValid === true;
    context.textAlign = align;
    context.fillStyle = measured
      ? joint.observationModelApplied ? "#22d3ee" : "#facc15"
      : "#626a74";
    context.font = '600 10px "IBM Plex Mono", monospace';
    const value = measured
      ? joint.observationModelApplied
        ? `${Number(joint.observationZeroedDeg).toFixed(1)}° zero / ${Number(joint.observationRawDeg).toFixed(1)}° ${joint.observationPositionSource === "motor_control_aligned" ? "CAN aligned" : joint.observationPositionSource === "motor_native" ? "CAN raw" : "AS5600"}`
        : `${Number(joint.observationRawDeg).toFixed(1)}° ${joint.observationPositionSource === "motor_control_aligned" ? "CAN aligned" : joint.observationPositionSource === "motor_native" ? "CAN raw" : "AS5600"} / MODEL HELD`
      : "UNOBSERVED";
    context.fillText(`${label}  ${value}`, x, y);
  }

  _drawLeg(context, width, height, side) {
    const direction = side === "left" ? -1 : 1;
    const center = width / 2;
    const hipX = center + direction * Math.min(105, width * 0.12);
    const hipY = height * 0.37;
    const hipPitch = this._joint(side, "hip_pitch");
    const knee = this._joint(side, "knee");
    const hipRoll = this._joint(side, "hip_roll");
    const outerCalf = this._joint(side, "outer_calf");
    const innerCalf = this._joint(side, "inner_calf");
    const clampRadians = (joint, scale = 1) => {
      const degrees = Math.max(-70, Math.min(70, (Number(joint?.angle) || 180) - 180));
      return degrees * Math.PI / 180 * scale;
    };
    const upperAngle = clampRadians(hipPitch, 0.75);
    const kneeAngle = upperAngle + clampRadians(knee, 0.55);
    const upperLength = Math.min(175, height * 0.23);
    const lowerLength = Math.min(180, height * 0.24);
    const kneeX = hipX + Math.sin(upperAngle) * upperLength;
    const kneeY = hipY + Math.cos(upperAngle) * upperLength;
    const ankleX = kneeX + Math.sin(kneeAngle) * lowerLength;
    const ankleY = kneeY + Math.cos(kneeAngle) * lowerLength;
    const measured = [hipPitch, knee, hipRoll, outerCalf, innerCalf]
      .some((joint) => joint?.observationValid === true);

    context.strokeStyle = measured ? (side === "left" ? "#facc15" : "#ececec") : "#4b515a";
    context.lineWidth = 13;
    context.lineCap = "round";
    context.beginPath();
    context.moveTo(hipX, hipY);
    context.lineTo(kneeX, kneeY);
    context.lineTo(ankleX, ankleY);
    context.stroke();
    context.lineWidth = 7;
    context.beginPath();
    context.moveTo(ankleX - 28, ankleY + 5);
    context.lineTo(ankleX + 42, ankleY + 5);
    context.stroke();

    for (const [x, y] of [[hipX, hipY], [kneeX, kneeY], [ankleX, ankleY]]) {
      context.fillStyle = measured ? "#22d3ee" : "#626a74";
      context.beginPath();
      context.arc(x, y, 7, 0, Math.PI * 2);
      context.fill();
    }

    const textX = side === "left" ? 22 : width - 22;
    const align = side === "left" ? "left" : "right";
    const startY = height * 0.67;
    this._drawJoint(context, textX, startY, outerCalf, `${side.toUpperCase()} OUTER`, align);
    this._drawJoint(context, textX, startY + 18, innerCalf, `${side.toUpperCase()} INNER`, align);
    this._drawJoint(context, textX, startY + 36, hipPitch, "HIP PITCH", align);
    this._drawJoint(context, textX, startY + 54, knee, "KNEE", align);
    this._drawJoint(context, textX, startY + 72, hipRoll, "HIP ROLL", align);
    this._drawJoint(context, textX, startY + 90, null, "HIP YAW", align);

    this.legTelemetry[side] = {
      ...emptyFoot(),
      ankleDeg: kneeAngle * 180 / Math.PI,
      outerCalfDeg: Number(outerCalf?.angle) || 180,
      innerCalfDeg: Number(innerCalf?.angle) || 180,
    };
  }

  _draw() {
    const { context, width, height } = prepareCanvas(this.canvas);
    context.fillStyle = "#080809";
    context.fillRect(0, 0, width, height);
    context.strokeStyle = "#1e2025";
    context.lineWidth = 1;
    for (let x = 0; x < width; x += 40) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
    }
    for (let y = 0; y < height; y += 40) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }

    context.fillStyle = "#17191d";
    context.strokeStyle = "#8b929b";
    context.lineWidth = 3;
    const torsoWidth = Math.min(210, width * 0.24);
    const torsoHeight = Math.min(180, height * 0.23);
    context.save();
    context.translate(width / 2, height * 0.12 + torsoHeight);
    context.rotate((Number(this.observationRootPitchDegrees) || 0) * Math.PI / 180);
    context.fillRect(-torsoWidth / 2, -torsoHeight, torsoWidth, torsoHeight);
    context.strokeRect(-torsoWidth / 2, -torsoHeight, torsoWidth, torsoHeight);
    context.restore();
    this._drawLeg(context, width, height, "left");
    this._drawLeg(context, width, height, "right");

    const available = SIDES.filter((side) => (
      ["outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll"]
        .some((key) => this._joint(side, key)?.observationValid === true)
    ));
    context.textAlign = "center";
    context.fillStyle = "#facc15";
    context.font = '700 11px "IBM Plex Mono", monospace';
    context.fillText("DROPBEAR MEASURED-STATE VIEW · 2D FALLBACK", width / 2, 24);
    context.fillStyle = available.length ? "#34d399" : "#fb7185";
    context.fillText(`LIVE SIDES ${available.length}/2 · WEBGL UNAVAILABLE`, width / 2, 43);
  }

  setJointStates(joints, selectedCanId = this.selectedCanId) {
    this.joints = joints || [];
    this.selectedCanId = Number(selectedCanId);
    this._draw();
  }

  setActive(active) { this.active = Boolean(active); if (this.active) this._draw(); }
  setObservationRootPitchDegrees(forwardDegrees = 0) { this.observationRootPitchDegrees = Number(forwardDegrees) || 0; if (this.active) this._draw(); }
  setArmSelection(id = null) { this.selectedArmMotorId = id; }
  setVerticalConstraintEnabled(enabled) { this.verticalConstraintEnabled = Boolean(enabled); }
  setExternalRootPose() {}
  resetGroundConstraint() {}
  setResolutionScale() {}
  fit() { this._draw(); }
  resize() { this._draw(); }
}
