#!/usr/bin/env python3
import os, sys
MODE = (os.environ.get("MODE") or "router").strip().lower()
if MODE == "panel":
    import storm_panel_site as M
else:
    import storm_router_site as M
if __name__ == "__main__":
    M.main()
