"""
Detection engines — six independent anomaly detectors.

Tabular (procedure-level features):
  1. IsolationForestDetector  — unsupervised tree-based; no distribution assumption
  2. StatisticalDetector      — rule/threshold; telecom domain knowledge
  3. OneClassSVMDetector      — kernel boundary; non-linear normal region
  4. LOFDetector              — local density; catches cluster-edge outliers
  5. EllipticEnvelopeDetector — Mahalanobis distance; Gaussian baseline

Sequential (message_log windows):
  6. LSTMAutoencoderDetector  — sequence reconstruction; catches order violations

All return a list of anomaly dicts with a common schema:
  {
    type, severity, score, detector, evidence,
    procedure, layer, failure_causes, recommendation,
  }
"""

import logging
from typing import Any, Dict, List

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM
from sklearn.neighbors import LocalOutlierFactor
from sklearn.covariance import EllipticEnvelope

import torch
import torch.nn as nn

from .features import (
    extract_procedure_features,
    extract_sequence_features,
    PROC_FEATURE_NAMES, WINDOW_SIZE,
)

logger = logging.getLogger(__name__)


# ── Shared helpers ────────────────────────────────────────────────────

CAUSE_RECOMMENDATIONS: Dict[str, str] = {
    "congestion": "Check AMF/UPF load; consider increasing capacity or load-balancing.",
    "timeout": "Investigate N2/F1/E1/Xn link latency; verify timer T3xx configuration.",
    "auth-failure": "Check HSS/AUSF reachability; verify UE SIM profile and SUPI.",
    "semantically-incorrect-message": "Inspect NAS message encoding; check AMF/SMF software version compatibility.",
    "radio-connection-with-ue-lost": "Analyse RF coverage; check DRX parameters and handover thresholds.",
    "user-inactivity": "Review inactivity timer configuration in AMF/gNB.",
    "radio-resources-not-available": "Check PRB utilisation; consider adding carriers or cells.",
    "procedure-cancelled": "Verify gNB-DU/CU interface stability; review F1AP trace.",
    "ue-context-release": "Check bearer lifecycle; verify UPF session anchor consistency.",
    "other-failure": "Collect RRC logs and UE traces for root cause analysis.",
    "rlf-report-available": "Review RLF reports; check A3/A5 measurement configuration.",
    "radio-connection-with-UE-lost": "Check Xn interface and handover configuration between gNBs.",
    "unknown": "Enable detailed tracing on the affected network function.",
}

LAYER_RECOMMENDATIONS: Dict[str, str] = {
    "NAS": "Review AMF/SMF logs and NAS trace for affected UE.",
    "NGAP": "Check N2 interface and AMF capacity; review NGAP trace.",
    "RRC": "Analyse gNB RRC logs; check radio coverage and cell config.",
    "F1AP": "Inspect F1 interface; verify gNB-DU software and configuration.",
    "E1AP": "Inspect E1 interface; verify gNB-CU-UP reachability.",
    "XnAP": "Check Xn interface configuration between gNBs.",
}

SEVERITY_THRESHOLDS = {           # success_rate → severity
    98.0: None,                   # ≥ 98% → clean
    95.0: "Low",
    85.0: "Medium",
    0.0: "High",
}


def _rate_to_severity(success_rate: float) -> str:
    for threshold, sev in sorted(SEVERITY_THRESHOLDS.items(), reverse=True):
        if success_rate >= threshold:
            return sev or "Clean"
    return "High"


def _build_anomaly(
    proc_name: str, stats: Dict, severity: str,
    score: float, detector: str, evidence: str,
    top_cause: str = "",
) -> Dict[str, Any]:
    rec = (
        CAUSE_RECOMMENDATIONS.get(top_cause, "")
        or LAYER_RECOMMENDATIONS.get(stats.get("layer", ""), "")
        or "Enable detailed tracing on the affected network function."
    )
    return {
        "type": f"{proc_name} anomaly",
        "severity": severity,
        "score": round(score, 3),
        "detector": detector,
        "evidence": evidence,
        "procedure": proc_name,
        "layer": stats.get("layer", "?"),
        "cell_id": stats.get("cell_id", "—"),
        "failure_causes": stats.get("failure_causes", {}),
        "recommendation": rec,
    }


