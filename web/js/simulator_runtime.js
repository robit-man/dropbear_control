// Redacted, exact simulator-catalog admission for browser consumers.
// This module selects evidence classes only. It never resolves a file or asset.

function deny(reason, blockers = []) {
  return Object.freeze({
    allowed: false,
    reason,
    blockers: Object.freeze([...blockers]),
    backend: null,
    model: null,
    exactModelFidelity: false,
    physicallyValidated: false,
    physicalIo: false,
  });
}

export function validateSimulatorRuntimeCatalog(catalog) {
  if (!catalog || catalog.schema_version !== "myactuator-simulator-runtime-catalog/1") {
    throw new Error("SIMULATOR_CATALOG_SCHEMA_MISMATCH");
  }
  if (catalog.support_granted !== false
      || catalog.physical_motion_authority !== false
      || catalog.physical_io_enabled !== false) {
    throw new Error("SIMULATOR_CATALOG_AUTHORITY_PROMOTION");
  }
  const { summary, models, backends, dropbear } = catalog;
  if (!summary || !Array.isArray(models) || !Array.isArray(backends)
      || summary.model_count !== 44
      || summary.source_variant_count !== 53
      || summary.geometry_configuration_count !== 53
      || models.length !== 44
      || summary.backend_descriptor_count !== backends.length) {
    throw new Error("SIMULATOR_CATALOG_COVERAGE_MISMATCH");
  }
  const modelKeys = new Set();
  const identities = new Set();
  const configurationIds = new Set();
  const variantIds = new Set();
  for (const model of models) {
    const identity = `${model.series}\u0000${model.model}`;
    if (modelKeys.has(model.model_key) || identities.has(identity)) {
      throw new Error("SIMULATOR_CATALOG_DUPLICATE_MODEL");
    }
    modelKeys.add(model.model_key);
    identities.add(identity);
    if (model.source_step_runtime_asset !== false) {
      throw new Error("SIMULATOR_CATALOG_SOURCE_STEP_PROMOTION");
    }
    const expectedExact = model.fidelity.exact_model_geometry_ready
      && model.fidelity.exact_model_plant_ready;
    if (model.fidelity.exact_model_simulation_ready !== expectedExact) {
      throw new Error("SIMULATOR_CATALOG_FIDELITY_RELATION");
    }
    for (const configurationId of model.configuration_ids) {
      if (configurationIds.has(configurationId)) {
        throw new Error("SIMULATOR_CATALOG_DUPLICATE_CONFIGURATION");
      }
      configurationIds.add(configurationId);
    }
    for (const variantId of model.source_variant_ids) {
      if (variantIds.has(variantId)) {
        throw new Error("SIMULATOR_CATALOG_DUPLICATE_VARIANT");
      }
      variantIds.add(variantId);
    }
  }
  if (configurationIds.size !== 53 || variantIds.size !== 53) {
    throw new Error("SIMULATOR_CATALOG_PARTITION_MISMATCH");
  }
  const backendIds = new Set();
  for (const backend of backends) {
    if (backendIds.has(backend.backend_id) || backend.physical_io !== false) {
      throw new Error("SIMULATOR_CATALOG_BACKEND_IDENTITY");
    }
    backendIds.add(backend.backend_id);
    if (backend.kind === "recorded_replay" && backend.command_capable !== false) {
      throw new Error("SIMULATOR_CATALOG_REPLAY_PROMOTION");
    }
    if ((backend.kind === "protocol_emulator" || backend.kind === "toy_demo")
        && backend.models_actuator_dynamics !== false) {
      throw new Error("SIMULATOR_CATALOG_DYNAMICS_PROMOTION");
    }
  }
  const wholeRobotReady = dropbear.whole_robot_graph_ready
    && dropbear.whole_robot_cad_ready
    && dropbear.whole_robot_plant_ready;
  if (dropbear.whole_robot_runtime_ready !== wholeRobotReady) {
    throw new Error("SIMULATOR_CATALOG_DROPBEAR_RELATION");
  }
  return true;
}

