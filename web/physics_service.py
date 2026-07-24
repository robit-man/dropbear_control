"""Read-only admission status for Dropbear dynamics backends."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any


EXPECTED_USD_SHA256 = (
    "ef4434e0adb5a74cb0fe8e779c49aac4ebdcba48998ed519cf17ab16d822e073"
)


class PhysicsRuntimeRegistry:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.manifest_path = (
            self.project_root
            / "web"
            / "assets"
            / "robot"
            / "dropbear-physics-manifest.json"
        )
        configured = os.environ.get("DROPBEAR_USD_PATH")
        self.usd_path = (
            Path(configured).expanduser().resolve()
            if configured
            else self.project_root / "artifacts" / "usd" / "dropbear.usd"
        )
        self._cached_signature: tuple[int, int] | None = None
        self._cached_digest: str | None = None

    def _usd_digest(self) -> str | None:
        if not self.usd_path.is_file():
            return None
        stat = self.usd_path.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        if self._cached_signature == signature:
            return self._cached_digest
        digest = hashlib.sha256()
        with self.usd_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        self._cached_signature = signature
        self._cached_digest = digest.hexdigest()
        return self._cached_digest

    def snapshot(self) -> dict[str, Any]:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        digest = self._usd_digest()
        source_verified = digest == EXPECTED_USD_SHA256
        isaac_available = bool(
            importlib.util.find_spec("isaaclab")
            or importlib.util.find_spec("omni")
        )
        mujoco_available = importlib.util.find_spec("mujoco") is not None
        return {
            "schema": "dropbear-physics-runtime-status-v1",
            "sourceUsd": {
                "path": str(self.usd_path.relative_to(self.project_root))
                if self.usd_path.is_relative_to(self.project_root)
                else str(self.usd_path),
                "available": self.usd_path.is_file(),
                "verified": source_verified,
                "sha256": digest,
                "expectedSha256": EXPECTED_USD_SHA256,
            },
            "groundTruth": manifest["statistics"],
            "activeBrowserContact": {
                "backend": "usd-mass-force-contact-v1",
                "forceBased": True,
                "gravityMps2": manifest["stage"]["gravityMagnitudeMps2"],
                "nonPenetrationBarrier": True,
                "fullRigidBody": False,
                "physicallyValidated": False,
            },
            "backends": [
                {
                    "id": "isaac-physx-usd",
                    "available": bool(source_verified and isaac_available),
                    "authoritative": True,
                    "blockers": [] if source_verified and isaac_available else [
                        *([] if source_verified else ["verified_source_usd_missing"]),
                        *([] if isaac_available else ["isaac_sim_runtime_missing"]),
                    ],
                },
                {
                    "id": "mujoco-usd",
                    "available": False,
                    "authoritative": False,
                    "blockers": [
                        *([] if source_verified else ["verified_source_usd_missing"]),
                        *([] if mujoco_available else ["mujoco_runtime_missing"]),
                        "dropbear_usd_to_mjcf_closed_chain_compilation_pending",
                    ],
                },
                {
                    "id": "teaching-plant-v2",
                    "available": True,
                    "authoritative": False,
                    "blockers": ["analytical_policy_teaching_plant"],
                },
            ],
        }
