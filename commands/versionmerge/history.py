# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Per-feature edit history across multiple versions.

The Version Merge command walks every version in
[compare_version, baseline_version] and uses this module to coalesce
the per-version timelines into a single history per feature.

Transient features (appeared and then disappeared inside the span,
present in neither the comparison nor the baseline snapshot) are
discarded — they don't need merge actions.
"""

from dataclasses import dataclass, field


@dataclass
class EditEvent:
    """One change applied to one feature in one version."""
    edit_id: str                # unique within this report
    version_number: int         # version where this edit happened
    kind: str                   # "added" | "deleted" | "param_changed" | "sketch_modified"
    param_name: str = ""        # only for param_changed
    older_value_expr: str = ""  # only for param_changed
    newer_value_expr: str = ""  # only for param_changed
    detail: str = ""            # human-readable summary for sketch_modified / added / deleted


@dataclass
class FeatureHistory:
    """All edits to one feature across the walked version span."""
    feature_key: tuple
    feature_type: str
    display_name: str
    present_in_compare: bool
    present_in_baseline: bool
    baseline_index: int | None = None
    compare_params: dict = field(default_factory=dict)   # {name: (value, expr, role)} at compare_v
    baseline_params: dict = field(default_factory=dict)  # {name: (value, expr, role)} at baseline_v
    events: list = field(default_factory=list)           # list[EditEvent]

    def edited_versions(self) -> list:
        """Return the sorted unique list of version numbers that touched this feature."""
        return sorted({e.version_number for e in self.events})

    def param_edits(self, name: str) -> list:
        """Return the chronological list of param_changed events for a given parameter."""
        out = [e for e in self.events if e.kind == "param_changed" and e.param_name == name]
        out.sort(key=lambda e: e.version_number)
        return out

    def param_names_edited(self) -> list:
        """Sorted unique parameter names that changed at least once across the span."""
        return sorted({e.param_name for e in self.events if e.kind == "param_changed" and e.param_name})


def build_histories(
    per_version_features: dict,
    compare_v: int,
    baseline_v: int,
) -> dict:
    """Build {feature_key: FeatureHistory} from per-version feature lists.

    Args:
        per_version_features: ``{version_number: list[TimelineFeature]}`` —
            must include both ``compare_v`` and ``baseline_v``.
        compare_v: lower bound (the user-picked comparison version).
        baseline_v: upper bound (the active document's current version).

    Returns:
        ``{feature_key tuple: FeatureHistory}``. Transient features
        (present in neither compare nor baseline snapshot) are skipped.
    """
    # Local imports to avoid module-level coupling at import time.
    from ..versiondiff.timeline_diff import _feature_key
    from ..versiondiff.param_fingerprint import _values_equal
    from ..versiondiff.sketch_hash import sketch_change_detail

    versions = sorted(per_version_features.keys())
    if len(versions) < 2:
        return {}
    if compare_v not in per_version_features or baseline_v not in per_version_features:
        return {}

    # Index per version: {version_number: {feature_key: TimelineFeature}}
    per_ver_map: dict = {}
    for v in versions:
        m = {}
        for f in per_version_features[v]:
            m[_feature_key(f)] = f
        per_ver_map[v] = m

    all_keys = set()
    for m in per_ver_map.values():
        all_keys.update(m.keys())

    histories: dict = {}

    for key in all_keys:
        present_in_compare = key in per_ver_map[compare_v]
        present_in_baseline = key in per_ver_map[baseline_v]
        if not present_in_compare and not present_in_baseline:
            # Transient — skip.
            continue

        # Identify display info from any version that has the feature.
        sample = None
        for v in versions:
            f = per_ver_map[v].get(key)
            if f is not None:
                sample = f
                break
        if sample is None:
            continue

        baseline_feat = per_ver_map[baseline_v].get(key)
        compare_feat = per_ver_map[compare_v].get(key)

        history = FeatureHistory(
            feature_key=key,
            feature_type=sample.feature_type,
            display_name=sample.name,
            present_in_compare=present_in_compare,
            present_in_baseline=present_in_baseline,
            baseline_index=(baseline_feat.index if baseline_feat else None),
            compare_params=(dict(compare_feat.feature_params) if (compare_feat and compare_feat.feature_params) else {}),
            baseline_params=(dict(baseline_feat.feature_params) if (baseline_feat and baseline_feat.feature_params) else {}),
        )

        # Walk adjacent versions to collect events for this feature.
        for i in range(len(versions) - 1):
            older_v = versions[i]
            newer_v = versions[i + 1]
            older_f = per_ver_map[older_v].get(key)
            newer_f = per_ver_map[newer_v].get(key)

            if older_f is None and newer_f is None:
                continue

            if older_f is None and newer_f is not None:
                history.events.append(EditEvent(
                    edit_id=f"e{newer_v}-add",
                    version_number=newer_v,
                    kind="added",
                    detail="feature added",
                ))
                continue

            if older_f is not None and newer_f is None:
                history.events.append(EditEvent(
                    edit_id=f"e{newer_v}-del",
                    version_number=newer_v,
                    kind="deleted",
                    detail="feature deleted",
                ))
                continue

            # Both present: detect XREF version, sketch fingerprint, + param changes.
            if (older_f.feature_type == "XREF"
                    and newer_f.feature_type == "XREF"
                    and older_f.component_version
                    and newer_f.component_version
                    and older_f.component_version != newer_f.component_version):
                history.events.append(EditEvent(
                    edit_id=f"e{newer_v}-xref",
                    version_number=newer_v,
                    kind="xref_version_changed",
                    older_value_expr=older_f.component_version,
                    newer_value_expr=newer_f.component_version,
                    detail=(
                        f"{older_f.component_version} → "
                        f"{newer_f.component_version}"
                    ),
                ))

            if (older_f.feature_type == "Sketch"
                    and newer_f.feature_type == "Sketch"
                    and older_f.sketch_fingerprint
                    and newer_f.sketch_fingerprint
                    and older_f.sketch_fingerprint.revision_id
                    != newer_f.sketch_fingerprint.revision_id):
                try:
                    sk_detail = sketch_change_detail(
                        older_f.sketch_fingerprint, newer_f.sketch_fingerprint
                    )
                except Exception:
                    sk_detail = "geometry modified"
                history.events.append(EditEvent(
                    edit_id=f"e{newer_v}-sk",
                    version_number=newer_v,
                    kind="sketch_modified",
                    detail=sk_detail or "geometry modified",
                ))

            of_params = older_f.feature_params or {}
            nf_params = newer_f.feature_params or {}
            shared = set(of_params.keys()) & set(nf_params.keys())
            for pname in sorted(shared):
                old_val, old_expr, _ = of_params[pname]
                new_val, new_expr, _ = nf_params[pname]
                if not _values_equal(old_val, new_val):
                    history.events.append(EditEvent(
                        edit_id=f"e{newer_v}-p-{pname}",
                        version_number=newer_v,
                        kind="param_changed",
                        param_name=pname,
                        older_value_expr=old_expr,
                        newer_value_expr=new_expr,
                    ))

        history.events.sort(key=lambda e: (e.version_number, e.kind, e.param_name))
        histories[key] = history

    return histories
