"""Optional TensorRT 10.13 engine build and CUDA numerical verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import torch

from .sonic_core import MOTION_TOKEN_DIM, OBSERVATION_DIM, DevicePlan, load_checkpoint, sha256_file


def _torch_dtype(trt_module, value):
    mapping = {
        trt_module.float32: torch.float32,
        trt_module.float16: torch.float16,
        trt_module.bfloat16: torch.bfloat16,
        trt_module.int32: torch.int32,
        trt_module.int64: torch.int64,
        trt_module.bool: torch.bool,
    }
    try:
        return mapping[value]
    except KeyError as error:
        raise RuntimeError(f"unsupported TensorRT tensor dtype: {value}") from error


def build_and_verify_tensorrt(
    onnx_path: Path,
    engine_path: Path,
    checkpoint: Path,
    plan: DevicePlan,
    *,
    fp16: bool = True,
    workspace_bytes: int = 1 << 30,
    batch_size: int = 8,
) -> Dict[str, Any]:
    """Build a dynamic-batch engine and compare one CUDA inference to Torch.

    When TensorRT is absent the result is explicitly ``skipped``.  When
    TensorRT 10.13+ is present, any parse/build/execution/numerical failure is
    raised and therefore fails the end-to-end smoke run.
    """

    if plan.torch_device.type != "cuda":
        return {
            "available": False,
            "status": "skipped",
            "reason": "TensorRT verification requires CUDA",
        }
    try:
        import tensorrt as trt
    except ImportError:
        return {
            "available": False,
            "status": "skipped",
            "reason": "TensorRT Python package is not installed",
        }
    version = tuple(int(part) for part in trt.__version__.split(".")[:2])
    if version < (10, 13):
        return {
            "available": True,
            "version": trt.__version__,
            "status": "skipped",
            "reason": "TensorRT 10.13 or newer is required",
        }

    logger = trt.Logger(trt.Logger.WARNING)
    with torch.cuda.device(plan.torch_device):
        builder = trt.Builder(logger)
        network_flags = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
        network = builder.create_network(network_flags)
        parser = trt.OnnxParser(network, logger)
        model_bytes = onnx_path.read_bytes()
        if not parser.parse(model_bytes):
            errors = [
                str(parser.get_error(index))
                for index in range(parser.num_errors)
            ]
            raise RuntimeError("TensorRT ONNX parse failed: " + " | ".join(errors))
        config = builder.create_builder_config()
        config.set_memory_pool_limit(
            trt.MemoryPoolType.WORKSPACE,
            int(workspace_bytes),
        )
        if fp16 and builder.platform_has_fast_fp16:
            config.set_flag(trt.BuilderFlag.FP16)
        profile = builder.create_optimization_profile()
        profile.set_shape(
            "observation",
            (1, OBSERVATION_DIM),
            (batch_size, OBSERVATION_DIM),
            (max(64, batch_size), OBSERVATION_DIM),
        )
        profile.set_shape(
            "motion_token",
            (1, MOTION_TOKEN_DIM),
            (batch_size, MOTION_TOKEN_DIM),
            (max(64, batch_size), MOTION_TOKEN_DIM),
        )
        config.add_optimization_profile(profile)
        serialized = builder.build_serialized_network(network, config)
        if serialized is None:
            raise RuntimeError("TensorRT returned no serialized engine")
        engine_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = engine_path.with_suffix(engine_path.suffix + ".tmp")
        temporary.write_bytes(bytes(serialized))
        temporary.replace(engine_path)

        runtime = trt.Runtime(logger)
        engine = runtime.deserialize_cuda_engine(engine_path.read_bytes())
        if engine is None:
            raise RuntimeError("TensorRT could not deserialize the built engine")
        context = engine.create_execution_context()
        if context is None:
            raise RuntimeError("TensorRT could not create an execution context")
        context.set_input_shape("observation", (batch_size, OBSERVATION_DIM))
        context.set_input_shape("motion_token", (batch_size, MOTION_TOKEN_DIM))

        generator = torch.Generator(device="cpu").manual_seed(307)
        source_observation = torch.randn(
            batch_size,
            OBSERVATION_DIM,
            generator=generator,
        )
        source_token = torch.randn(
            batch_size,
            MOTION_TOKEN_DIM,
            generator=generator,
        )
        tensors: Dict[str, torch.Tensor] = {}
        for index in range(engine.num_io_tensors):
            name = engine.get_tensor_name(index)
            dtype = _torch_dtype(trt, engine.get_tensor_dtype(name))
            shape = tuple(context.get_tensor_shape(name))
            if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                source = (
                    source_observation
                    if name == "observation"
                    else source_token
                )
                tensor = source.to(
                    device=plan.torch_device,
                    dtype=dtype,
                ).contiguous()
            else:
                tensor = torch.empty(
                    shape,
                    device=plan.torch_device,
                    dtype=dtype,
                )
            tensors[name] = tensor
            if not context.set_tensor_address(name, tensor.data_ptr()):
                raise RuntimeError(f"failed to bind TensorRT tensor {name}")
        current_stream = torch.cuda.current_stream(plan.torch_device)
        stream = torch.cuda.Stream(device=plan.torch_device)
        stream.wait_stream(current_stream)
        if not context.execute_async_v3(stream_handle=stream.cuda_stream):
            raise RuntimeError("TensorRT execute_async_v3 failed")
        stream.synchronize()
        actual = tensors["motor_residual"].float()

        model, _ = load_checkpoint(checkpoint, plan)
        with torch.inference_mode():
            mu, _, _ = model(
                source_observation.to(plan.torch_device),
                source_token.to(plan.torch_device),
            )
            expected = torch.tanh(mu.float())
        maximum_error = float((actual - expected).abs().amax())
        tolerance = 8e-3 if fp16 else 3e-4
        if not torch.isfinite(actual).all() or maximum_error > tolerance:
            raise RuntimeError(
                "TensorRT numerical verification failed: "
                f"error={maximum_error}, tolerance={tolerance}"
            )
    return {
        "available": True,
        "version": trt.__version__,
        "status": "passed",
        "engine": str(engine_path),
        "engine_sha256": sha256_file(engine_path),
        "precision": "fp16" if fp16 else "fp32",
        "batch_size": batch_size,
        "max_abs_error": maximum_error,
        "tolerance": tolerance,
    }
