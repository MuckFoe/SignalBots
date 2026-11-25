"""Local server for the specs viewer (index.html), with saving.

    python specs/serve.py [port]        default port 8777

Serves this folder on 127.0.0.1 only, and accepts PUT for the markdown files
the viewer shows so they can be edited in the browser. Standard library only.

What a PUT may touch is deliberately narrow, because this writes into the
repository:
  - README.md, or <spec-folder>/{spec,plan,tasks,notes}.md
  - the file must already exist: the viewer edits, the /sdd-* skills create
  - the request must carry the ETag it read (If-Match), so a file changed on
    disk in the meantime is never silently overwritten
  - the request must come from this page: loopback Host, same Origin, and a
    custom header a foreign site cannot send without a preflight we refuse
"""

import hashlib
import json
import os
import re
import sys
import tempfile
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
EDITABLE = re.compile(r"^(?:README\.md|[A-Za-z0-9][A-Za-z0-9._-]*/(?:spec|plan|tasks|notes)\.md)$")
MAX_BYTES = 2 * 1024 * 1024


def etag(data):
    return '"' + hashlib.sha256(data).hexdigest() + '"'


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # The page must always see the file as it is on disk right now.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def editable_path(self):
        """Filesystem path for an editable markdown file, or None."""
        rel = self.path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if not EDITABLE.match(rel) or ".." in rel:
            return None
        return os.path.join(ROOT, *rel.split("/"))

    def send_json(self, status, body, headers=None):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/__edit":
            self.send_json(HTTPStatus.OK, {"edit": True})
            return
        path = self.editable_path()
        if path is None or not os.path.isfile(path):
            super().do_GET()
            return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag(data))
        self.end_headers()
        self.wfile.write(data)

    def from_this_page(self):
        port = self.server.server_address[1]
        hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {"http://" + h for h in hosts}:
            return False
        return self.headers.get("X-Specs-Edit") == "1"

    def do_PUT(self):
        if not self.from_this_page():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Not sent by the viewer page."})
            return
        path = self.editable_path()
        if path is None:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Not a file the viewer may edit."})
            return
        if not os.path.isfile(path):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "The file does not exist; the viewer does not create files."})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length is required."})
            return
        if length > MAX_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Too large."})
            return
        body = self.rfile.read(length)
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "The body is not UTF-8."})
            return

        with open(path, "rb") as f:
            current = f.read()
        if self.headers.get("If-Match") != etag(current):
            self.send_json(HTTPStatus.PRECONDITION_FAILED,
                           {"error": "The file changed on disk since the page read it."})
            return

        # Keep the line endings the file already has; a textarea always sends LF.
        text = text.replace("\r\n", "\n")
        if b"\r\n" in current:
            text = text.replace("\n", "\r\n")
        data = text.encode("utf-8")

        # Write beside the target and swap, so a crash never leaves half a file.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except OSError:
            if os.path.exists(tmp):
                os.remove(tmp)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Could not write the file."})
            return
        self.send_json(HTTPStatus.OK, {"saved": True}, {"ETag": etag(data)})


class Server(ThreadingHTTPServer):
    # The default lets a second server bind a port that is already in use on
    # Windows; requests then reach whichever got there first, and saving
    # silently does not work. Refuse to start instead.
    allow_reuse_address = False


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    try:
        server = Server(("127.0.0.1", port), Handler)
    except OSError:
        sys.exit("Port %d is already in use - stop the other server, or pass another port: "
                 "python specs/serve.py %d" % (port, port + 1))
    print("Specs viewer with editing: http://127.0.0.1:%d/   (Ctrl+C to stop)" % port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
