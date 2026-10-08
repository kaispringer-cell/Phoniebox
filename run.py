"""Service entry point: one waitress process on loopback; nginx terminates TLS in front."""

import os
import signal
import sys
from waitress import serve
from app import create_app

os.umask(0o077)
app = create_app(start_hardware=True)


def stop(*_):
    app.extensions['hardware'].close()
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
# One process only: singleton NFC reader, OAuth states and librespot supervisor.
serve(app, host='127.0.0.1', port=8888, threads=4, clear_untrusted_proxy_headers=False)
