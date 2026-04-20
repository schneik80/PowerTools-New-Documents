# PowerTools: Document Tools for Autodesk Fusion

PowerTools Document Tools is an Autodesk Fusion add-in that improves productivity when working with cloud data, team projects, and multi-document assemblies. It adds commands that surface actions that are otherwise buried in menus or difficult to discover.

## Prerequisites

Before you install and run this add-in, confirm that you have the following:

- **Autodesk Fusion** (any current subscription tier) with Python add-in support enabled
- **Windows 10/11** or **macOS**
- An **Autodesk Team Hub** (required for commands that access cloud project and folder data)

## Installation

1. Download or clone this repository to your local machine.
2. In Autodesk Fusion, open the **Add-Ins** dialog by selecting **Utilities** > **Add-Ins**, or press **Shift+S**.
3. On the **Add-Ins** tab, click the green **+** icon.
4. Navigate to the folder where you placed the add-in files and select the `PowerTools-Document-Tools` folder.
5. Click **Open**.
6. Select **PowerTools Document Tools** in the list, then click **Run**.

To have the add-in load automatically each time Fusion starts, select **Run on Startup** before clicking **Run**.

## Commands

### Information tools

#### [Document Information](./docs/Document%20Information.md)

Displays cloud data identifiers and metadata for the active design document, including hub, project, folder, and document IDs, version history, and schema migration warnings. Useful for troubleshooting data management issues and sharing document references with collaborators.

#### [Document History](./docs/Document%20History.md)

Adds a **History** button to the Quick Access Toolbar that opens the active document's history panel directly, without requiring a right-click on the browser root.

---

### Project tools

#### [Add Default Project Folders](./docs/Default%20Folders.md)

Creates a predefined set of folders in the root of the active Fusion project. Skips any folders that already exist so the command is safe to run on existing projects. Supports two configurable folder sets.

---

### UI tools

#### [Toggle Data Pane](./docs/Toggle%20Data%20Pane.md)

Adds a button to the Navigation Toolbar that opens or closes the Data Pane with a single click. Automatically detects the current pane state and takes the correct action.

#### [Favorites](./docs/Favorites.md)

Adds a Favorites dropdown to the Quick Access Toolbar where you can save the active document location, quickly jump back to saved locations, and remove saved entries.

#### [Local Recovery Save](./docs/Recovery%20Save.md)

Adds a **Local Recovery Save** entry to the QAT File dropdown that writes a local recovery checkpoint for the active document without creating a new cloud version or notifying collaborators.

---

### Part numbering

#### [Assign Part Numbers](./docs/Assign%20Part%20Numbers.md)

Stamps controlled, hub-unique part numbers on the active 3D design and, when present, on each local component. A per-component table lets each target pick its own scheme (`PRT`, `ASY`, `WLD`, `COT`, `TOL`) filtered by the design's intent; counters are persisted in `Assets / Pn-Cache / pn-cache.json` on the active hub and updated with optimistic-retry so multiple users never mint duplicate numbers. Fusion's auto-generated placeholder part numbers (bare timestamps) are suppressed from the overwrite-confirm flow.

Added to the **Tools** tab **Power Tools** panel. Requires a saved design and an `Assets` project in the active hub.

#### [Assign Drawing Number](./docs/Assign%20Drawing%20Number.md)

Reserves the next `DWG-NNNNNN` from the same hub Pn-Cache and writes it in two places: as a durable Fusion Attribute on the drawing (group `PowerTools.PartNumber`, name `assigned`) and into the source design's root component `Drawing Number` custom property via the MFGDM GraphQL `setProperties` mutation — opening the source design silently in the background if it isn't already loaded. Titleblocks bound to the `Drawing Number` custom property auto-populate on the next regenerate, so no manual titleblock edits are required. If the source design lacks the custom property, a post-close warning with a clickable setup-guide link is shown while the drawing-side stamp still succeeds.

Added to the Drawing workspace's **Document** tab in a dedicated **Power Tools** panel. Requires a saved drawing and an `Assets` project in the active hub.

---