export function admitSimulatorSelection(catalog, selection) {
  validateSimulatorRuntimeCatalog(catalog);
  if (!selection
      || !selection.catalogGenerationSha256
      || !selection.modelKey
      || !selection.series
      || !selection.model
      || !selection.configurationId
      || !selection.backendId
      || !selection.backendKind
      || !selection.useCase) {
    return deny("exact_selection_required");
  }
  if (selection.catalogGenerationSha256 !== catalog.integrity.record_sha256) {
    return deny("stale_catalog_generation", ["catalog_generation_changed"]);
  }
  const model = catalog.models.find((item) => item.model_key === selection.modelKey);
  if (!model) return deny("model_not_found", ["exact_model_key_not_registered"]);
  if (model.series !== selection.series || model.model !== selection.model) {
    return deny("model_identity_mismatch", ["model_key_series_model_disagree"]);
  }
  if (!model.configuration_ids.includes(selection.configurationId)) {
    return deny("configuration_not_found", ["exact_configuration_not_owned_by_model"]);
  }
  const backend = catalog.backends.find((item) => item.backend_id === selection.backendId);
  if (!backend) return deny("backend_not_found", ["exact_backend_not_registered"]);
  if (backend.kind !== selection.backendKind) {
    return deny("backend_kind_mismatch", ["backend_id_kind_disagree"]);
  }
  if (!backend.runtime_loadable) return deny("backend_not_loadable", backend.blockers);
  if (!backend.allowed_use_cases.includes(selection.useCase)) {
    return deny("use_case_not_supported", ["backend_use_case_mismatch"]);
  }
  if (selection.requireDropbearWholeRobot && !catalog.dropbear.whole_robot_runtime_ready) {
    return deny("whole_robot_fidelity_unavailable", catalog.dropbear.blockers);
  }
  const exact = model.fidelity.exact_model_simulation_ready
    && backend.exact_model_applicability_verified
    && model.admitted_exact_model_backend_ids.includes(backend.backend_id);
  if (selection.requireExactModelFidelity && !exact) {
    return deny("exact_model_fidelity_unavailable", model.blockers);
  }
  const physical = exact
    && model.fidelity.physically_correlated_plant_ready
    && backend.physically_validated;
  if (selection.requirePhysicalValidation && !physical) {
    return deny("physical_validation_unavailable", [
      "physically_correlated_exact_model_backend_missing",
    ]);
  }
  return Object.freeze({
    allowed: true,
    reason: "allowed",
    blockers: Object.freeze([]),
    backend: Object.freeze({
      backendId: backend.backend_id,
      backendKind: backend.kind,
      evidenceClass: backend.evidence_class,
      substitutionScope: backend.substitution_scope,
      commandCapable: backend.command_capable,
      deterministicVirtualTime: backend.deterministic_virtual_time,
    }),
    model: Object.freeze({
      modelKey: model.model_key,
      series: model.series,
      model: model.model,
      configurationId: selection.configurationId,
    }),
    exactModelFidelity: exact,
    physicallyValidated: physical,
    physicalIo: false,
  });
}

export function simulatorReadinessSummary(catalog) {
  validateSimulatorRuntimeCatalog(catalog);
  return Object.freeze({
    catalogGenerationSha256: catalog.integrity.record_sha256,
    modelCount: catalog.summary.model_count,
    configurationCount: catalog.summary.geometry_configuration_count,
    exactModelReadyCount: catalog.summary.exact_model_simulation_ready_count,
    browserArticulatedAssetReadyCount:
      catalog.summary.browser_articulated_asset_ready_count,
    dropbearWholeRobotReady: catalog.dropbear.whole_robot_runtime_ready,
    physicalIoEnabled: false,
    supportGranted: false,
  });
}
