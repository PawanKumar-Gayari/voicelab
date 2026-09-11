#!/usr/bin/env python3
"""VoiceLab staging smoke suite.

Default mode is non-destructive and does not call paid provider APIs. --live
runs authenticated FastAPI, LiveKit-token, AssemblyAI session-ready, and
Gemini vision checks against the configured staging environment.
"""
from __future__ import annotations

import argparse, asyncio, base64, json, os, ssl, urllib.parse, urllib.request
from pathlib import Path

try:
    import websockets
except ImportError:
    websockets = None

BASE = os.getenv("VOICE_LAB_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def http_json(url, method="GET", payload=None, cookie=None, timeout=12):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": "VoiceLab-StagingCheck/1.0", "Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()


def env_check():
    keys = ["AUTH_USERNAME", "AUTH_PASSWORD", "AUTH_SECRET", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ASSEMBLYAI_API_KEY", "GOOGLE_API_KEY"]
    return {k: bool(os.getenv(k, "").strip()) for k in keys}


def png_1x1():
    # Minimal valid transparent PNG; sufficient to exercise Gemini inline image input.
    return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


async def assemblyai_ready():
    if websockets is None:
        return False, "websockets package unavailable"
    key = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
    if not key:
        return False, "ASSEMBLYAI_API_KEY missing"
    url = "wss://agents.assemblyai.com/v1/ws"
    try:
        async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {key}"}, open_timeout=10, close_timeout=5) as ws:
            msg = {"type":"session.update","session":{"system_prompt":"Reply briefly.","greeting":"Hello from staging check.","output":{"voice":"anna"},"tools":[]}}
            await ws.send(json.dumps(msg))
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                event = json.loads(raw)
                if event.get("type") == "session.ready":
                    return True, event.get("session_id")
                if event.get("type") == "session.error":
                    return False, event
    except Exception as exc:
        return False, str(exc)
    return False, "session.ready not received"


def gemini_vision():
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key:
        return False, "GOOGLE_API_KEY missing"
    body = {
        "contents": [{"parts": [
            {"text": 'Return JSON only: {"ok":true,"summary":"one pixel image received"}.'},
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png_1x1()).decode()}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + urllib.parse.quote(key)
    try:
        status, _, raw = http_json(url, "POST", body, timeout=25)
        data = json.loads(raw.decode())
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return bool(text), text[:300]
    except Exception as exc:
        return False, str(exc)


def run(live=False):
    results=[]
    env=env_check()
    results.append({"check":"required_environment","ok":(all(env.values()) if live else True),"details":env if live else "provider keys checked only in --live mode"})
    try:
        status,_,_=http_json(BASE+"/health")
        results.append({"check":"fastapi_health","ok":status==200,"details":status})
    except Exception as exc:
        results.append({"check":"fastapi_health","ok":False,"details":str(exc)})
        return results
    if not live:
        for name in ("authenticated_session_creation","livekit_token","assemblyai_session_ready","gemini_vision","interruption","persistence_recovery"):
            results.append({"check":name,"ok":None,"details":"skipped; use --live or pytest contract suite"})
        return results

    user=os.getenv("AUTH_USERNAME",""); password=os.getenv("AUTH_PASSWORD","")
    try:
        status,headers,raw=http_json(BASE+"/api/auth/login","POST",{"username":user,"password":password})
        cookie=headers.get("Set-Cookie","").split(";",1)[0]
        data=json.loads(raw)
        results.append({"check":"authenticated_login","ok":status==200 and data.get("success") and bool(cookie),"details":"session cookie issued"})
    except Exception as exc:
        results.append({"check":"authenticated_login","ok":False,"details":str(exc)}); return results

    try:
        status,_,raw=http_json(BASE+"/api/sessions","POST",{},cookie)
        sid=json.loads(raw)["session_id"]
        results.append({"check":"authenticated_session_creation","ok":status==200,"details":sid})
    except Exception as exc:
        results.append({"check":"authenticated_session_creation","ok":False,"details":str(exc)}); return results

    try:
        room="voicelab-"+sid; identity="researcher-"+sid
        status,_,raw=http_json(BASE+"/api/livekit/token?"+urllib.parse.urlencode({"room":room,"identity":identity}),cookie=cookie)
        token=json.loads(raw).get("token","")
        results.append({"check":"livekit_token","ok":status==200 and bool(token),"details":"short-lived token issued"})
    except Exception as exc:
        results.append({"check":"livekit_token","ok":False,"details":str(exc)})

    ok,detail=asyncio.run(assemblyai_ready())
    results.append({"check":"assemblyai_session_ready","ok":ok,"details":detail})
    ok,detail=gemini_vision()
    results.append({"check":"gemini_vision","ok":ok,"details":detail})
    results.append({"check":"interruption","ok":None,"details":"requires real browser/audio; deterministic interruption contract is in pytest"})
    results.append({"check":"persistence_recovery","ok":None,"details":"requires staging process restart; deterministic persistence contract is in pytest"})
    return results


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--live",action="store_true"); args=parser.parse_args()
    results=run(args.live); print(json.dumps(results,indent=2)); raise SystemExit(1 if any(r["ok"] is False for r in results) else 0)
