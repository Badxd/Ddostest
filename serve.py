#!/usr/bin/env python3
"""camweb for Heroku: password-protected camera snapshot receiver + gallery.
Heroku terminates HTTPS itself, so this serves plain HTTP on $PORT."""
import base64, hmac, http.server, os, re, sys, time

PORT = int(os.environ.get('PORT', '8080'))
ROOT = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(ROOT, 'shots')
USER = os.environ.get('CAM_USER', 'admin')
PASSWORD = os.environ.get('CAM_PASSWORD', '')
MAX_SHOTS = int(os.environ.get('MAX_SHOTS', '50'))   # oldest are deleted beyond this
MAX_BYTES = 10 * 1024 * 1024
SAFE = re.compile(r'^[A-Za-z0-9._-]+\.png$')

if not PASSWORD:
    sys.exit('CAM_PASSWORD is not set. Refusing to start without a password.')
os.makedirs(SHOTS, exist_ok=True)

HEAD = '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>shots</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;padding:16px;background:#111;color:#eee;font:15px/1.4 system-ui,sans-serif}
h1{font-size:16px;font-weight:600;color:#aaa;margin:0 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.card{display:block;background:#181818;border:1px solid #262626;border-radius:10px;overflow:hidden;text-decoration:none;color:inherit}
.card img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block;background:#000}
.meta{padding:8px 10px;font-size:12px;display:flex;flex-direction:column;gap:2px;color:#bbb}
.meta b{font-weight:500;word-break:break-all}.meta span{color:#777}
.empty{color:#666;padding:40px 0;text-align:center}</style></head><body>'''


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'camweb'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def _send(self, code, ctype, data, extra=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        h = self.headers.get('Authorization', '')
        if h.startswith('Basic '):
            try:
                u, _, p = base64.b64decode(h[6:]).decode('utf-8').partition(':')
                ok_u = hmac.compare_digest(u.encode(), USER.encode())
                ok_p = hmac.compare_digest(p.encode(), PASSWORD.encode())
                if ok_u and ok_p:
                    return True
            except Exception:
                pass
        self._send(401, 'text/plain', b'login required',
                   {'WWW-Authenticate': 'Basic realm="camweb"'})
        return False

    def do_GET(self):
        if not self._authed():
            return
        path = self.path.split('?')[0]
        if path in ('/', '/index.html'):
            with open(os.path.join(ROOT, 'index.html'), 'rb') as f:
                return self._send(200, 'text/html; charset=utf-8', f.read())
        if path == '/shots':
            return self.gallery()
        if path.startswith('/shots/'):
            name = path[len('/shots/'):]
            fp = os.path.join(SHOTS, name)
            if SAFE.match(name) and os.path.isfile(fp):
                with open(fp, 'rb') as f:
                    return self._send(200, 'image/png', f.read())
        self._send(404, 'text/plain', b'not found')

    def do_POST(self):
        if not self._authed():
            return
        if self.path != '/snap':
            return self._send(404, 'text/plain', b'not found')
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if n <= 0 or n > MAX_BYTES:
                return self._send(413, 'text/plain', b'bad size')
            body = self.rfile.read(n)
            if not body.startswith(b'\x89PNG'):
                return self._send(415, 'text/plain', b'png only')
            base = 'shot-' + time.strftime('%Y%m%d-%H%M%S')
            name, i = base + '.png', 1
            while os.path.exists(os.path.join(SHOTS, name)):
                name, i = '%s-%d.png' % (base, i), i + 1
            with open(os.path.join(SHOTS, name), 'wb') as f:
                f.write(body)
            self.prune()
            self._send(200, 'application/json', ('{"ok":true,"file":"%s"}' % name).encode())
        except Exception as e:
            print('snap error:', e, flush=True)
            self._send(500, 'text/plain', b'error')

    def prune(self):
        files = sorted(f for f in os.listdir(SHOTS) if SAFE.match(f))
        for f in files[:-MAX_SHOTS] if len(files) > MAX_SHOTS else []:
            try:
                os.remove(os.path.join(SHOTS, f))
            except OSError:
                pass

    def gallery(self):
        files = sorted((f for f in os.listdir(SHOTS) if SAFE.match(f)), reverse=True)
        out = [HEAD, '<h1>shots &middot; %d</h1>' % len(files)]
        if files:
            out.append('<div class="grid">')
            for f in files:
                st = os.stat(os.path.join(SHOTS, f))
                when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))
                out.append('<a class="card" href="/shots/%s" target="_blank"><img src="/shots/%s" loading="lazy">'
                           '<div class="meta"><b>%s</b><span>%s &middot; %.1f KB</span></div></a>'
                           % (f, f, f, when, st.st_size / 1024.0))
            out.append('</div>')
        else:
            out.append('<div class="empty">no snaps yet</div>')
        out.append('<script>setInterval(function(){location.reload()},10000)</script></body></html>')
        self._send(200, 'text/html; charset=utf-8', ''.join(out).encode())


if __name__ == '__main__':
    print('camweb listening on 0.0.0.0:%d' % PORT, flush=True)
    http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
    
