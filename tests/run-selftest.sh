#!/usr/bin/env bash
# Regression check: serve a deliberately broken fixture site and assert that the
# marketplace detects the defects that were built into it. Guards against the
# opposite failure to false positives — checks quietly ceasing to fire.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT=${PORT:-8731}
OUT=$(mktemp -d)

python3 -m http.server "$PORT" --directory "$ROOT/tests/fixture-site" >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
sleep 1

python3 "$ROOT/skills/audit-orchestrator/scripts/run_audit.py" "http://localhost:$PORT" \
    --out "$OUT" --max-pages 8 --delay 0 --budget 60 --render off >/dev/null 2>&1

EXPECTED=(
  CA-AI-RETRIEVAL-BLOCKED CA-SITEMAP-MISSING CA-NOINDEX-ON-CONTENT CA-NOSNIPPET
  CA-CANONICAL-TO-HOMEPAGE RX-CLIENT-RENDERED-SHELL RX-FACTS-LOCKED-IN-IMAGES
  RX-TABBED-CONTENT-NOT-IN-HTML RX-CONTENT-IN-IFRAME RX-NO-QUOTABLE-DEFINITION
  RX-CONTACT-DETAILS-NOT-IN-TEXT RX-MULTIPLE-H1 SD-NONE CF-STALE-COPYRIGHT
  CF-UNSOURCED-CLAIMS CF-NO-OFFSITE-ANCHORS EN-NO-VIEWPORT-META
  EN-INTERRUPTING-OVERLAY EN-ACCESSIBILITY-BASELINE EN-GATED-FACTS
  SA-DEAD-END-PAGES AQ-NO-QUESTION-CONTENT AQ-NO-COMPARISON-CONTENT
  AQ-NO-OBJECTION-HANDLING TL-NO-LEGAL-PAGES-LINKED
  DC-DUPLICATE-TITLE-OR-DESCRIPTION DC-PARAM-VARIANT-NOT-CANONICALIZED
)
FOUND=$(python3 -c "
import json,sys
r=json.load(open('$OUT/report.json'))
ids={f['check_id'] for f in r['findings']}
ids|={n['check_id'] for n in r['checks_not_applicable']}   # folded into a cause
print(' '.join(sorted(ids)))")

fail=0
for id in "${EXPECTED[@]}"; do
  case " $FOUND " in
    *" $id "*) ;;
    *) echo "MISSING: $id"; fail=1;;
  esac
done
python3 -c "
import json
r=json.load(open('$OUT/report.json'))
s=r['summary']
print('findings: %d (crit %d, high %d, med %d, low %d)  discoverability %d  engagement %d'
      % (s['total_findings'],s['critical'],s['high'],s['medium'],s['low'],
         s['ai_discoverability_score'],s['on_site_engagement_score']))"
[ $fail -eq 0 ] && echo "PASS: every seeded defect was detected" || echo "FAIL: see MISSING above"
exit $fail
