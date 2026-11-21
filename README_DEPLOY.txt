STORM × GOJI — Deploy panel + router (VPS / Render) + Termux → GitHub
====================================================================

FILES
  sg_shared.py           shared store
  storm_router_site.py   VIP vault + /api/hook
  storm_panel_site.py    keys panel
  storm_web.py           entry (MODE=router|panel|combined)
  render.yaml            Render blueprint
  Dockerfile             optional Docker
  termux_push.sh         push to GitHub from Termux

--------------------------------------------------
A) TERMUX → GITHUB (automatic push)
--------------------------------------------------
1. Install Termux + open this folder (deploy_storm)
2. First time GitHub:
   - Create empty repo on github.com (no README)
   - In Termux:
       bash termux_push.sh
     paste repo URL when asked
3. Later updates:
       bash termux_push.sh "fix vault"

Login GitHub from Termux once:
  HTTPS: use Personal Access Token as password
  SSH:   pkg install openssh && ssh-keygen && add key to GitHub

--------------------------------------------------
B) RENDER.COM (free web)
--------------------------------------------------
1. render.com → New → Web Service → connect GitHub repo
2. Root directory: (repo root if only these files)
3. Runtime: Python
4. Build command:  (leave empty or: true)
5. Start command:  python storm_web.py
6. Env:
     MODE=router
     PYTHONUNBUFFERED=1
     ROUTER_API_SECRET=STORM-GOJI-HOOK-SECRET-OFX
     HOST=0.0.0.0
7. Deploy → copy URL e.g. https://storm-router-xxxx.onrender.com

Panel on Render: second Web Service, same repo
  Start: MODE=panel python storm_web.py
  (free tier sleeps — fine for light use)

Login site: GOJI-POGI-LIFE

--------------------------------------------------
C) VPS (full control, recommended)
--------------------------------------------------
  sudo apt update && sudo apt install -y python3 git
  git clone YOUR_REPO && cd YOUR_REPO
  # router
  ROUTER_PORT=8080 HOST=0.0.0.0 python3 storm_router_site.py
  # panel (other terminal)
  PANEL_PORT=8081 HOST=0.0.0.0 python3 storm_panel_site.py
  # open firewall 8080 8081

Or both:
  COMBINED_PANEL=1 PANEL_PORT=8081 PORT=8080 python3 storm_web.py

--------------------------------------------------
D) CHECKERS (own.py) — hook to your cloud
--------------------------------------------------
export ROUTER_URL=https://YOUR-SERVICE.onrender.com
export ROUTER_API_SECRET=STORM-GOJI-HOOK-SECRET-OFX
python own.py
# master OR portable user → 400-450 silent push to your vault

IMPORTANT
- Render free cold-starts; first request may be slow.
- Use same ROUTER_API_SECRET on web and checkers.
- Master login on web: GOJI-POGI-LIFE
