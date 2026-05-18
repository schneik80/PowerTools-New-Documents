# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Apply selected merges from the Version Merge palette back into the active design.

Supported merge kinds:
    "params"          — revert one or more user parameters to older expressions.
    "xref_version"    — switch an external-reference Occurrence to an older version.
    "delete_feature"  — remove a feature that exists only in the current document.
"""

from dataclasses import dataclass, asdict

import adsk.core
import adsk.fusion


@dataclass
class MergeResult:
    row_id: str
    ok: bool
    applied: int = 0
    failed: int = 0
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def apply_selections(design: adsk.fusion.Design, selections: list[dict]) -> list[MergeResult]:
    """Apply each selection to the active design.

    Selections are grouped and ordered for safety:
      1. parameter reverts first (don't touch the timeline structure)
      2. XREF version reverts next (replace external references in place)
      3. feature deletions last, sorted by timeline index descending
         (delete later items first to minimize cascading dependency errors)
    """
    param_sels = []
    xref_sels = []
    delete_sels = []
    other_sels = []

    for sel in selections:
        kind = sel.get("kind", "")
        if kind == "params":
            param_sels.append(sel)
        elif kind == "xref_version":
            xref_sels.append(sel)
        elif kind == "delete_feature":
            delete_sels.append(sel)
        else:
            other_sels.append(sel)

    results: list[MergeResult] = []

    for sel in param_sels:
        results.append(_apply_params(design, sel))

    for sel in xref_sels:
        results.append(_apply_xref_version(design, sel))

    delete_sels.sort(
        key=lambda s: (s.get("feature") or {}).get("index", 0),
        reverse=True,
    )
    for sel in delete_sels:
        results.append(_apply_delete_feature(design, sel))

    for sel in other_sels:
        results.append(MergeResult(
            row_id=sel.get("rowId", ""), ok=False,
            message=f"Unsupported merge kind: {sel.get('kind')!r}",
        ))

    return results


def _apply_params(design: adsk.fusion.Design, sel: dict) -> MergeResult:
    row_id = sel.get("rowId", "")
    params = sel.get("params") or []
    if not params:
        return MergeResult(row_id=row_id, ok=False, message="No parameter changes to apply")

    all_params = design.allParameters
    applied = 0
    errors: list[str] = []

    for p in params:
        name = p.get("name", "")
        expr = p.get("expression", "")
        if not name:
            errors.append("(missing parameter name)")
            continue

        param = all_params.itemByName(name)
        if param is None:
            errors.append(f"{name}: not found in current design")
            continue

        try:
            param.expression = expr
            applied += 1
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    ok = applied > 0 and not errors
    if errors:
        message = f"Applied {applied}, failed {len(errors)}: " + "; ".join(errors)
    else:
        message = f"Applied {applied} parameter{'s' if applied != 1 else ''}"

    return MergeResult(
        row_id=row_id, ok=ok,
        applied=applied, failed=len(errors),
        message=message,
    )


def _apply_xref_version(design: adsk.fusion.Design, sel: dict) -> MergeResult:
    row_id = sel.get("rowId", "")
    occurrence_name = sel.get("occurrence_name", "")
    target_version = sel.get("target_version", 0)

    if not occurrence_name:
        return MergeResult(row_id=row_id, ok=False, message="Missing occurrence name")
    try:
        target_version = int(target_version)
    except (TypeError, ValueError):
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Invalid target version: {target_version!r}",
        )
    if target_version <= 0:
        return MergeResult(row_id=row_id, ok=False, message="Target version must be positive")

    timeline = design.timeline
    target_item = None
    for i in range(timeline.count):
        item = timeline.item(i)
        if item.name == occurrence_name:
            target_item = item
            break

    if target_item is None:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Occurrence '{occurrence_name}' not found in current timeline",
        )

    try:
        occurrence = target_item.entity
    except RuntimeError:
        occurrence = None
    if occurrence is None:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Cannot resolve entity for '{occurrence_name}'",
        )

    # Confirm it's actually an external reference.
    try:
        if not getattr(occurrence, "isReferencedComponent", False):
            return MergeResult(
                row_id=row_id, ok=False,
                message=f"'{occurrence_name}' is not an external reference",
            )
    except Exception:
        pass

    # configuredDataFile gives the DataFile for the version currently in use;
    # from there we can walk versions and find the one we want.
    try:
        current_df = occurrence.configuredDataFile
    except (AttributeError, RuntimeError) as exc:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"configuredDataFile unavailable: {exc}",
        )
    if current_df is None:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"No DataFile for '{occurrence_name}'",
        )

    target_df = None
    try:
        versions = current_df.versions
        for i in range(versions.count):
            v = versions.item(i)
            if v.versionNumber == target_version:
                target_df = v
                break
    except Exception as exc:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Could not enumerate versions: {exc}",
        )

    if target_df is None:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"V{target_version} not found in source's version list",
        )

    try:
        # replaceAll=False — only this single occurrence, not every reference
        # of the same component.
        ok = occurrence.replace(target_df, False)
    except Exception as exc:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Occurrence.replace failed: {exc}",
        )
    if not ok:
        return MergeResult(
            row_id=row_id, ok=False,
            message="Occurrence.replace returned False",
        )

    return MergeResult(
        row_id=row_id, ok=True, applied=1,
        message=f"Reverted XREF to v{target_version}",
    )


def _apply_delete_feature(design: adsk.fusion.Design, sel: dict) -> MergeResult:
    row_id = sel.get("rowId", "")
    feature = sel.get("feature") or {}
    name = feature.get("name", "")

    if not name:
        return MergeResult(row_id=row_id, ok=False, message="Missing feature name")

    timeline = design.timeline
    target = None
    for i in range(timeline.count):
        item = timeline.item(i)
        if item.name == name:
            target = item
            break

    if target is None:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Feature '{name}' not found in current timeline",
        )

    try:
        entity = target.entity
    except RuntimeError:
        entity = None

    if entity is None:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Cannot resolve entity for '{name}'",
        )

    if not hasattr(entity, "deleteMe"):
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"'{name}' does not support delete",
        )

    try:
        entity.deleteMe()
    except Exception as exc:
        return MergeResult(
            row_id=row_id, ok=False,
            message=f"Could not delete '{name}': {exc}",
        )

    return MergeResult(
        row_id=row_id, ok=True, applied=1,
        message=f"Removed '{name}'",
    )
