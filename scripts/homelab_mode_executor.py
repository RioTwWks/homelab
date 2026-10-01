#!/usr/bin/env python3
import json, os, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
PORT=int(os.environ.get("HOMELAB_MODE_PORT","8092")); ROOT=Path(__file__).resolve().parent.parent; SH=ROOT/"scripts"/"homelab_mode.sh"
class H(BaseHTTPRequestHandler):
  def do_GET(self):
    if self.path.rstrip('/') not in ('','/healthz'): return self.send_error(404)
    self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')
  def do_POST(self):
    if self.path.rstrip('/')!='/v1/mode': return self.send_error(404)
    mode=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))).decode() or '{}').get('mode','').lower()
    p=subprocess.run(['/bin/bash',str(SH),'apply',mode],cwd=ROOT,capture_output=True,text=True)
    b=json.dumps({'mode':mode,'ok':p.returncode==0}).encode(); self.send_response(200 if p.returncode==0 else 500); self.end_headers(); self.wfile.write(b)
if __name__=='__main__': HTTPServer(('0.0.0.0',PORT),H).serve_forever()
