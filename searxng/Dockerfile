FROM docker.io/searxng/searxng:latest

COPY settings.yml /etc/searxng/settings.yml
COPY patch_pinterest_engine.py /tmp/patch_pinterest_engine.py
RUN python /tmp/patch_pinterest_engine.py && rm /tmp/patch_pinterest_engine.py