# ═════════════════════════════════════════════════════════════════════
# 1. Isolation Forest
# ═════════════════════════════════════════════════════════════════════

class IsolationForestDetector:
    """
    Unsupervised anomaly detection on per-procedure KPI features.
    Uses sklearn IsolationForest — no labelled data needed.

    With N procedures as samples, the IF learns what "normal" looks like
    across all feature dimensions and flags outlier procedures.

    contamination=0.15 means up to 15% of procedures can be anomalies.
    In a healthy network, set lower (0.05). For triage captures, keep 0.15.
    """

    def __init__(self, contamination: float = 0.15, random_state: int = 42):
        self.contamination = contamination
        self.random_state = random_state

    def detect(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        procedures = parsed.get("procedures", {})
        proc_names, X = extract_procedure_features(parsed)

        if len(proc_names) < 3:
            logger.info("IF: fewer than 3 procedures — skipping")
            return []

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_estimators=200,
        )
        preds = clf.fit_predict(X_scaled)   # -1 = anomaly, 1 = normal
        raw_scores = clf.score_samples(X_scaled)  # more negative = more anomalous

        # Normalise scores to [0, 1]  (1 = most anomalous)
        s_min, s_max = raw_scores.min(), raw_scores.max()
        norm_scores = 1.0 - (raw_scores - s_min) / (s_max - s_min + 1e-10)

        anomalies = []
        for i, (pred, nscore) in enumerate(zip(preds, norm_scores)):
            if pred != -1:
                continue

            proc_name = proc_names[i]
            stats = procedures[proc_name]
            fail = stats["failure"]
            sr = stats["success_rate"]
            causes = stats.get("failure_causes", {})
            top_cause = max(causes, key=causes.get) if causes else ""

            # Build human-readable evidence from feature vector
            feat_vals = dict(zip(PROC_FEATURE_NAMES, X[i]))
            ev_parts = [f"success_rate={sr:.1f}%", f"failures={fail}"]
            if feat_vals["timeout_ratio"] > 0:
                ev_parts.append(f"timeouts={causes.get('timeout', 0)}")
            if feat_vals["top_cause_concentration"] > 0.7:
                ev_parts.append(f"dominant_cause={top_cause!r} ({causes.get(top_cause, 0)}×)")
            evidence = "; ".join(ev_parts)

            severity = "High" if nscore > 0.75 else ("Medium" if nscore > 0.5 else "Low")

            anomalies.append(
                _build_anomaly(proc_name, stats, severity, nscore,
                               "Isolation Forest", evidence, top_cause)
            )
            logger.info(f"IF anomaly: {proc_name} score={nscore:.3f} ({severity})")

        return anomalies


# ═════════════════════════════════════════════════════════════════════
# 2. Statistical / Rule-based Detector
# ═════════════════════════════════════════════════════════════════════

