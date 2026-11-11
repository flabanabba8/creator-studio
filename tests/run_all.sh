#!/bin/sh
# Run every test of the suite. Needs the Hermes Python (for plugins.plugin_storage, fastapi) and ffmpeg.
# Usage: HERMES_HOME=$(mktemp -d) PYTHONPATH=/path/to/hermes-agent /path/to/hermes-python tests/run_all.sh
PY=${PYTHON:-python3}
cd "$(dirname "$0")/.." || exit 1
rc=0
$PY -m unittest discover -s tests -p 'test_register.py' || rc=1
for part in youtube_studio podcast_studio caption_studio tutorial_creator; do
  (cd "$part" && $PY -m unittest discover -s tests) || rc=1
done
exit $rc
