"""From-scratch ML primitives: logistic regression, gradient-boosted trees,
isotonic calibration, and ranking metrics. No sklearn — everything is
numpy + standard library so the model is fully inspectable and portable."""

from __future__ import annotations
import numpy as np


# ---------------------------------------------------------------------------
# Logistic Regression (L2-regularized, batch gradient descent)
# ---------------------------------------------------------------------------
class LogisticRegression:
    def __init__(self, lr: float = 0.1, n_iter: int = 2000, l2: float = 1e-3):
        self.lr = lr
        self.n_iter = n_iter
        self.l2 = l2
        self.w: np.ndarray | None = None
        self.b: float = 0.0

    @staticmethod
    def _sigmoid(z: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticRegression":
        n, d = X.shape
        self.w = np.zeros(d)
        self.b = 0.0
        y = y.astype(float)
        for _ in range(self.n_iter):
            p = self._sigmoid(X @ self.w + self.b)
            err = p - y
            grad_w = X.T @ err / n + self.l2 * self.w
            grad_b = float(err.mean())
            self.w -= self.lr * grad_w
            self.b -= self.lr * grad_b
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._sigmoid(X @ self.w + self.b)

    def to_dict(self) -> dict:
        return {"type": "logistic_regression",
                "weights": self.w.tolist(),
                "bias": float(self.b)}


# ---------------------------------------------------------------------------
# Decision Tree Regressor (single tree, used as a weak learner)
# ---------------------------------------------------------------------------
class DecisionTreeRegressor:
    def __init__(self, max_depth: int = 3, min_samples_split: int = 20,
                 n_thresholds: int = 16):
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.n_thresholds = n_thresholds
        self.tree: dict | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "DecisionTreeRegressor":
        self.tree = self._build(X, y.astype(float), depth=0)
        return self

    def _build(self, X: np.ndarray, y: np.ndarray, depth: int) -> dict:
        n = len(y)
        leaf_val = float(y.mean()) if n > 0 else 0.0
        if depth >= self.max_depth or n < self.min_samples_split:
            return {"leaf": True, "value": leaf_val}

        best = None  # (sse, feature_idx, threshold, mask)
        # candidate thresholds via quantiles per-feature
        qs = np.linspace(0.1, 0.9, self.n_thresholds)
        for j in range(X.shape[1]):
            xj = X[:, j]
            ts = np.unique(np.quantile(xj, qs))
            for t in ts:
                mask = xj <= t
                nl, nr = int(mask.sum()), int((~mask).sum())
                if nl < 5 or nr < 5:
                    continue
                yl = y[mask]; yr = y[~mask]
                sse = float(((yl - yl.mean()) ** 2).sum() +
                            ((yr - yr.mean()) ** 2).sum())
                if best is None or sse < best[0]:
                    best = (sse, j, float(t), mask)
        if best is None:
            return {"leaf": True, "value": leaf_val}

        _, j, t, mask = best
        return {
            "leaf": False, "feature": j, "threshold": t,
            "left":  self._build(X[mask],  y[mask],  depth + 1),
            "right": self._build(X[~mask], y[~mask], depth + 1),
        }

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.array([self._predict_one(x, self.tree) for x in X])

    def _predict_one(self, x: np.ndarray, node: dict) -> float:
        if node["leaf"]:
            return node["value"]
        if x[node["feature"]] <= node["threshold"]:
            return self._predict_one(x, node["left"])
        return self._predict_one(x, node["right"])


# ---------------------------------------------------------------------------
# Gradient-Boosted Trees for binary classification (log-odds boosting)
# ---------------------------------------------------------------------------
class GradientBoostedClassifier:
    def __init__(self, n_estimators: int = 120, max_depth: int = 3,
                 learning_rate: float = 0.05, subsample: float = 0.8,
                 seed: int = 0):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.subsample = subsample
        self.trees: list[DecisionTreeRegressor] = []
        self.init_log_odds: float = 0.0
        self.rng = np.random.default_rng(seed)

    @staticmethod
    def _sigmoid(z: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def fit(self, X: np.ndarray, y: np.ndarray,
            X_val: np.ndarray | None = None, y_val: np.ndarray | None = None,
            early_stopping_rounds: int = 15) -> "GradientBoostedClassifier":
        y = y.astype(float)
        p_mean = float(np.clip(y.mean(), 1e-3, 1 - 1e-3))
        self.init_log_odds = float(np.log(p_mean / (1 - p_mean)))
        F = np.full(len(y), self.init_log_odds)
        F_val = np.full(len(y_val), self.init_log_odds) if X_val is not None else None

        self.trees = []
        best_val = float("inf")
        rounds_since_best = 0
        best_n = 0

        for k in range(self.n_estimators):
            p = self._sigmoid(F)
            grad = y - p  # negative gradient of logloss in log-odds space
            if self.subsample < 1.0:
                m = int(self.subsample * len(y))
                idx = self.rng.choice(len(y), m, replace=False)
            else:
                idx = np.arange(len(y))
            tree = DecisionTreeRegressor(max_depth=self.max_depth).fit(X[idx], grad[idx])
            F = F + self.learning_rate * tree.predict(X)
            self.trees.append(tree)

            if X_val is not None:
                F_val = F_val + self.learning_rate * tree.predict(X_val)
                p_val = self._sigmoid(F_val)
                ll = -float(np.mean(y_val * np.log(p_val + 1e-9) +
                                    (1 - y_val) * np.log(1 - p_val + 1e-9)))
                if ll < best_val - 1e-5:
                    best_val = ll
                    best_n = k + 1
                    rounds_since_best = 0
                else:
                    rounds_since_best += 1
                    if rounds_since_best >= early_stopping_rounds:
                        self.trees = self.trees[:best_n]
                        break
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        F = np.full(len(X), self.init_log_odds)
        for tree in self.trees:
            F = F + self.learning_rate * tree.predict(X)
        return self._sigmoid(F)

    def feature_importance(self, n_features: int) -> np.ndarray:
        imp = np.zeros(n_features)

        def walk(node: dict) -> None:
            if node["leaf"]:
                return
            imp[node["feature"]] += 1.0
            walk(node["left"]); walk(node["right"])

        for t in self.trees:
            walk(t.tree)
        s = imp.sum()
        return imp / s if s > 0 else imp

    def to_dict(self) -> dict:
        return {
            "type": "gbt",
            "init_log_odds": self.init_log_odds,
            "learning_rate": self.learning_rate,
            "trees": [self._tree_to_dict(t.tree) for t in self.trees],
        }

    def _tree_to_dict(self, node: dict) -> dict:
        # compact keys keep the JSON small for the dashboard
        if node["leaf"]:
            return {"l": True, "v": node["value"]}
        return {
            "l": False, "f": node["feature"], "t": node["threshold"],
            "L": self._tree_to_dict(node["left"]),
            "R": self._tree_to_dict(node["right"]),
        }


# ---------------------------------------------------------------------------
# Isotonic Regression (PAV) for probability calibration
# ---------------------------------------------------------------------------
class IsotonicRegression:
    def __init__(self):
        self.x_thresholds: np.ndarray | None = None
        self.y_values: np.ndarray | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "IsotonicRegression":
        order = np.argsort(x)
        xs = np.asarray(x)[order]
        ys = np.asarray(y, dtype=float)[order]

        # Pool Adjacent Violators
        sums = list(ys)
        weights = [1.0] * len(ys)
        ends = list(range(len(ys)))
        i = 0
        while i < len(sums) - 1:
            if sums[i] / weights[i] > sums[i + 1] / weights[i + 1]:
                sums[i] += sums[i + 1]
                weights[i] += weights[i + 1]
                ends[i] = ends[i + 1]
                del sums[i + 1]; del weights[i + 1]; del ends[i + 1]
                if i > 0:
                    i -= 1
            else:
                i += 1

        means = [s / w for s, w in zip(sums, weights)]
        thresholds = [xs[e] for e in ends]
        self.x_thresholds = np.array(thresholds)
        self.y_values = np.array(means)
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x)
        idx = np.searchsorted(self.x_thresholds, x, side="left")
        idx = np.clip(idx, 0, len(self.y_values) - 1)
        return self.y_values[idx]

    def to_dict(self) -> dict:
        return {"x": self.x_thresholds.tolist(), "y": self.y_values.tolist()}


# ---------------------------------------------------------------------------
# Platt Scaling (1-D logistic on top of an uncalibrated score)
# ---------------------------------------------------------------------------
# Two-parameter model p_cal = sigmoid(a * s + b). Robust to small val sets in
# a way isotonic isn't: PAV needs many positives per "step" and gets noisy
# when positives are scarce; Platt only has to estimate two scalars.
class PlattScaling:
    def __init__(self, lr: float = 0.1, n_iter: int = 2000):
        self.lr = lr
        self.n_iter = n_iter
        self.a: float = 1.0
        self.b: float = 0.0

    @staticmethod
    def _sigmoid(z: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def fit(self, scores: np.ndarray, y: np.ndarray) -> "PlattScaling":
        s = np.asarray(scores, dtype=float)
        y = np.asarray(y, dtype=float)
        # GBT outputs probabilities in (0,1); map back to log-odds so the
        # logistic has a well-conditioned linear input.
        s = np.log(np.clip(s, 1e-6, 1 - 1e-6) /
                   (1 - np.clip(s, 1e-6, 1 - 1e-6)))
        a, b = 1.0, 0.0
        n = len(y)
        for _ in range(self.n_iter):
            p = self._sigmoid(a * s + b)
            err = p - y
            a -= self.lr * float((err * s).mean())
            b -= self.lr * float(err.mean())
        self.a, self.b = float(a), float(b)
        return self

    def transform(self, scores: np.ndarray) -> np.ndarray:
        s = np.asarray(scores, dtype=float)
        s = np.log(np.clip(s, 1e-6, 1 - 1e-6) /
                   (1 - np.clip(s, 1e-6, 1 - 1e-6)))
        return self._sigmoid(self.a * s + self.b)

    def to_dict(self) -> dict:
        return {"type": "platt", "a": self.a, "b": self.b}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = np.asarray(y_true)
    order = np.argsort(-np.asarray(y_score))
    y_true = y_true[order]
    P = int(y_true.sum())
    N = len(y_true) - P
    if P == 0 or N == 0:
        return float("nan")
    tp = fp = 0
    auc = 0.0
    prev_fpr = prev_tpr = 0.0
    for t in y_true:
        if t == 1: tp += 1
        else:      fp += 1
        tpr = tp / P; fpr = fp / N
        auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2
        prev_fpr, prev_tpr = fpr, tpr
    return float(auc)


def pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = np.asarray(y_true)
    order = np.argsort(-np.asarray(y_score))
    y_true = y_true[order]
    P = int(y_true.sum())
    if P == 0:
        return float("nan")
    tp = fp = 0
    ap = 0.0
    prev_recall = 0.0
    for t in y_true:
        if t == 1: tp += 1
        else:      fp += 1
        precision = tp / (tp + fp)
        recall = tp / P
        ap += (recall - prev_recall) * precision
        prev_recall = recall
    return float(ap)


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    return float(np.mean((np.asarray(y_prob) - np.asarray(y_true)) ** 2))
