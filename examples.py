#!/usr/bin/env python3
"""
Examples showing expected request formats and responses.
"""

import httpx
import json
import asyncio
from datetime import datetime

# Server configuration
BASE_URL = "http://localhost:12000"

# Example requests and expected responses
EXAMPLES = [
    {
        "name": "Simple Chat Completion",
        "description": "Basic OpenAI-style chat completion request",
        "request": {
            "url": f"{BASE_URL}/v1/chat/completions",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer any_key_here"  # This is ignored by bridge
            },
            "body": {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "What is 2+2?"}
                ]
            }
        },
        "expected_response": {
            "status": 200,
            "body_structure": {
                "id": "chat-<id>",
                "object": "chat.completion",
                "created": "<timestamp>",
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "2 + 2 equals 4."
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": "<number>",
                    "completion_tokens": "<number>",
                    "total_tokens": "<number>"
                }
            }
        }
    },
    {
        "name": "Streaming Chat Completion",
        "description": "Streaming response using Server-Sent Events",
        "request": {
            "url": f"{BASE_URL}/v1/chat/completions",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": {
                "model": "gpt-4o",
                "messages": [
                    {"role": "user", "content": "Tell me a short story"}
                ],
                "stream": True
            }
        },
        "expected_response": {
            "status": 200,
            "headers": {
                "Content-Type": "text/event-stream"
            },
            "body_format": "Server-Sent Events stream",
            "example_chunks": [
                'data: {"choices":[{"delta":{"role":"assistant","content":"Once"},"index":0}]}',
                'data: {"choices":[{"delta":{"content":" upon"},"index":0}]}',
                'data: {"choices":[{"delta":{"content":" a"},"index":0}]}',
                'data: [DONE]'
            ]
        }
    },
    {
        "name": "With Temperature and Max Tokens",
        "description": "Request with additional parameters",
        "request": {
            "url": f"{BASE_URL}/v1/chat/completions",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": {
                "model": "gpt-4.1",
                "messages": [
                    {"role": "user", "content": "Write a haiku about coding"}
                ],
                "temperature": 0.8,
                "max_tokens": 50,
                "top_p": 0.9
            }
        }
    },
    {
        "name": "Multi-turn Conversation",
        "description": "Conversation with history",
        "request": {
            "url": f"{BASE_URL}/v1/chat/completions",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a math tutor."},
                    {"role": "user", "content": "What is calculus?"},
                    {"role": "assistant", "content": "Calculus is a branch of mathematics..."},
                    {"role": "user", "content": "Can you give me an example?"}
                ]
            }
        }
    }
]


def print_example(example):
    """Pretty print an example request/response."""
    print(f"\n{'=' * 70}")
    print(f"EXAMPLE: {example['name']}")
    print(f"Description: {example['description']}")
    print(f"{'=' * 70}")
    
    req = example['request']
    print(f"\nREQUEST:")
    print(f"  Method: {req['method']}")
    print(f"  URL: {req['url']}")
    print(f"  Headers:")
    for k, v in req.get('headers', {}).items():
        print(f"    {k}: {v}")
    print(f"  Body:")
    print(json.dumps(req['body'], indent=4))
    
    if 'expected_response' in example:
        resp = example['expected_response']
        print(f"\nEXPECTED RESPONSE:")
        print(f"  Status: {resp['status']}")
        if 'headers' in resp:
            print(f"  Headers:")
            for k, v in resp['headers'].items():
                print(f"    {k}: {v}")
        if 'body_structure' in resp:
            print(f"  Body Structure:")
            print(json.dumps(resp['body_structure'], indent=4))
        if 'body_format' in resp:
            print(f"  Body Format: {resp['body_format']}")
        if 'example_chunks' in resp:
            print(f"  Example Stream Chunks:")
            for chunk in resp['example_chunks']:
                print(f"    {chunk}")


def print_curl_examples():
    """Print curl command examples."""
    print(f"\n{'=' * 70}")
    print("CURL COMMAND EXAMPLES")
    print(f"{'=' * 70}")
    
    print("\n1. Basic chat completion:")
    print("""curl -X POST http://localhost:12000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ]
  }'""")
    
    print("\n2. With authorization header (ignored but can be included):")
    print("""curl -X POST http://localhost:12000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer sk-any-key-here" \\
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is the weather like?"}
    ],
    "temperature": 0.7
  }'""")
    
    print("\n3. Streaming response:")
    print("""curl -X POST http://localhost:12000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Count to 5"}],
    "stream": true
  }'""")
    
    print("\n4. Health check:")
    print("curl http://localhost:12000/health")


def print_python_sdk_example():
    """Print example using OpenAI Python SDK."""
    print(f"\n{'=' * 70}")
    print("PYTHON SDK EXAMPLE (using openai package)")
    print(f"{'=' * 70}")
    
    print("""
# Install: pip install openai

from openai import OpenAI

# Point to your local bridge server
client = OpenAI(
    base_url="http://localhost:12000/v1",
    api_key="any-key-here"  # Bridge ignores this
)

# Use as normal
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ],
    temperature=0.7
)

print(response.choices[0].message.content)

# Streaming example
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Count to 5"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')
""")


def print_common_errors():
    """Print common errors and their meanings."""
    print(f"\n{'=' * 70}")
    print("COMMON ERRORS AND THEIR MEANINGS")
    print(f"{'=' * 70}")
    
    errors = [
        {
            "error": "Invalid HTTP request received",
            "causes": [
                "Trying to use HTTPS on HTTP endpoint (use http:// not https://)",
                "Malformed HTTP request",
                "Wrong protocol or port",
                "Client disconnect during request"
            ]
        },
        {
            "error": "400 Bad Request - Model parameter required",
            "causes": [
                "Missing 'model' field in request body",
                "Sending empty request body"
            ]
        },
        {
            "error": "502 Bad Gateway - Token err",
            "causes": [
                "Circuit OAuth credentials not configured",
                "Invalid Circuit credentials",
                "Circuit OAuth endpoint unreachable"
            ]
        },
        {
            "error": "504 Gateway Timeout",
            "causes": [
                "Circuit API took too long to respond",
                "Network issues between bridge and Circuit",
                "Very large request causing timeout"
            ]
        }
    ]
    
    for err in errors:
        print(f"\nError: {err['error']}")
        print("Possible causes:")
        for cause in err['causes']:
            print(f"  - {cause}")


def main():
    """Print all examples."""
    print("OpenAI to Circuit Bridge - Request/Response Examples")
    print(f"Generated: {datetime.now().isoformat()}")
    
    # Print each example
    for example in EXAMPLES:
        print_example(example)
    
    # Print curl examples
    print_curl_examples()
    
    # Print SDK example
    print_python_sdk_example()
    
    # Print common errors
    print_common_errors()


if __name__ == "__main__":
    main()
