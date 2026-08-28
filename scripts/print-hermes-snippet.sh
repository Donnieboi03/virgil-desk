#!/usr/bin/env bash
# Print Hermes skills.external_dirs snippet for this repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS="${ROOT}/skills"
cat <<EOF
# Add to ~/.hermes/profiles/<profile>/config.yaml
skills:
  external_dirs:
    - ${SKILLS}
EOF
