"""Finto Gemini per i test locali delle domande: risponde citando la prima fonte del prompt.
Con una domanda che contiene "quota" risponde 429, per provare il messaggio di quota esaurita."""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        prompt = body["contents"][0]["parts"][0]["text"]
        question = prompt.rsplit("DOMANDA DEL LETTORE:", 1)[-1].strip()
        if "quota" in question.lower():
            self.send_response(429); self.end_headers(); self.wfile.write(b'{"error":{"message":"quota"}}'); return
        ref = (re.search(r"\[(S\d+)\]", prompt) or [None, "S1"])[1]
        text = (f"[Prova] Risposta alla domanda «{question}». Secondo la fonte il dato è confermato [{ref}].\n\n"
                "In generale, una decisione di questo tipo si riflette sulle rate dei mutui a tasso variabile.")
        out = json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)


ThreadingHTTPServer(("127.0.0.1", 8899), H).serve_forever()
