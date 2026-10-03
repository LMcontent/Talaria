# See README.md's "Running in Docker" section for how to build/run this,
# what it changes vs. the non-Docker setup, and what still needs your own
# .env.
FROM python:3.11-slim

# Playwright installs Chromium to this fixed path instead of the
# installing user's home (~/.cache/ms-playwright) — the browser is still
# reachable after USER switches to a non-root account below.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installs Chromium itself plus every OS package it needs to actually
# launch headless (fonts, graphics libs, ...) via --with-deps — this is
# what makes the image several hundred MB bigger than a plain Python
# image, the one-time build-time cost that replaces the README's
# `playwright install chromium` step for a non-Docker setup.
RUN playwright install --with-deps chromium

COPY . .

# Chromium's own internal sandboxing refuses to launch as root without
# --no-sandbox, which talaria/tools/browser.py deliberately doesn't pass
# (weakening that for every user, Docker or not, just to suit a container
# default isn't worth it) — running as a non-root user here sidesteps the
# conflict entirely instead. WORKSPACE_DIR is created (and owned by this
# user) before the VOLUME line below so a named volume Docker creates at
# that mount point inherits the right ownership instead of defaulting to
# root.
RUN useradd --create-home --uid 1000 talaria \
    && mkdir -p /data/workspace \
    && chown -R talaria:talaria /app /opt/pw-browsers /data/workspace
USER talaria

# Everything persistent (conversation history/chats, notes, goals, cron
# jobs, skill state, the run_python sandbox venv, browser login state,
# screenshots) lives under WORKSPACE_DIR — declared as a volume so data
# survives a `docker run`/compose without an explicit mount, instead of
# vanishing the moment the container is removed.
ENV WORKSPACE_DIR=/data/workspace
VOLUME ["/data/workspace"]

# 127.0.0.1 (the non-Docker default — see README) would make the web UI
# unreachable from outside this container; 0.0.0.0 plus Docker's own port
# publishing is what actually exposes it, still only to whatever port you
# choose to publish.
ENV WEB_HOST=0.0.0.0
ENV WEB_PORT=5000
ENV BROWSER_HEADLESS=true

EXPOSE 5000

CMD ["python", "-m", "talaria.web"]
