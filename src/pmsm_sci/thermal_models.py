"""Low-order state models for the frozen Paper 4 thermal-transport benchmark."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

STATE_COLUMNS = ("temp_winding", "temp_stator_core", "temp_rotor")
LOSS_FEATURES = (
    "current_magnitude_squared",
    "current_magnitude_squared_times_speed",
    "voltage_times_current_magnitude",
    "absolute_mechanical_power_proxy",
    "speed_squared",
)
MAGNITUDE_NAMES = ("current", "voltage", "speed", "torque")
MODEL_FEATURE_COUNT = 2 + 2 + len(LOSS_FEATURES)


@dataclass(frozen=True)
class MagnitudeFloors:
    """Positive source-derived floors for deployment-prefix normalization."""

    current: float
    voltage: float
    speed: float
    torque: float

    def as_array(self) -> np.ndarray:
        return np.asarray([self.current, self.voltage, self.speed, self.torque], dtype=float)


@dataclass(frozen=True)
class RawLossScales:
    """Source-only numerical scales that preserve absolute-unit information."""

    values: np.ndarray

    def __post_init__(self) -> None:
        values = np.asarray(self.values, dtype=float)
        if values.shape != (len(LOSS_FEATURES),) or not np.isfinite(values).all():
            raise ValueError("raw loss scales must be a finite five-vector")
        if (values <= 0).any():
            raise ValueError("raw loss scales must be strictly positive")
        object.__setattr__(self, "values", values)


@dataclass(frozen=True)
class PositiveThermalModel:
    """Nonnegative effective thermal couplings and heat-source coefficients."""

    coefficients: np.ndarray
    loss_mode: str

    def __post_init__(self) -> None:
        coefficients = np.asarray(self.coefficients, dtype=float)
        if coefficients.shape != (len(STATE_COLUMNS), MODEL_FEATURE_COUNT):
            raise ValueError("positive model has an invalid coefficient shape")
        if not np.isfinite(coefficients).all() or (coefficients < 0).any():
            raise ValueError("positive model coefficients must be finite and nonnegative")
        object.__setattr__(self, "coefficients", coefficients)


@dataclass(frozen=True)
class RidgeThermalModel:
    """Unconstrained linear ARX transition model."""

    coefficients: np.ndarray
    intercepts: np.ndarray
    alpha: float

    def __post_init__(self) -> None:
        coefficients = np.asarray(self.coefficients, dtype=float)
        intercepts = np.asarray(self.intercepts, dtype=float)
        if coefficients.shape != (len(STATE_COLUMNS), MODEL_FEATURE_COUNT):
            raise ValueError("ridge model has an invalid coefficient shape")
        if intercepts.shape != (len(STATE_COLUMNS),):
            raise ValueError("ridge model has an invalid intercept shape")
        if not np.isfinite(coefficients).all() or not np.isfinite(intercepts).all():
            raise ValueError("ridge model parameters must be finite")
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "intercepts", intercepts)


@dataclass(frozen=True)
class FastHistPredictor:
    """Vectorized single-row traversal of a fitted numeric histogram ensemble."""

    baseline: float
    values: np.ndarray
    feature_indices: np.ndarray
    thresholds: np.ndarray
    missing_go_left: np.ndarray
    left_children: np.ndarray
    right_children: np.ndarray
    is_leaf: np.ndarray
    max_depth: int

    @classmethod
    def from_estimator(cls, model: HistGradientBoostingRegressor) -> FastHistPredictor:
        if model.is_categorical_ is not None and np.asarray(model.is_categorical_).any():
            raise ValueError("the frozen fast path supports numeric predictors only")
        predictors = [iteration[0] for iteration in model._predictors]
        max_nodes = max(len(predictor.nodes) for predictor in predictors)
        shape = (len(predictors), max_nodes)
        values = np.zeros(shape, dtype=float)
        feature_indices = np.zeros(shape, dtype=np.int64)
        thresholds = np.zeros(shape, dtype=float)
        missing_go_left = np.zeros(shape, dtype=bool)
        left_children = np.zeros(shape, dtype=np.int64)
        right_children = np.zeros(shape, dtype=np.int64)
        is_leaf = np.ones(shape, dtype=bool)
        max_depth = 0
        for tree_index, predictor in enumerate(predictors):
            nodes = predictor.nodes
            count = len(nodes)
            values[tree_index, :count] = nodes["value"]
            feature_indices[tree_index, :count] = nodes["feature_idx"]
            thresholds[tree_index, :count] = nodes["num_threshold"]
            missing_go_left[tree_index, :count] = nodes["missing_go_to_left"].astype(bool)
            left_children[tree_index, :count] = nodes["left"]
            right_children[tree_index, :count] = nodes["right"]
            is_leaf[tree_index, :count] = nodes["is_leaf"].astype(bool)
            max_depth = max(max_depth, int(nodes["depth"].max()))
        return cls(
            baseline=float(np.asarray(model._baseline_prediction).ravel()[0]),
            values=values,
            feature_indices=feature_indices,
            thresholds=thresholds,
            missing_go_left=missing_go_left,
            left_children=left_children,
            right_children=right_children,
            is_leaf=is_leaf,
            max_depth=max_depth,
        )

    def predict_one(self, row: np.ndarray) -> float:
        row = np.asarray(row, dtype=float)
        tree_indices = np.arange(self.values.shape[0])
        node_indices = np.zeros(self.values.shape[0], dtype=np.int64)
        for _ in range(self.max_depth + 1):
            leaf = self.is_leaf[tree_indices, node_indices]
            if leaf.all():
                break
            active = np.flatnonzero(~leaf)
            nodes = node_indices[active]
            features = self.feature_indices[active, nodes]
            observed = row[features]
            go_left = np.where(
                np.isnan(observed),
                self.missing_go_left[active, nodes],
                observed <= self.thresholds[active, nodes],
            )
            node_indices[active] = np.where(
                go_left,
                self.left_children[active, nodes],
                self.right_children[active, nodes],
            )
        if not self.is_leaf[tree_indices, node_indices].all():
            raise RuntimeError("histogram tree traversal exceeded its fitted maximum depth")
        return self.baseline + float(self.values[tree_indices, node_indices].sum())


@dataclass(frozen=True)
class HybridThermalModel:
    """Positive source network plus fixed nonlinear transition-residual models."""

    base: PositiveThermalModel
    boosters: tuple[HistGradientBoostingRegressor, ...]
    fast_predictors: tuple[FastHistPredictor, ...] | None = None

    def __post_init__(self) -> None:
        if len(self.boosters) != len(STATE_COLUMNS):
            raise ValueError("one residual booster is required per thermal node")
        if self.fast_predictors is None:
            object.__setattr__(
                self,
                "fast_predictors",
                tuple(FastHistPredictor.from_estimator(model) for model in self.boosters),
            )
        elif len(self.fast_predictors) != len(STATE_COLUMNS):
            raise ValueError("one fast residual predictor is required per thermal node")


@dataclass(frozen=True)
class RolloutResult:
    prediction: np.ndarray
    clip_count: int
    nonfinite_count: int


def _magnitudes(frame: pd.DataFrame) -> np.ndarray:
    current = np.hypot(frame["i_d"].to_numpy(float), frame["i_q"].to_numpy(float))
    voltage = np.hypot(frame["u_d"].to_numpy(float), frame["u_q"].to_numpy(float))
    speed = np.abs(frame["speed_rpm"].to_numpy(float))
    torque = np.abs(frame["torque_nm"].to_numpy(float))
    return np.column_stack([current, voltage, speed, torque])


def learn_magnitude_floors(
    profiles: list[pd.DataFrame], *, prefix_seconds: int = 300
) -> MagnitudeFloors:
    """Learn small positive floors from source-train prefix magnitudes only."""

    if not profiles:
        raise ValueError("at least one source profile is required")
    profile_p95 = []
    for profile in profiles:
        prefix = _magnitudes(profile.iloc[:prefix_seconds])
        if len(prefix) == 0:
            raise ValueError("empty source profile")
        profile_p95.append(np.quantile(prefix, 0.95, axis=0))
    typical = np.median(np.vstack(profile_p95), axis=0)
    floors = np.maximum(0.05 * typical, 1e-6)
    return MagnitudeFloors(*map(float, floors))


def prefix_magnitude_scales(
    frame: pd.DataFrame,
    floors: MagnitudeFloors,
    *,
    prefix_seconds: int = 300,
) -> np.ndarray:
    """Estimate deployment scales from exogenous prefix values without target labels."""

    prefix = _magnitudes(frame.iloc[:prefix_seconds])
    if len(prefix) == 0:
        raise ValueError("cannot scale an empty profile")
    return np.maximum(np.quantile(prefix, 0.95, axis=0), floors.as_array())


def _loss_from_magnitudes(magnitudes: np.ndarray) -> np.ndarray:
    current, voltage, speed, torque = magnitudes.T
    return np.column_stack(
        [
            current**2,
            current**2 * speed,
            voltage * current,
            torque * speed * (2.0 * np.pi / 60.0),
            speed**2,
        ]
    )


def normalized_loss_features(
    frame: pd.DataFrame,
    floors: MagnitudeFloors,
    *,
    prefix_seconds: int = 300,
) -> np.ndarray:
    """Build capacity-normalized loss proxies from prefix-only exogenous scales."""

    scale = prefix_magnitude_scales(frame, floors, prefix_seconds=prefix_seconds)
    normalized = _magnitudes(frame) / scale
    return _loss_from_magnitudes(normalized)


def learn_raw_loss_scales(
    profiles: list[pd.DataFrame], *, cap_seconds: int = 3600
) -> RawLossScales:
    """Learn source-only numerical denominators for raw physical-unit proxies."""

    if not profiles:
        raise ValueError("at least one source profile is required")
    profile_p95 = []
    for profile in profiles:
        raw = _loss_from_magnitudes(_magnitudes(profile.iloc[:cap_seconds]))
        profile_p95.append(np.quantile(np.abs(raw), 0.95, axis=0))
    scales = np.maximum(np.median(np.vstack(profile_p95), axis=0), 1e-9)
    return RawLossScales(scales)


def raw_loss_features(frame: pd.DataFrame, scales: RawLossScales) -> np.ndarray:
    """Build raw-unit loss proxies using source-only numerical scaling."""

    return _loss_from_magnitudes(_magnitudes(frame)) / scales.values


def _node_design(
    previous_state: np.ndarray,
    coolant: np.ndarray,
    ambient: np.ndarray,
    losses: np.ndarray,
    node: int,
) -> np.ndarray:
    others = [index for index in range(len(STATE_COLUMNS)) if index != node]
    return np.column_stack(
        [
            previous_state[:, others[0]] - previous_state[:, node],
            previous_state[:, others[1]] - previous_state[:, node],
            coolant - previous_state[:, node],
            ambient - previous_state[:, node],
            losses,
        ]
    )


def transition_design(
    frame: pd.DataFrame, losses: np.ndarray
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Create one-second designs using current inputs and the preceding state."""

    state = frame[list(STATE_COLUMNS)].to_numpy(dtype=float)
    if len(state) != len(losses):
        raise ValueError("loss-feature rows must match the profile")
    if len(state) < 2:
        raise ValueError("a profile needs at least two states")
    previous = state[:-1]
    coolant = frame["coolant"].to_numpy(float)[1:]
    ambient = frame["ambient"].to_numpy(float)[1:]
    current_losses = losses[1:]
    x = [
        _node_design(previous, coolant, ambient, current_losses, node)
        for node in range(len(STATE_COLUMNS))
    ]
    y = [state[1:, node] - previous[:, node] for node in range(len(STATE_COLUMNS))]
    return x, y


