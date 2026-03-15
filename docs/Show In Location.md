# Show In Location

[Back to Readme](../README.md)

## Description

By default in Fusion, the Data Panel does not automatically reflect which document you are currently working in. The **Show In Location** feature automatically runs Fusion's built-in **Show In Location** command whenever a Fusion design document is opened or whenever you switch to a different document tab.

This keeps the Data Panel in sync with the active document at all times, without any manual action required.

## Behavior

- Fires automatically — there is no button or dialog.
- Triggers on two events:
  - **Document Opened** — when any Fusion design document finishes loading.
  - **Document Activated** — when you switch between open document tabs.
- Only acts on Fusion design documents. Non-design documents (drawings, etc.) are silently ignored.
- The root component is selected before the command runs, which is required for Show In Location to work correctly.
- Any errors are logged silently and do not interrupt your workflow.

## Access

This feature runs automatically in the background whenever the add-in is loaded. No user interaction is needed.

[Back to Readme](../README.md)
