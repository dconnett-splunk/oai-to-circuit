#!/bin/bash
# View recent individual requests from logs

TIMEFRAME="${1:-1 hour ago}"

echo "=== Recent API Requests (since $TIMEFRAME) ==="
echo ""

sudo journalctl -u oai-to-circuit --since "$TIMEFRAME" | \
  grep "Sending usage event" | \
  sed 's/.*Sending usage event to Splunk HEC: //' | \
  jq -r '
    ["Timestamp", "User", "Model", "Prompt", "Completion", "Total", "Status"],
    (.timestamp[0:19], .subkey[0:20] + "***", .model, .prompt_tokens, .completion_tokens, .total_tokens, .status_code) | 
    @tsv
  ' | column -t -s $'\t'

echo ""
echo "Total requests:"
sudo journalctl -u oai-to-circuit --since "$TIMEFRAME" | \
  grep -c "Sending usage event"

