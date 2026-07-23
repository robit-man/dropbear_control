// web/js/threejs.js
//
// Simple Three.js motor visualization for the MyActuator dashboard.
// Displays a motor body and output shaft, with shaft rotation based on motor position.

import * as THREE from 'three';

export class MotorVisualizer {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setSize(canvas.width, canvas.height);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1a1a1a);

    this.camera = new THREE.PerspectiveCamera(45, canvas.width / canvas.height, 0.1, 100);
    this.camera.position.set(0, 0, 3);
    // Look at origin
    this.camera.lookAt(0, 0, 0);

    // Light
    const light = new THREE.DirectionalLight(0xffffff, 1);
    light.position.set(1, 1, 1);
    this.scene.add(light);
    const ambient = new THREE.AmbientLight(0x404040);
    this.scene.add(ambient);

    // Motor body (cylinder)
    const bodyGeometry = new THREE.CylinderGeometry(0.5, 0.5, 1, 32);
    const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0x2a2a2a });
    this.body = new THREE.Mesh(bodyGeometry, bodyMaterial);
    this.body.rotation.x = Math.PI / 2; // align cylinder along Z? We'll set shaft along Z later
    this.scene.add(this.body);

    // Shaft (cylinder)
    const shaftGeometry = new THREE.CylinderGeometry(0.1, 0.1, 1.5, 32);
    const shaftMaterial = new THREE.MeshStandardMaterial({ color: 0xfacc15 });
    this.shaft = new THREE.Mesh(shaftGeometry, shaftMaterial);
    this.shaft.position.z = 0.25; // offset so that one end is at body center?
    this.scene.add(this.shaft);

    // Optional: add a base or mounting plate
    const baseGeometry = new THREE.CylinderGeometry(0.6, 0.6, 0.05, 32);
    const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x1c232c });
    this.base = new THREE.Mesh(baseGeometry, baseMaterial);
    this.base.position.z = -0.525; // below body
    this.scene.add(this.base);

    // Store initial shaft rotation (we'll rotate around Y? Actually, output shaft rotation is along its length.
    // We'll define the shaft's local Z as the axis of rotation.
    // The shaft geometry is a cylinder along Z? Actually, CylinderGeometry by default has height along Y.
    // We'll rotate the shaft to align its length with Z.
    this.shaft.rotation.x = Math.PI / 2; // now cylinder along Z
    // The rotation we want to apply is around the shaft's local Z (which is now the cylinder axis).
    // We'll create a separate object to hold the shaft and rotate it around Z.
    // Let's redo: create a shaft holder.
    // For simplicity, we'll just rotate the shaft mesh around its local Z after positioning.
    // We'll adjust: create a shaft object that is a cylinder along Z, then rotate around Z.
    // We'll rebuild.

    // Instead, let's create a simple line for shaft? But we want a cylinder.
    // Let's create a cylinder along Z, then we can rotate around Z to simulate spinning.
    // The cylinder's rotation around Z will not change its appearance (it's symmetric). So we need an asymmetric marker.
    // We'll add a small box at the end of the shaft to indicate rotation.
    // For now, we'll just rotate the shaft around Y? Actually, the output shaft rotates along its length, which we want to visualize as spinning.
    // Since a cylinder looks the same when spun, we need a feature. We'll add a longitudinal stripe or a flat spot.
    // For simplicity, we'll just rotate the shaft around its local X? That would be like flipping.
    // Let's think: The motor position is the angle of the output shaft. We want to show the shaft rotating.
    // We can draw a line from the center to the edge of a disk at the end of the shaft.
    // Let's change approach: create a disk at the end of the shaft, and a line on the disk.

    // Given time, we'll do a simple visualization: a cylinder for the body, and a line for the shaft that rotates.
    // We'll replace the shaft with a line.

    // Remove the previous shaft and base.
    this.scene.remove(this.shaft);
    this.scene.remove(this.base);

    // Create a line for the shaft
    const shaftGeometryLine = new THREE.BufferGeometry();
    const points = [
      new THREE.Vector3(0, 0, -0.5), // start at back of body
      new THREE.Vector3(0, 0, 0.5)   // end at front of body
    ];
    shaftGeometryLine.setFromPoints(points);
    const shaftMaterialLine = new THREE.LineBasicMaterial({ color: 0xfacc15, linewidth: 3 });
    this.shaftLine = new THREE.Line(shaftGeometryLine, shaftMaterialLine);
    this.scene.add(this.shaftLine);

    // Create a disk at the front end to show rotation
    const diskGeometry = new THREE.RingGeometry(0.15, 0.2, 32);
    const diskMaterial = new THREE.MeshBasicMaterial({ color: 0xfacc15, side: THREE.DoubleSide });
    this.disk = new THREE.Mesh(diskGeometry, diskMaterial);
    this.disk.position.z = 0.5; // at front end
    this.disk.rotation.x = Math.PI / 2; // lie in XY plane? Actually, we want the disk facing outward along Z.
    // If we want the disk perpendicular to the shaft (which is along Z), we set its normal along Z.
    // The RingGeometry lies in XY plane by default. So we rotate 90 degrees around X to make it lie in YZ? Let's just set rotation.x = -Math.PI/2 to face forward.
    this.disk.rotation.x = -Math.PI / 2;
    this.scene.add(this.disk);

    // Add a line on the disk to indicate angle
    const lineGeometry = new THREE.BufferGeometry();
    const linePoints = [
      new THREE.Vector3(0, 0, 0.5), // center of disk
      new THREE.Vector3(0.2, 0, 0.5) // point at radius 0.2 along X
    ];
    lineGeometry.setFromPoints(linePoints);
    const lineMaterial = new THREE.LineBasicMaterial({ color: 0xff0000 });
    this.angleLine = new THREE.Line(lineGeometry, lineMaterial);
    this.disk.add(this.angleLine); // attach to disk so it rotates with disk

    // Group body and shaft so we can position them together
    this.motorGroup = new THREE.Group();
    this.motorGroup.add(this.body);
    this.motorGroup.add(this.shaftLine);
    this.motorGroup.add(this.disk);
    this.scene.add(this.motorGroup);

    // Initial update
    this.update(0);
  }

  setSize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  /**
   * Update the motor visualization based on motor position (in radians).
   * @param {number} positionRad - motor position in radians
   */
  update(positionRad) {
    // Rotate the disk (and the angle line) around the shaft axis (Z) by positionRad
    this.disk.rotation.z = positionRad;
    // Also rotate the motor group? The body should stay fixed.
    // We'll just update the disk.
    this.renderer.render(this.scene, this.camera);
  }

  // Optional: animate render loop
  animate() {
    requestAnimationFrame(() => this.animate());
    this.renderer.render(this.scene, this.camera);
  }
}

// If we want to use a simple function to create and return a visualizer
export function createMotorVisualizer(canvas) {
  return new MotorVisualizer(canvas);
}