def _stack_profile_designs(
    profiles: list[pd.DataFrame],
    profile_losses: list[np.ndarray],
    *,
    cap_seconds: int,
) -> tuple[list[np.ndarray], list[np.ndarray], np.ndarray]:
    if len(profiles) != len(profile_losses) or not profiles:
        raise ValueError("profiles and loss arrays must be nonempty and aligned")
    x_by_node: list[list[np.ndarray]] = [[] for _ in STATE_COLUMNS]
    y_by_node: list[list[np.ndarray]] = [[] for _ in STATE_COLUMNS]
    weights: list[np.ndarray] = []
    for profile, losses in zip(profiles, profile_losses, strict=True):
        n = min(len(profile), cap_seconds)
        x, y = transition_design(profile.iloc[:n], losses[:n])
        transition_count = n - 1
        weights.append(np.full(transition_count, 1.0 / transition_count))
        for node in range(len(STATE_COLUMNS)):
            x_by_node[node].append(x[node])
            y_by_node[node].append(y[node])
    return (
        [np.vstack(parts) for parts in x_by_node],
        [np.concatenate(parts) for parts in y_by_node],
        np.concatenate(weights),
    )


def _bounded_fit(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> np.ndarray:
    root_weight = np.sqrt(weights)
    result = lsq_linear(
        x * root_weight[:, None],
        y * root_weight,
        bounds=(0.0, np.inf),
        tol=1e-10,
        lsmr_tol=1e-10,
        max_iter=2000,
    )
    if not result.success:
        raise RuntimeError(f"bounded thermal fit did not converge: {result.message}")
    return result.x


def fit_positive_source_model(
    profiles: list[pd.DataFrame],
    profile_losses: list[np.ndarray],
    *,
    loss_mode: str,
    cap_seconds: int = 3600,
) -> PositiveThermalModel:
    """Fit a profile-balanced nonnegative source thermal network."""

    x, y, weights = _stack_profile_designs(
        profiles, profile_losses, cap_seconds=cap_seconds
    )
    coefficients = np.vstack(
        [_bounded_fit(x[node], y[node], weights) for node in range(len(STATE_COLUMNS))]
    )
    return PositiveThermalModel(coefficients=coefficients, loss_mode=loss_mode)


def fit_prefix_positive_model(
    frame: pd.DataFrame,
    losses: np.ndarray,
    *,
    prefix_seconds: int,
    source_prior: PositiveThermalModel | None = None,
    prior_penalty: float = 0.0,
) -> PositiveThermalModel:
    """Fit a target-only or source-prior nonnegative model on a strict prefix."""

    if prefix_seconds < 2 or prefix_seconds > len(frame):
        raise ValueError("prefix_seconds must leave at least one transition")
    if prior_penalty < 0:
        raise ValueError("prior_penalty must be nonnegative")
    x, y = transition_design(frame.iloc[:prefix_seconds], losses[:prefix_seconds])
    coefficients = []
    for node in range(len(STATE_COLUMNS)):
        count = len(y[node])
        x_data = x[node] / np.sqrt(count)
        y_data = y[node] / np.sqrt(count)
        if source_prior is not None and prior_penalty > 0:
            prior_x = np.sqrt(prior_penalty) * np.eye(MODEL_FEATURE_COUNT)
            prior_y = np.sqrt(prior_penalty) * source_prior.coefficients[node]
            x_data = np.vstack([x_data, prior_x])
            y_data = np.concatenate([y_data, prior_y])
        weights = np.ones(len(y_data), dtype=float)
        coefficients.append(_bounded_fit(x_data, y_data, weights))
    mode = "target_only" if source_prior is None else f"source_prior_lambda_{prior_penalty:g}"
    return PositiveThermalModel(np.vstack(coefficients), loss_mode=mode)


def fit_ridge_source_model(
    profiles: list[pd.DataFrame],
    profile_losses: list[np.ndarray],
    *,
    alpha: float,
    cap_seconds: int = 3600,
) -> RidgeThermalModel:
    """Fit a profile-balanced unconstrained delta-state ARX comparator."""

    x, y, weights = _stack_profile_designs(
        profiles, profile_losses, cap_seconds=cap_seconds
    )
    coefficients = []
    intercepts = []
    for node in range(len(STATE_COLUMNS)):
        model = Ridge(alpha=alpha, fit_intercept=True)
        model.fit(x[node], y[node], sample_weight=weights)
        coefficients.append(model.coef_)
        intercepts.append(model.intercept_)
    return RidgeThermalModel(np.vstack(coefficients), np.asarray(intercepts), alpha)


def _residual_design(frame: pd.DataFrame, losses: np.ndarray) -> np.ndarray:
    states = frame[list(STATE_COLUMNS)].to_numpy(float)
    return np.column_stack(
        [
            states[:-1],
            frame["coolant"].to_numpy(float)[1:],
            frame["ambient"].to_numpy(float)[1:],
            losses[1:],
        ]
    )


def fit_hybrid_source_model(
    profiles: list[pd.DataFrame],
    profile_losses: list[np.ndarray],
    base: PositiveThermalModel,
    *,
    cap_seconds: int = 3600,
    seed: int = 20260821,
) -> HybridThermalModel:
    """Fit the frozen nonlinear residual comparator on source transitions."""

    common_parts = []
    residual_parts: list[list[np.ndarray]] = [[] for _ in STATE_COLUMNS]
    weight_parts = []
    for profile, losses in zip(profiles, profile_losses, strict=True):
        n = min(len(profile), cap_seconds)
        sliced = profile.iloc[:n]
        sliced_losses = losses[:n]
        x, y = transition_design(sliced, sliced_losses)
        common_parts.append(_residual_design(sliced, sliced_losses))
        weight_parts.append(np.full(n - 1, 1.0 / (n - 1)))
        for node in range(len(STATE_COLUMNS)):
            residual_parts[node].append(y[node] - x[node] @ base.coefficients[node])
    common = np.vstack(common_parts)
    weights = np.concatenate(weight_parts)
    boosters = []
    for node in range(len(STATE_COLUMNS)):
        booster = HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=200,
            max_leaf_nodes=15,
            min_samples_leaf=50,
            l2_regularization=1.0,
            random_state=seed,
        )
        booster.fit(common, np.concatenate(residual_parts[node]), sample_weight=weights)
        boosters.append(booster)
    return HybridThermalModel(base=base, boosters=tuple(boosters))


