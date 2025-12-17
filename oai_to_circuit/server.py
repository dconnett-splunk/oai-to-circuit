import argparse
import os
import ssl
import time
import multiprocessing

import uvicorn

from oai_to_circuit.config import load_config
from oai_to_circuit.logging_config import configure_logging
from oai_to_circuit.app import create_app


def build_app_import_string() -> str:
    # Uvicorn can import an ASGI app via "module:variable".
    # We expose `oai_to_circuit.server:app` for that purpose.
    return "oai_to_circuit.server:app"


configure_logging()
_config = load_config()
app = create_app(config=_config)


def run_http(host: str, port: int):
    uvicorn.run(
        build_app_import_string(),
        host=host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
    )


def run_https(host: str, port: int, key: str, cert: str):
    uvicorn.run(
        build_app_import_string(),
        host=host,
        port=port,
        ssl_keyfile=key,
        ssl_certfile=cert,
        reload=False,
        log_level="info",
        access_log=True,
    )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="OpenAI to Circuit Bridge Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=12000, help="Port for HTTP (default: 12000)")
    parser.add_argument("--ssl-port", type=int, default=12443, help="Port for HTTPS (default: 12443)")
    parser.add_argument("--ssl", action="store_true", help="Enable HTTPS")
    parser.add_argument("--ssl-only", action="store_true", help="Only run HTTPS (no HTTP)")
    parser.add_argument("--cert", default="cert.pem", help="SSL certificate file")
    parser.add_argument("--key", default="key.pem", help="SSL private key file")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")

    args = parser.parse_args(argv)

    # SSL configuration (kept for parity with prior behavior)
    if args.ssl or args.ssl_only:
        if not os.path.exists(args.cert) or not os.path.exists(args.key):
            raise SystemExit(
                f"SSL certificate files not found: {args.cert}, {args.key}. "
                f"Run 'python generate_cert.py' to create self-signed certificates."
            )

        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(args.cert, args.key)

    if args.ssl_only:
        os.environ["SSL_MODE"] = "https_only"
        uvicorn.run(
            build_app_import_string(),
            host=args.host,
            port=args.ssl_port,
            ssl_keyfile=args.key,
            ssl_certfile=args.cert,
            reload=not args.no_reload,
            log_level="debug",
            access_log=True,
        )
    elif args.ssl:
        os.environ["SSL_MODE"] = "dual"

        try:
            multiprocessing.set_start_method("fork")
        except RuntimeError:
            pass

        http_process = multiprocessing.Process(
            target=run_http,
            args=(args.host, args.port),
            daemon=True,
            name="bridge-http",
        )
        https_process = multiprocessing.Process(
            target=run_https,
            args=(args.host, args.ssl_port, args.key, args.cert),
            daemon=True,
            name="bridge-https",
        )

        processes = [http_process, https_process]
        for p in processes:
            p.start()

        try:
            while any(p.is_alive() for p in processes):
                time.sleep(0.5)
        except KeyboardInterrupt:
            for p in processes:
                if p.is_alive():
                    p.terminate()
            for p in processes:
                p.join(timeout=5.0)
    else:
        os.environ["SSL_MODE"] = os.environ.get("SSL_MODE", "")
        uvicorn.run(
            build_app_import_string(),
            host=args.host,
            port=args.port,
            reload=not args.no_reload,
            log_level="debug",
            access_log=True,
        )


