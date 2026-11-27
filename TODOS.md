# TODOS

## App

### Single-instance window

**What:** A second `presence-guard ui` launch brings the running window to the front (and applies its `--since`) instead of opening another window.

**Why:** Clicking two notifications, or opening the app from the menu while it is open, gives duplicate windows.

**Context:** Accepted as a v1 limit in the design (docs/designs/wrong-password-photos-app.md, Open Questions). Start in `pg/ui.py` `main()`: try `QLocalSocket.connectToServer("presence-guard")`; if it connects, send the `--since` value and exit; otherwise start a `QLocalServer` with that name and raise the window on each message.

**Effort:** S
**Priority:** P3
**Depends on:** None