class StatisticalDetector:
    """
    Threshold-based anomaly detection using telecom domain rules.

    Rules applied per procedure:
      R1  success_rate below 98/95/85 % thresholds
      R2  any timeout failure present
      R3  single cause dominates ≥ 80% of failures (concentration alert)
      R4  zero attempts for a procedure present in another capture's baseline
      R5  failure rate increasing across procedure layers (cascading failure)
    """

    # Telecom-grade thresholds (adjust per network SLA)
    SR_LOW = 98.0
    SR_MEDIUM = 95.0
    SR_HIGH = 85.0
    CONCENTRATION_THRESHOLD = 0.80

    def detect(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        procedures = parsed.get("procedures", {})
        anomalies: List[Dict[str, Any]] = []

        for proc_name, stats in procedures.items():
            sr = stats["success_rate"]
            fail = stats["failure"]
            att = stats["attempts"]
            causes = stats.get("failure_causes", {})

            # R1 — success rate threshold
            if sr < self.SR_HIGH:
                severity = "High"
            elif sr < self.SR_MEDIUM:
                severity = "Medium"
            elif sr < self.SR_LOW and fail > 0:
                severity = "Low"
            else:
                severity = None

            if severity:
                top_cause = max(causes, key=causes.get) if causes else "unknown"
                score = round(1.0 - sr / 100.0, 3)
                evidence = (
                    f"success_rate={sr:.1f}% "
                    f"({fail}/{att} failures)"
                    + (f"; top_cause={top_cause!r}" if causes else "")
                )
                anomalies.append(
                    _build_anomaly(proc_name, stats, severity, score,
                                   "Statistical (threshold)", evidence, top_cause)
                )

            # R2 — any timeout (network connectivity concern)
            if "timeout" in causes and severity is None:
                score = causes["timeout"] / max(fail, 1)
                anomalies.append(
                    _build_anomaly(
                        proc_name, stats, "Low",
                        round(score * 0.5, 3),
                        "Statistical (timeout rule)",
                        f"{causes['timeout']} timeout failure(s) detected",
                        "timeout",
                    )
                )

            # R3 — cause concentration alert
            if fail >= 2 and causes:
                top_n = max(causes.values())
                if top_n / fail >= self.CONCENTRATION_THRESHOLD and severity is None:
                    top_cause = max(causes, key=causes.get)
                    anomalies.append(
                        _build_anomaly(
                            proc_name, stats, "Low",
                            round(top_n / fail, 3),
                            "Statistical (cause concentration)",
                            f"{top_n}/{fail} failures share cause {top_cause!r}",
                            top_cause,
                        )
                    )

        # R5 — cascading failure: registration fails but auth still attempted
        self._detect_cascading(procedures, anomalies)

        return anomalies

    def _detect_cascading(self, procedures: Dict, anomalies: List) -> None:
        """
        Flag when upstream procedure failure rate > 20% but downstream still shows
        high attempt count — suggests incomplete failure isolation.
        """
        CHAIN = [
            ("NAS_Registration", "NAS_Authentication"),
            ("NAS_Authentication", "NAS_SecurityMode"),
            ("NAS_SecurityMode", "NAS_PDUSession_Establishment"),
            ("RRC_Setup", "RRC_Reconfiguration"),
            ("NGAP_InitialContextSetup", "NGAP_PDUSessionResourceSetup"),
            ("F1AP_UEContextSetup", "F1AP_DLRRCMessageTransfer"),
        ]
        for upstream, downstream in CHAIN:
            up = procedures.get(upstream)
            down = procedures.get(downstream)
            if not up or not down:
                continue
            up_fail_rate = up["failure"] / max(up["attempts"], 1)
            if up_fail_rate > 0.20 and down["attempts"] > 0:
                anomalies.append({
                    "type": f"Cascading failure: {upstream} → {downstream}",
                    "severity": "Medium",
                    "score": round(up_fail_rate, 3),
                    "detector": "Statistical (cascade rule)",
                    "evidence": (
                        f"{upstream} failure_rate={up_fail_rate * 100:.0f}% "
                        f"while {downstream} still has {down['attempts']} attempts"
                    ),
                    "procedure": upstream,
                    "layer": up.get("layer", "?"),
                    "cell_id": up.get("cell_id", "—"),
                    "failure_causes": up.get("failure_causes", {}),
                    "recommendation": (
                        f"Investigate {upstream} failures first; "
                        f"downstream {downstream} may inherit the root cause."
                    ),
                })


# ═════════════════════════════════════════════════════════════════════
# 3. LSTM Autoencoder
# ═════════════════════════════════════════════════════════════════════

class _LSTMAutoencoder(nn.Module):
    """
    Sequence-to-sequence autoencoder.
    Encoder: LSTM compresses window → latent vector.
    Decoder: repeats latent → LSTM reconstructs the window.
    High reconstruction MSE on a window → that window is anomalous.
    """

    def __init__(self, n_features: int = 4, hidden: int = 32, n_layers: int = 1):
        super().__init__()
        self.n_features = n_features
        self.hidden = hidden
        self.encoder = nn.LSTM(n_features, hidden, n_layers, batch_first=True)
        self.decoder = nn.LSTM(hidden, hidden, n_layers, batch_first=True)
        self.output = nn.Linear(hidden, n_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, n_features)
        _, (h, c) = self.encoder(x)
        # Repeat hidden state seq_len times to feed decoder
        seq_len = x.size(1)
        dec_in = h[-1].unsqueeze(1).repeat(1, seq_len, 1)
        dec_out, _ = self.decoder(dec_in, (h, c))
        return self.output(dec_out)   # (batch, seq_len, n_features)


class LSTMAutoencoderDetector:
    """
    Detects anomalous EVENT SEQUENCES in the message log.

    Trains a small LSTM autoencoder on all windows from the capture,
    then flags windows whose reconstruction MSE exceeds mean + 2*std.

    Works on a single PCAP capture (no pre-trained weights needed) because
    it trains and evaluates on the same capture — the assumption is that
    most windows are "normal" and a few are outliers.
    """

    def __init__(
        self,
        hidden: int = 32,
        epochs: int = 60,
        lr: float = 1e-3,
        window: int = WINDOW_SIZE,
        z_score: float = 2.0,          # flag windows > mean + z*std
    ):
        self.hidden = hidden
        self.epochs = epochs
        self.lr = lr
        self.window = window
        self.z_score = z_score

    def detect(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        windows, meta, _ = extract_sequence_features(parsed, self.window)

        if len(windows) < 5:
            logger.info("LSTM-AE: fewer than 5 windows — skipping")
            return []

        n_feat = windows.shape[2]
        model = _LSTMAutoencoder(n_features=n_feat, hidden=self.hidden)
        opt = torch.optim.Adam(model.parameters(), lr=self.lr)
        loss_fn = nn.MSELoss()

        X = torch.tensor(windows)      # (N, W, F)

        # ── Training ─────────────────────────────────────────────────
        model.train()
        for epoch in range(self.epochs):
            opt.zero_grad()
            recon = model(X)
            loss = loss_fn(recon, X)
            loss.backward()
            opt.step()
            if (epoch + 1) % 20 == 0:
                logger.info(f"LSTM-AE epoch {epoch + 1}/{self.epochs} loss={loss.item():.5f}")

        # ── Inference ────────────────────────────────────────────────
        model.eval()
        with torch.no_grad():
            recon = model(X)

        # Per-window MSE
        errors = ((X - recon) ** 2).mean(dim=(1, 2)).numpy()   # (N,)

        threshold = errors.mean() + self.z_score * errors.std()
        logger.info(
            f"LSTM-AE: mean_err={errors.mean():.5f} "
            f"std={errors.std():.5f} threshold={threshold:.5f}"
        )

        procedures = parsed.get("procedures", {})
        anomalies: List[Dict[str, Any]] = []

        for i, (err, m) in enumerate(zip(errors, meta)):
            if err <= threshold:
                continue

            proc_name = m["procedure"]
            stats = procedures.get(proc_name, {})
            score = round(float(err / (threshold + 1e-10)), 3)
            severity = "High" if score > 2.0 else ("Medium" if score > 1.5 else "Low")

            anomalies.append({
                "type": f"Anomalous message sequence near {proc_name}",
                "severity": severity,
                "score": min(score, 1.0),
                "detector": "LSTM Autoencoder",
                "evidence": (
                    f"Window {i} (events {m['start_idx']}–{m['end_idx']}): "
                    f"reconstruction_error={err:.5f} > threshold={threshold:.5f}; "
                    f"layer={m['layer']} procedure={m['procedure']} role={m['role']}"
                ),
                "procedure": proc_name,
                "layer": m.get("layer", "?"),
                "cell_id": stats.get("cell_id", "—"),
                "failure_causes": stats.get("failure_causes", {}),
                "recommendation": (
                    LAYER_RECOMMENDATIONS.get(m.get("layer", ""), "")
                    or "Review message sequence in context; check for unexpected procedure order."
                ),
            })

        return anomalies


# ═════════════════════════════════════════════════════════════════════
# 4. One-Class SVM
# ═════════════════════════════════════════════════════════════════════

class OneClassSVMDetector:
    """
    Kernel-based boundary method on procedure-level features.

    WHY: Isolation Forest uses tree depth (global partitioning); OC-SVM
    learns a non-linear geometric boundary around the normal cluster.
    Catches anomalies that lie near the IF decision boundary but clearly
    outside the support of the normal distribution in kernel space.

    nu = upper bound on the fraction of anomalies (mirrors contamination).
    rbf + gamma='scale' auto-tunes to feature variance.
    """

    def __init__(self, nu: float = 0.15, kernel: str = "rbf"):
        self.nu = nu
        self.kernel = kernel

    def detect(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        procedures = parsed.get("procedures", {})
        proc_names, X = extract_procedure_features(parsed)

        if len(proc_names) < 3:
            logger.info("OC-SVM: fewer than 3 procedures — skipping")
            return []

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = OneClassSVM(nu=self.nu, kernel=self.kernel, gamma="scale")
        preds = clf.fit_predict(X_scaled)         # -1 = anomaly
        scores = clf.decision_function(X_scaled)   # more negative = more anomalous

        s_min, s_max = scores.min(), scores.max()
        norm_scores = 1.0 - (scores - s_min) / (s_max - s_min + 1e-10)

        anomalies = []
        for i, (pred, nscore) in enumerate(zip(preds, norm_scores)):
            if pred != -1:
                continue
            proc_name = proc_names[i]
            stats = procedures[proc_name]
            sr = stats["success_rate"]
            fail = stats["failure"]
            causes = stats.get("failure_causes", {})
            top_cause = max(causes, key=causes.get) if causes else ""

            severity = "High" if nscore > 0.75 else ("Medium" if nscore > 0.5 else "Low")
            evidence = (
                f"success_rate={sr:.1f}%; failures={fail}; "
                f"SVM_decision={scores[i]:.4f} (outside normal boundary)"
            )
            anomalies.append(
                _build_anomaly(proc_name, stats, severity, nscore,
                               "One-Class SVM", evidence, top_cause)
            )
            logger.info(f"OC-SVM anomaly: {proc_name} score={nscore:.3f} ({severity})")

        return anomalies


# ═════════════════════════════════════════════════════════════════════
# 5. Local Outlier Factor (LOF)
# ═════════════════════════════════════════════════════════════════════

class LOFDetector:
    """
    Density-based local anomaly detection on procedure-level features.

    WHY: IF and OC-SVM are global — they compare each point to the whole
    dataset. LOF compares each procedure to its k-nearest neighbors.
    A procedure can look globally unremarkable but be a local outlier
    (e.g., 85% success rate in a cluster where all peers are >99%).
    LOF catches these cluster-edge cases the other methods miss.

    n_neighbors=5 (or n_procs-1 if fewer) gives a tight local window.
    contamination=0.15 aligns with the other detectors.
    """

    def __init__(self, n_neighbors: int = 5, contamination: float = 0.15):
        self.n_neighbors = n_neighbors
        self.contamination = contamination

    def detect(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        procedures = parsed.get("procedures", {})
        proc_names, X = extract_procedure_features(parsed)

        if len(proc_names) < 4:
            logger.info("LOF: fewer than 4 procedures — skipping")
            return []

        n_neighbors = min(self.n_neighbors, len(proc_names) - 1)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = LocalOutlierFactor(
            n_neighbors=n_neighbors,
            contamination=self.contamination,
        )
        preds = clf.fit_predict(X_scaled)        # -1 = anomaly
        lof_scores = -clf.negative_outlier_factor_    # higher = more anomalous

        s_min, s_max = lof_scores.min(), lof_scores.max()
        norm_scores = (lof_scores - s_min) / (s_max - s_min + 1e-10)

        anomalies = []
        for i, (pred, nscore) in enumerate(zip(preds, norm_scores)):
            if pred != -1:
                continue
            proc_name = proc_names[i]
            stats = procedures[proc_name]
            sr = stats["success_rate"]
            fail = stats["failure"]
            causes = stats.get("failure_causes", {})
            top_cause = max(causes, key=causes.get) if causes else ""

            severity = "High" if nscore > 0.75 else ("Medium" if nscore > 0.5 else "Low")
            evidence = (
                f"success_rate={sr:.1f}%; failures={fail}; "
                f"LOF={lof_scores[i]:.4f} ({abs(lof_scores[i] - 1.0):.2f}× denser neighbors)"
            )
            anomalies.append(
                _build_anomaly(proc_name, stats, severity, nscore,
                               "LOF", evidence, top_cause)
            )
            logger.info(f"LOF anomaly: {proc_name} score={nscore:.3f} ({severity})")

        return anomalies


# ═════════════════════════════════════════════════════════════════════
# 6. Elliptic Envelope (Gaussian / Mahalanobis)
# ═════════════════════════════════════════════════════════════════════

class EllipticEnvelopeDetector:
    """
    Robust Gaussian covariance estimator — Mahalanobis distance baseline.

    WHY: The simplest interpretable baseline. Fits a multivariate Gaussian
    to the procedure feature space; points with high Mahalanobis distance
    are flagged. When the normal procedures form a roughly elliptical
    cluster (common in stable networks), this is the most reliable method.
    Serves as a sanity check: any anomaly missed by this but caught by
    ML methods warrants extra scrutiny.

    Requires n_samples > n_features; skips gracefully when not met.
    contamination=0.10 (tighter than others — only clear Gaussian outliers).
    """

    def __init__(self, contamination: float = 0.10):
        self.contamination = contamination

    def detect(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        procedures = parsed.get("procedures", {})
        proc_names, X = extract_procedure_features(parsed)

        n_procs, n_feats = X.shape
        if n_procs < n_feats + 2:
            logger.info(
                f"Elliptic Envelope: {n_procs} procedures < {n_feats} features + 2 — skipping"
            )
            return []

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        import warnings
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # MCD convergence noise on small samples
                clf = EllipticEnvelope(contamination=self.contamination, random_state=42)
                preds = clf.fit_predict(X_scaled)
                mahal = clf.mahalanobis(X_scaled)
        except Exception as e:
            logger.warning(f"Elliptic Envelope: fit failed — {e}")
            return []

        s_min, s_max = mahal.min(), mahal.max()
        norm_scores = (mahal - s_min) / (s_max - s_min + 1e-10)

        anomalies = []
        for i, (pred, nscore) in enumerate(zip(preds, norm_scores)):
            if pred != -1:
                continue
            proc_name = proc_names[i]
            stats = procedures[proc_name]
            sr = stats["success_rate"]
            fail = stats["failure"]
            causes = stats.get("failure_causes", {})
            top_cause = max(causes, key=causes.get) if causes else ""

            severity = "High" if nscore > 0.75 else ("Medium" if nscore > 0.5 else "Low")
            evidence = (
                f"success_rate={sr:.1f}%; failures={fail}; "
                f"Mahalanobis²={mahal[i]:.2f} (outside {int((1 - self.contamination) * 100)}th-pct Gaussian envelope)"
            )
            anomalies.append(
                _build_anomaly(proc_name, stats, severity, nscore,
                               "Elliptic Envelope", evidence, top_cause)
            )
            logger.info(f"Elliptic Envelope anomaly: {proc_name} score={nscore:.3f} ({severity})")

        return anomalies
