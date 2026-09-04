#!/bin/sh
set -e

# On a brand-new Fly volume /app/data starts empty -- reseed the demo
# topic content and sample assets from the image so the app isn't blank
# on first boot. Once real content/asset files exist there, this is a
# no-op forever (never overwrites what's already on the volume).
mkdir -p /app/data
if [ ! -d /app/data/topics ]; then
  cp -r /app/seed-data/topics /app/data/topics
fi
if [ ! -d /app/data/assets ]; then
  cp -r /app/seed-data/assets /app/data/assets
fi

exec "$@"
