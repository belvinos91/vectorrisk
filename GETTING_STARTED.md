# VectorRisk — Getting Started (step by step)

This guide takes you from the downloaded ZIP to a live dashboard with a link you
can share. No prior server experience assumed.

There are two parts:
- **Part 1–4**: run it on your own computer (Cursor) and see the dashboard.
- **Part 5–7**: put it on your server and get a public link for others.

---

## Part 0 — Install the tools you need (once)

1. **Cursor** — download from https://cursor.com and install.
2. **Miniconda** — download from https://www.anaconda.com/download/success
   (Miniconda is enough). This is what installs the mapping libraries (GDAL)
   reliably. Install it and accept "add to PATH" if asked.
3. (For the server later) an account/access to your Linux server via SSH, and
   optionally a **domain name**.

Check they work — open a terminal and run:
```bash
conda --version
```
You should see a version number.

---

## Part 1 — Open the project in Cursor

1. **Unzip** `vectorrisk_pkg.zip`. You now have a folder called `vectorrisk_pkg`.
2. Open **Cursor** → **File → Open Folder…** → select the `vectorrisk_pkg` folder.
3. Open the built-in terminal: **Terminal → New Terminal** (or press `` Ctrl+` ``).
   All commands below are typed into this terminal.

You should see files like `README.md`, `environment.yml`, `Dockerfile`, and a
`vectorrisk/` folder.

---

## Part 2 — Install the package

Run these one at a time in the Cursor terminal:

```bash
conda env create -f environment.yml
conda activate vectorrisk
```

- The first line reads `environment.yml` and installs Python + all the mapping,
  climate, and web libraries. It takes a few minutes.
- The second line "switches on" that environment. You'll see `(vectorrisk)` at
  the start of your terminal line. **Run it again every time you open a new
  terminal.**

Check it installed:
```bash
vectorrisk --help
```
You should see the list of commands: `serve, fetch, maps, metrics, incidence,
validate, panel, subpanel, check`.

> Windows note: run these in the **Anaconda Prompt** (search the Start menu) if
> `conda` isn't found in Cursor's terminal.

---

## Part 3 — Check the data links, then download the data

First, test that your internet can reach every data source:
```bash
vectorrisk check
```
You'll get an OK/FAIL list (WorldClim temperature/rainfall, boundaries, WHO,
TerraClimate, CHIRPS, MAP). If something says **FAIL**, it's usually a
firewall/proxy on your network — not the software.

Now download and cache the climate + country boundaries (first run only):
```bash
vectorrisk fetch --resolution 10m
```
- `10m` (~18 km) is fast and good to start.
- Use `--resolution 30s` later for 1 km (much larger download; be patient).

---

## Part 4 — Run it and view the dashboard

```bash
vectorrisk serve
```
Leave this running. Open your browser to:

- **http://127.0.0.1:8000/**  → the dashboard (it auto-connects to your live data)
- **http://127.0.0.1:8000/docs** → the API explorer (for developers)

In the dashboard you can: see the map and country risk, the 12-month tables
(download CSV/Excel), run Monte Carlo, Girsanov scenarios, multi-year
simulation, and the Validation tab. To stop the server, press `Ctrl+C` in the
terminal.

> If temperature/rainfall look empty: you either skipped `vectorrisk fetch`
> (Part 3) or `vectorrisk check` showed a FAIL on WorldClim. Fix that first.

**You now have the full project running locally.** Parts 5–7 make it public.

---

## Part 5 — Put the project on your server

Two ways. **Docker is easiest** because it bundles the mapping libraries.

### Option A — Docker (recommended)

On your **local** machine, copy the project to the server (replace user/host/path):
```bash
scp -r vectorrisk_pkg user@your-server-ip:/home/user/
```
(Or, if you use GitHub: push the folder to a repo and `git clone` it on the server.)

Then **SSH into the server** and build + run it:
```bash
ssh user@your-server-ip
cd vectorrisk_pkg

# install Docker once if needed:  https://docs.docker.com/engine/install/
docker build -t vectorrisk .
docker run -d --restart unless-stopped -p 8000:8000 \
  -v $PWD/cache:/app/vectorrisk_cache --name vectorrisk vectorrisk
```
- `-d` runs it in the background, `--restart unless-stopped` keeps it alive after
  reboots, `-v …/cache` keeps downloaded data between restarts.

Check it's alive:
```bash
curl http://127.0.0.1:8000/health      # -> {"status":"ok",...}
```
Download the data inside the container (first time):
```bash
docker exec vectorrisk vectorrisk fetch --resolution 10m
```

### Option B — no Docker (conda + a service)

```bash
ssh user@your-server-ip
cd vectorrisk_pkg
conda env create -f environment.yml && conda activate vectorrisk
vectorrisk fetch --resolution 10m
```
Keep it running permanently with a systemd service. Create
`/etc/systemd/system/vectorrisk.service`:
```ini
[Unit]
Description=VectorRisk API + dashboard
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/vectorrisk_pkg
ExecStart=/home/YOUR_USER/miniconda3/envs/vectorrisk/bin/vectorrisk serve --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```
Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vectorrisk
```

---

## Part 6 — Generate the link people can open

### Best for donors/WHO: your domain + HTTPS (permanent, professional)

1. Point your domain's DNS **A record** (e.g. `vectorrisk.example.org`) to your
   server's IP.
2. Install nginx and create `/etc/nginx/sites-available/vectorrisk`:
```nginx
server {
    server_name vectorrisk.example.org;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```
3. Enable it and add free HTTPS:
```bash
sudo ln -s /etc/nginx/sites-available/vectorrisk /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d vectorrisk.example.org
```
Now share: **https://vectorrisk.example.org/** — anyone can open the dashboard.

### Quick demo, no server config (temporary link)

On any machine where it's running:
```bash
# install once:  https://github.com/cloudflare/cloudflared
cloudflared tunnel --url http://localhost:8000
```
It prints a public `https://…trycloudflare.com` URL. Send that to people. (This
link lasts while the command runs — good for a live demo, not for production.)

---

## Part 7 — Before you sell it (important)

1. **Boundary licence.** GADM is non-commercial. In `vectorrisk/config.py` set:
   ```python
   ADMIN_SOURCE = "geoboundaries"     # CC BY 4.0 — commercial OK
   ```
2. **Lock down access.** In `vectorrisk/api.py`, change
   `allow_origins=["*"]` to your domain, and consider putting the heavy
   `/pipeline*` and `/validate/subnational-panel` routes behind a password.
3. **Attribute sources** in your product (WorldClim, TerraClimate, CHIRPS, WHO,
   geoBoundaries, MAP). Run `vectorrisk check` to see each licence.

---

## Daily use cheat-sheet

```bash
conda activate vectorrisk      # every new terminal
vectorrisk check               # are the data links up?
vectorrisk fetch --resolution 10m   # (once) download climate + boundaries
vectorrisk serve               # run API + dashboard -> http://127.0.0.1:8000/
vectorrisk metrics 27 150      # quick model output for T=27C, R=150mm
vectorrisk panel --years 2001 2020   # country-year validation panel
```

Stuck on any step? Note which command failed and its exact message — that's
enough to pin down the fix.
