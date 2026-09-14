#!/usr/bin/env python3
"""Minimal demo app for Athena financial-tracking (Epic 10) testing.

1) Serves a health endpoint on $PORT so the k8s deployment becomes Ready.
2) In a background loop, calls the Amberd LLM gateway so its Prometheus
   token/duration counters attribute usage -> cost to this app's namespace.

Athena injects LLM_ENDPOINT and LLM_MODEL_NAME at deploy time (the gateway
route is chosen by tier/model, not by the endpoint typed at registration).
Provide LLM_API_TOKEN (and any override below) as a container Parameter.
"""
import json, os, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT     = int(os.getenv("PORT", "8080"))
ENDPOINT = os.getenv("LLM_ENDPOINT", "")          # set by Athena, e.g. amberd-llm-gateway.tier2.svc:8010
MODEL    = os.getenv("LLM_MODEL_NAME", "")         # set by Athena
TOKEN    = os.getenv("LLM_API_TOKEN", "")          # you add as a Parameter
SCHEME   = os.getenv("LLM_SCHEME", "http")         # http | https
PATH     = os.getenv("LLM_PATH", "/v1/chat/completions")
INTERVAL = float(os.getenv("CALL_INTERVAL_S", "10"))
MAXTOK   = int(os.getenv("MAX_TOKENS", "64"))

state = {"status": "starting", "calls": 0, "errors": 0, "last_usage": None}

def log(*a):
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), *a, flush=True)

def call_gateway():
    url = f"{SCHEME}://{ENDPOINT}{PATH}"
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hello and count to five."}],
        "max_tokens": MAXTOK,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    state["last_usage"] = data.get("usage")
    log("gateway ok model=", MODEL, "usage=", state["last_usage"])

def loop():
    if not ENDPOINT or not MODEL:
        state["status"] = "misconfigured: LLM_ENDPOINT / LLM_MODEL_NAME missing"
        log(state["status"]); return
    log("call loop start endpoint=", ENDPOINT, "model=", MODEL, "interval=", INTERVAL)
    while True:
        try:
            call_gateway(); state["calls"] += 1; state["status"] = "ok"
        except urllib.error.HTTPError as e:
            state["errors"] += 1; state["status"] = f"http {e.code}"
            log("HTTPError", e.code, e.read()[:500])
        except Exception as e:
            state["errors"] += 1; state["status"] = f"error: {e}"
            log("error", repr(e))
        time.sleep(INTERVAL)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(state).encode())
    def log_message(self, *a): pass

if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    log(f"health server on :{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
