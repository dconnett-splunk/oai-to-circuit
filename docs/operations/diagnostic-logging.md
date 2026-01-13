# Diagnostic Logging Guide - Phase 1

This guide explains how to use the diagnostic logging added in Phase 1 to analyze Circuit API responses.

## What Was Added

New diagnostic logging in `oai_to_circuit/app.py` that captures:

1. **Request Type Detection**
   - `[REQUEST TYPE]` - Logs whether request is streaming or non-streaming

2. **Circuit API Response Headers**
   - `[CIRCUIT RESPONSE]` - Status code, content-type, all headers
   - `[CIRCUIT RATE LIMITS]` - Any rate limit headers (if present)

3. **Response Content Logging**
   - `[STREAMING RESPONSE]` - Detected streaming responses with raw content preview
   - `[NON-STREAMING RESPONSE]` - Full JSON response for non-streaming

4. **Token Extraction Details**
   - `[TOKEN EXTRACTION]` - Success/failure details
   - Now logs warnings instead of silently failing
   - Shows why token extraction failed (content-type, missing fields, parse errors)

## How to Enable Diagnostic Logging

### In Production (systemd service)

1. Edit the credentials file:
   ```bash
   sudo vi /etc/oai-to-circuit/credentials.env
   ```

2. Add or update the LOG_LEVEL variable:
   ```bash
   LOG_LEVEL=DEBUG
   ```

3. Restart the service:
   ```bash
   sudo systemctl restart oai-to-circuit
   ```

4. Watch the logs:
   ```bash
   sudo journalctl -u oai-to-circuit -f
   ```

### Local Testing

1. Set environment variable:
   ```bash
   export LOG_LEVEL=DEBUG
   ```

2. Run the test script:
   ```bash
   python test_diagnostic_logging.py
   ```

3. Or run the server:
   ```bash
   python rewriter.py
   ```

## What to Look For

### 1. Rate Limit Headers

Look for log lines like:
```
[CIRCUIT RATE LIMITS] {'x-ratelimit-remaining-requests': '1000', 'x-ratelimit-limit-requests': '10000'}
```

If you see "No rate limit headers found", the Circuit API doesn't provide rate limiting information.

### 2. Streaming Response Format

For streaming requests, look for:
```
[STREAMING RESPONSE] Detected streaming response
[STREAMING RESPONSE] Raw content preview (first 1000 bytes): data: {"choices":[...]...
```

This shows the actual SSE format Circuit uses.

### 3. Token Usage Location

For streaming responses with `tokens=0`, check:
- Does the response include a `usage` field at all?
- Is it in the final chunk of the stream?
- What does the raw content look like?

### 4. Non-Streaming Responses

Look for:
```
[NON-STREAMING RESPONSE] Full JSON response: {"id":"...", "choices":[...], "usage":{...}}
```

This shows the complete response structure.

### 5. Token Extraction Failures

If tokens are 0, look for:
```
[TOKEN EXTRACTION] Failed to extract token usage from response: ...
[TOKEN EXTRACTION] Response body that failed to parse: ...
```

Or:
```
[TOKEN EXTRACTION] Skipped - Content-Type: text/event-stream, has_content: True
```

This tells you WHY tokens weren't extracted.

## Test Cases

### Test 1: Non-Streaming Request

```bash
curl -X POST http://localhost:12000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-subkey" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

Expected logs:
- `[REQUEST TYPE] Streaming request: False`
- `[NON-STREAMING RESPONSE]` with full JSON
- `[TOKEN EXTRACTION] Successfully extracted tokens: ...`

### Test 2: Streaming Request

```bash
curl -X POST http://localhost:12000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-subkey" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

Expected logs:
- `[REQUEST TYPE] Streaming request: True`
- `[STREAMING RESPONSE] Detected streaming response`
- `[TOKEN EXTRACTION] Skipped - Content-Type: text/event-stream, has_content: True`

## Data Collection Checklist

After running a few test requests in production, document:

- [ ] Does Circuit API return rate limit headers?
  - If yes, what are the header names?
  - Example values?

- [ ] What does streaming response format look like?
  - Is it SSE (Server-Sent Events)?
  - Does it include `data:` prefixes?
  - Where does usage info appear?
  - Is there a `[DONE]` marker?

- [ ] What does non-streaming response include?
  - Does it have a `usage` field?
  - Token counts present?

- [ ] Any unexpected errors or warnings?
  - Document them here

## Next Steps

Once you've collected this data:

1. **Analyze the logs** - Look for the patterns above
2. **Document findings** - Note what Circuit API actually returns
3. **Proceed to Phase 2** - Implement stream parsing, rate limits, and cost tracking based on actual data

## Turning Off Debug Logging

After collecting diagnostic data, return to normal logging:

```bash
sudo vi /etc/oai-to-circuit/credentials.env
# Change LOG_LEVEL=DEBUG to LOG_LEVEL=INFO
sudo systemctl restart oai-to-circuit
```

## Files Modified

- `oai_to_circuit/app.py` - Added diagnostic logging
- `test_diagnostic_logging.py` - Test script for local verification
- This guide - `DIAGNOSTIC_LOGGING_GUIDE.md`

