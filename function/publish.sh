#!/usr/bin/env bash
# Deploy this folder to the Function App func-motrisk, from any directory.
#
# Azure receives only this folder, so the motrisk package is copied in first, fresh at every
# deployment: the code that runs in Azure is then the code in src/ that the tests check.
# The copy is gitignored.
set -euo pipefail

cd "$(dirname "$0")"
rm -rf motrisk
cp -r ../src/motrisk motrisk
func azure functionapp publish func-motrisk --python
