// Exact, fail-closed CAD selection for the browser simulator.
// Source STEP files, candidate reports and procedural meshes are never released assets.

export function validateCadRegistry(registry) {
  if (!registry || registry.schema_version !== "myactuator-web-cad-registry/1") {
    throw new Error("CAD_REGISTRY_SCHEMA_MISMATCH");
  }
  const configurations = registry.configurations;
  if (!Array.isArray(configurations) || configurations.length !== registry.summary.geometry_configurations) {
    throw new Error("CAD_REGISTRY_CONFIGURATION_COVERAGE");
  }
  const ids = new Set();
  for (const configuration of configurations) {
    if (ids.has(configuration.configuration_id)) throw new Error("CAD_REGISTRY_DUPLICATE_CONFIGURATION");
    ids.add(configuration.configuration_id);
    const released = configuration.review_status === "accepted_redistributable";
    if (configuration.browser_loadable && (!released || !configuration.assets)) {
      throw new Error("CAD_REGISTRY_UNRELEASED_ASSET_EXPOSURE");
    }
    if (!configuration.browser_loadable && configuration.assets !== null) {
      throw new Error("CAD_REGISTRY_UNLOADABLE_ASSET_PATH");
    }
    for (const candidate of configuration.candidate_reports || []) {
      if (candidate.accepted_asset !== false || candidate.support_granted !== false) {
        throw new Error("CAD_REGISTRY_CANDIDATE_PROMOTION");
      }
    }
  }
  return true;
}

export function resolveReleasedCadAsset(registry, exactSelection) {
  validateCadRegistry(registry);
  const { series, model, configurationId } = exactSelection || {};
  if (!series || !model || !configurationId) {
    return { supported: false, reason: "exact_configuration_required", asset: null };
  }
  const matches = registry.configurations.filter(
    (item) => item.configuration_id === configurationId && item.series === series && item.model === model,
  );
  if (matches.length !== 1) {
    return { supported: false, reason: "exact_configuration_not_found", asset: null };
  }
  const configuration = matches[0];
  if (!configuration.browser_loadable) {
    return {
      supported: false,
      reason: configuration.candidate_reports.length
        ? "candidate_not_reviewed_or_released"
        : "configuration_not_reviewed_or_released",
      asset: null,
    };
  }
  return { supported: true, reason: "accepted_redistributable", asset: configuration.assets };
}

export function proceduralFallbackEvidence() {
  return Object.freeze({
    evidenceClass: "toy-visual-only",
    physicalGeometry: false,
    collisionGeometry: false,
    actuatorPlant: false,
    supportGranted: false,
  });
}
