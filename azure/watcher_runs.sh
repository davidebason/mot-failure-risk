#!/usr/bin/env bash
# Every run of the watcher, the Azure Function func-motrisk, from its Application Insights record:
# when it started, whether it succeeded, how long it took, and what it logged about the files it
# landed. Written to the file named as the first argument. Run from the repository's root, logged
# in with az login:
#
#     bash azure/watcher_runs.sh data/watcher_runs_2026-11-18.log
set -euo pipefail
OUT=${1:?output file}
QUERY="requests
| where name has 'scheduler'
| join kind=leftouter (
    traces
    | where message startswith 'uploaded' or severityLevel >= 3
    | summarize messages = strcat_array(make_list(message), '; ') by operation_Id
  ) on operation_Id
| project timestamp, success, seconds = round(duration / 1000, 1), messages
| order by timestamp asc"
{
  date -u +"written %F %T UTC from Application Insights func-motrisk"
  printf "started\tsucceeded\tseconds\tlogged\n"
  az monitor app-insights query -g rg-mot-failure-risk --app func-motrisk --offset 30d \
    --analytics-query "$QUERY" -o json \
    | python3 -c 'import json, sys; [print(*r, sep="\t") for r in json.load(sys.stdin)["tables"][0]["rows"]]'
} > "$OUT"
echo "$(($(wc -l < "$OUT") - 2)) runs written to $OUT"