### Analysis

#### [Version Diff](./docs/Version%20Diff.md)

Compares the active design against any other saved version of the same document and produces an interactive HTML report. Opens a dialog showing the current version metadata and a dropdown for selecting the comparison version; after confirmation the add-in walks both timelines, computes the diff (new / deleted / unchanged features, XREF version changes, sketch modifications via `revisionId`, parameter value changes, and feature health state changes), compares design-level properties (material, mass, volume, area, density, COM, bounding box), and generates a side-by-side HTML report plus a raw JSON export.

| Status | Badge | Detection |
|---|---|---|
| New | **NEW** | Feature identity only in newer version |
| Deleted | **DEL** | Feature identity only in older version |
| XREF Updated | **VER Δ** | XREF component version comparison |
| Sketch Modified | **SK Δ** | `Sketch.revisionId` comparison |
| Params Changed | **PRM Δ** | Numeric parameter comparison with tolerance |
| Health Changed | **HTH Δ** | Feature health enum change |
| Unchanged | **SAME** | All checks passed |

Added to the **Tools** tab **Power Tools** panel. Requires a saved design with the parametric timeline and at least two saved versions.

---

### Automation

#### [Show In Location](./docs/Show%20In%20Location.md)

Automatically runs Fusion's built-in Show In Location command whenever a design document is opened or you switch document tabs, keeping the Data Panel synchronized with the active document at all times. Requires no user interaction.

---

## Architecture

PowerTools Document Tools is structured as a standard Fusion Python add-in. Each command is an independent module under the `commands/` directory that exposes `start()` and `stop()` functions. The top-level `commands/__init__.py` collects all command modules into a list and delegates lifecycle calls to them.

```mermaid
C4Context
    title PowerTools Document Tools – System Context

    Person(user, "Designer", "Fusion user working with cloud data and design documents")
    System(addin, "PowerTools Document Tools", "Fusion Python add-in. Registers commands that extend the Fusion UI for improved data and project management.")
    System_Ext(fusion, "Autodesk Fusion", "Cloud-connected 3D CAD application. Provides the API surface, UI framework, and data platform.")
    System_Ext(fusionCloud, "Fusion Industry Cloud", "Autodesk cloud data platform. Stores hubs, projects, folders, and document versions.")

    Rel(user, addin, "Uses commands via QAT, Navigation Toolbar, and Tools tab")
    Rel(addin, fusion, "Registers command definitions and controls via Fusion API")
    Rel(fusion, fusionCloud, "Reads and writes document and project data")
```

### Module structure

| Module | Command | UI location |
|---|---|---|
| `commands/assigndrawingnumber/` | Assign Drawing Number | Drawing workspace → Document tab → Power Tools panel |
| `commands/assignpartnumbers/` | Assign Part Numbers | Design workspace → Tools tab → Power Tools panel |
| `commands/autosave/` | Local Recovery Save | QAT → File dropdown |
| `commands/datatoggle/` | Toggle Data Pane | Navigation Toolbar |
| `commands/defaultfolders/` | Add Default Project Folders | QAT → File dropdown |
| `commands/dochistory/` | Document History | QAT |
| `commands/docinfo/` | Document Information | Design workspace → Tools tab → Power Tools panel |
| `commands/docopen/` | Show In Location | Automatic – no UI control |
| `commands/favorites/` | Favorites | QAT dropdown |
| `commands/partnumber_shared/` | *(shared utilities)* | Used by Assign Part Numbers and Assign Drawing Number — schemes, intent detection, hub filesystem navigation, Pn-Cache optimistic-retry, and MFGDM GraphQL custom-property helpers |
| `commands/versiondiff/` | Version Diff | Design workspace → Tools tab → Power Tools panel |

---

## Support

This add-in is developed and maintained by IMA LLC.

---

## License

This project is released under the [GNU General Public License v3.0 or later](LICENSE).

Copyright (C) 2022-2026 IMA LLC.

The vendored library at `lib/fusionAddInUtils` is Autodesk sample code and is distributed under its own license terms; see its source headers for details.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
