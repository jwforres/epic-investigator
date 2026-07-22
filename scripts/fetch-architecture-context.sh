#!/bin/bash
# Fetches the latest RHOAI architecture context via sparse checkout.
# Safe to run multiple times — pulls updates if already cloned.

if [ -n "${EPIC_SKIP_BOOTSTRAP:-}" ]; then
  echo "EPIC_SKIP_BOOTSTRAP set - skipping dependency bootstrapping step"
  exit 0
fi

CONTEXT_DIR=".context/architecture-context"

# Pick the newest rhoai-* directory by *version order*, not lexical order.
# Lexical sort is wrong twice: 'rhoai-2.9' > 'rhoai-2.20' (string compare), and an
# '-ea.N' pre-release sorts after its GA. Parse the numeric version into an int
# tuple and rank GA above any pre-release of the same version.
LATEST=$(curl -sL https://api.github.com/repos/opendatahub-io/architecture-context/contents/architecture | python3 -c "
import sys, json, re
entries = json.load(sys.stdin)
names = [e['name'] for e in entries if e['name'].startswith('rhoai-')]
def key(n):
    body = n[len('rhoai-'):]
    m = re.match(r'([0-9]+(?:\.[0-9]+)*)(.*)', body)
    ver = tuple(int(p) for p in m.group(1).split('.')) if m else ()
    rest = (m.group(2) if m else body).lstrip('-.')
    is_ga = 1 if not rest else 0            # GA outranks any pre-release of same ver
    pre = tuple(int(p) if p.isdigit() else 0 for p in re.split(r'[.\-]', rest) if p)
    return (ver, is_ga, pre)
names.sort(key=key)
print(names[-1] if names else '')
")

if [ -z "$LATEST" ] || [ "$LATEST" = "null" ]; then
  echo "Could not detect latest architecture version"
  exit 1
fi

if [ -d "$CONTEXT_DIR" ]; then
  git -C "$CONTEXT_DIR" sparse-checkout set "architecture/$LATEST"
  git -C "$CONTEXT_DIR" pull --quiet
else
  git clone --depth 1 --filter=blob:none --sparse https://github.com/opendatahub-io/architecture-context "$CONTEXT_DIR"
  git -C "$CONTEXT_DIR" sparse-checkout set "architecture/$LATEST"
fi

echo "Architecture context ready: $CONTEXT_DIR/architecture/$LATEST"
