import json, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

class Relay(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length)
        print(f"[WH] Received POST: {body[:200]}")
        
        result = b'{"status":"relayed"}'
        try:
            req = urllib.request.Request(
                'http://127.0.0.1:8080/webhooks/revenuecat',
                data=body, headers={'Content-Type': 'application/json'}, method='POST'
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = resp.read()
            print(f"[WH] Forwarded OK: {result[:100]}")
        except Exception as e:
            print(f"[WH] Forward error (non-fatal): {e}")
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(result)
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"status":"relay_ok","note":"RevenueCat webhook relay"}).encode())
    
    def log_message(self, fmt, *args):
        print(f"[WH] {args[0]} {args[1]} {args[2]}")

port = 8082
print(f"[WH] RevenueCat webhook relay starting on port {port}...")
print(f"[WH] Forwards POST / -> http://127.0.0.1:8080/webhooks/revenuecat")
HTTPServer(('0.0.0.0', port), Relay).serve_forever()