def _single_design(
    state: np.ndarray, coolant: float, ambient: float, losses: np.ndarray, node: int
) -> np.ndarray:
    return _node_design(
        state.reshape(1, -1),
        np.asarray([coolant]),
        np.asarray([ambient]),
        losses.reshape(1, -1),
        node,
    )[0]


def rollout_state_model(
    model: PositiveThermalModel | RidgeThermalModel | HybridThermalModel,
    frame: pd.DataFrame,
    losses: np.ndarray,
    *,
    start: int,
    end: int,
    temperature_guard: tuple[float, float] = (-50.0, 250.0),
) -> RolloutResult:
    """Generate a closed-loop trajectory without reading post-prefix target states."""

    if not (1 <= start < end <= len(frame)):
        raise ValueError("rollout indices are outside the profile")
    if len(losses) != len(frame):
        raise ValueError("loss-feature rows must match the profile")
    lower, upper = temperature_guard
    state = frame[list(STATE_COLUMNS)].iloc[start - 1].to_numpy(float)
    predictions = np.empty((end - start, len(STATE_COLUMNS)), dtype=float)
    clip_count = 0
    nonfinite_count = 0
    for output_index, time_index in enumerate(range(start, end)):
        coolant = float(frame["coolant"].iloc[time_index])
        ambient = float(frame["ambient"].iloc[time_index])
        current_losses = losses[time_index]
        base_model = model.base if isinstance(model, HybridThermalModel) else model
        delta = np.empty(len(STATE_COLUMNS), dtype=float)
        for node in range(len(STATE_COLUMNS)):
            design = _single_design(state, coolant, ambient, current_losses, node)
            delta[node] = float(design @ base_model.coefficients[node])
            if isinstance(base_model, RidgeThermalModel):
                delta[node] += float(base_model.intercepts[node])
        if isinstance(model, HybridThermalModel):
            common = np.concatenate(
                [state, np.asarray([coolant, ambient]), current_losses]
            )
            if model.fast_predictors is None:
                raise AssertionError("hybrid fast predictors were not initialized")
            delta += np.asarray(
                [predictor.predict_one(common) for predictor in model.fast_predictors]
            )
        next_state = state + delta
        invalid = ~np.isfinite(next_state)
        if invalid.any():
            nonfinite_count += int(invalid.sum())
            next_state[invalid] = state[invalid]
        clipped = (next_state < lower) | (next_state > upper)
        clip_count += int(clipped.sum())
        next_state = np.clip(next_state, lower, upper)
        predictions[output_index] = next_state
        state = next_state
    return RolloutResult(predictions, clip_count, nonfinite_count)


def rollout_persistence(
    frame: pd.DataFrame,
    *,
    start: int,
    end: int,
    boundary_shift: bool,
    temperature_guard: tuple[float, float] = (-50.0, 250.0),
) -> RolloutResult:
    """Generate initial-state or boundary-shift persistence predictions."""

    if not (1 <= start < end <= len(frame)):
        raise ValueError("rollout indices are outside the profile")
    anchor = frame[list(STATE_COLUMNS)].iloc[start - 1].to_numpy(float)
    prediction = np.repeat(anchor.reshape(1, -1), end - start, axis=0)
    if boundary_shift:
        boundary = 0.5 * (
            frame["coolant"].to_numpy(float) + frame["ambient"].to_numpy(float)
        )
        prediction += (boundary[start:end] - boundary[start - 1]).reshape(-1, 1)
    lower, upper = temperature_guard
    clipped = (prediction < lower) | (prediction > upper)
    prediction = np.clip(prediction, lower, upper)
    return RolloutResult(prediction, int(clipped.sum()), 0)
