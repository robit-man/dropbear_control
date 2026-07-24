"""Named order conversion for the 22 Dropbear motor coordinates.

All conversions use the semantic action identity as the join key.  The code
does not assume that Isaac Lab, MuJoCo, ROS 2 or an exported policy happen to
enumerate joints in the same order. Isaac Lab and MuJoCo entries are explicitly
declared target orders until generated assets are registered and parity-tested.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

from .embodiment import CONTRACT, EmbodimentContractError


T = TypeVar("T")


class DropbearOrderConverter:
    """Convert motor vectors between declared subsystem orders."""

    def __init__(self) -> None:
        actions = CONTRACT["actions"]
        canonical = tuple(action["name"] for action in actions)
        self._names: dict[str, tuple[str, ...]] = {
            "policy": canonical,
            "mujoco": canonical,
            "isaaclab": canonical,
            "usd": tuple(action["usdJoint"] for action in actions),
            "ros2": tuple(action["rosJoint"] for action in actions),
        }
        self._semantic_by_label: dict[str, dict[str, str]] = {
            "policy": dict(zip(self._names["policy"], canonical)),
            "mujoco": dict(zip(self._names["mujoco"], canonical)),
            "isaaclab": dict(zip(self._names["isaaclab"], canonical)),
            "usd": dict(zip(self._names["usd"], canonical)),
            "ros2": dict(zip(self._names["ros2"], canonical)),
        }
        self._label_by_semantic = {
            order: {semantic: label for label, semantic in mapping.items()}
            for order, mapping in self._semantic_by_label.items()
        }
        self._status = {
            "policy": "verified-contract",
            "usd": "verified-source-manifest",
            "ros2": "verified-sil-contract",
            "mujoco": "declared-target-unverified",
            "isaaclab": "declared-target-unverified",
        }

    @property
    def valid_orders(self) -> tuple[str, ...]:
        return tuple(self._names)

    def names(self, order: str) -> tuple[str, ...]:
        try:
            return self._names[order]
        except KeyError as error:
            raise EmbodimentContractError(f"unknown motor order: {order}") from error

    def status(self, order: str) -> str:
        """Return whether an order is source-verified or only a target."""

        try:
            return self._status[order]
        except KeyError as error:
            raise EmbodimentContractError(f"unknown motor order: {order}") from error

    def index_map(self, from_order: str, to_order: str) -> tuple[int, ...]:
        """Indices that select a source vector into the requested order."""

        source_names = self.names(from_order)
        source_semantics = self._semantic_by_label[from_order]
        source_index = {
            source_semantics[label]: index
            for index, label in enumerate(source_names)
        }
        target_semantics = self._semantic_by_label[to_order]
        return tuple(
            source_index[target_semantics[label]]
            for label in self.names(to_order)
        )

    def convert_vector(
        self,
        values: Sequence[T],
        from_order: str,
        to_order: str,
    ) -> list[T]:
        if len(values) != len(self.names(from_order)):
            raise EmbodimentContractError(
                f"{from_order} vector contains {len(values)} values, "
                f"expected {len(self.names(from_order))}"
            )
        return [values[index] for index in self.index_map(from_order, to_order)]

    def convert_mapping(
        self,
        values: Mapping[str, T],
        from_order: str,
        to_order: str,
    ) -> dict[str, T]:
        expected = set(self.names(from_order))
        if set(values) != expected:
            missing = sorted(expected - set(values))
            extra = sorted(set(values) - expected)
            raise EmbodimentContractError(
                f"{from_order} mapping mismatch; missing={missing}, extra={extra}"
            )
        semantic_values = {
            self._semantic_by_label[from_order][label]: value
            for label, value in values.items()
        }
        return {
            label: semantic_values[self._semantic_by_label[to_order][label]]
            for label in self.names(to_order)
        }

    def labels_for_semantics(
        self, semantics: Sequence[str], order: str
    ) -> tuple[str, ...]:
        labels = self._label_by_semantic.get(order)
        if labels is None:
            raise EmbodimentContractError(f"unknown motor order: {order}")
        try:
            return tuple(labels[name] for name in semantics)
        except KeyError as error:
            raise EmbodimentContractError(
                f"unknown Dropbear motor semantic: {error.args[0]}"
            ) from error
