# PowerTools: New Documents for Autodesk Fusion

PowerTools New Documents is an Autodesk Fusion add-in that improves productivity when working with cloud data, team projects, and multi-document assemblies. It adds commands that surface actions that are otherwise buried in menus or difficult to discover.

## Prerequisites

Before you install and run this add-in, confirm that you have the following:

- **Autodesk Fusion** (any current subscription tier) with Python add-in support enabled
- **Windows 10/11** or **macOS**
- An **Autodesk Team Hub** (required for commands that access cloud project and folder data)

## Installation

1. Download or clone this repository to your local machine.
2. In Autodesk Fusion, open the **Add-Ins** dialog by selecting **Utilities** > **Add-Ins**, or press **Shift+S**.
3. On the **Add-Ins** tab, click the green **+** icon.
4. Navigate to the folder where you placed the add-in files and select the `PowerTools-New-Documents` folder.
5. Click **Open**.
6. Select **PowerTools New Documents** in the list, then click **Run**.

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

#### [Recovery Save](./docs/Recovery%20Save.md)

Adds a **Recovery Save** entry to the QAT File dropdown that writes a local recovery checkpoint for the active document without creating a new cloud version or notifying collaborators.

---

### Automation

#### [Show In Location](./docs/Show%20In%20Location.md)

Automatically runs Fusion's built-in Show In Location command whenever a design document is opened or you switch document tabs, keeping the Data Panel synchronized with the active document at all times. Requires no user interaction.

---

## Architecture

PowerTools New Documents is structured as a standard Fusion Python add-in. Each command is an independent module under the `commands/` directory that exposes `start()` and `stop()` functions. The top-level `commands/__init__.py` collects all command modules into a list and delegates lifecycle calls to them.

```mermaid
C4Context
    title PowerTools New Documents – System Context

    Person(user, "Designer", "Fusion user working with cloud data and design documents")
    System(addin, "PowerTools New Documents", "Fusion Python add-in. Registers commands that extend the Fusion UI for improved data and project management.")
    System_Ext(fusion, "Autodesk Fusion", "Cloud-connected 3D CAD application. Provides the API surface, UI framework, and data platform.")
    System_Ext(fusionCloud, "Fusion Industry Cloud", "Autodesk cloud data platform. Stores hubs, projects, folders, and document versions.")

    Rel(user, addin, "Uses commands via QAT, Navigation Toolbar, and Tools tab")
    Rel(addin, fusion, "Registers command definitions and controls via Fusion API")
    Rel(fusion, fusionCloud, "Reads and writes document and project data")
```

### Module structure

| Module | Command | UI location |
|---|---|---|
| `commands/autosave/` | Recovery Save | QAT → File dropdown |
| `commands/datatoggle/` | Toggle Data Pane | Navigation Toolbar |
| `commands/defaultfolders/` | Add Default Project Folders | QAT → File dropdown |
| `commands/dochistory/` | Document History | QAT |
| `commands/docinfo/` | Document Information | Design workspace → Tools tab → Power Tools panel |
| `commands/docopen/` | Show In Location | Automatic – no UI control |

---

## Support

This add-in is developed and maintained by IMA LLC.

---

## License

This project is released under the [MIT License](LICENSE).

---

*Copyright © 2026 IMA LLC. All rights reserved.*
