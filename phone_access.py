"""
phone_access.py - lets the Spoolhouse phone app use this computer's inventory and printers over Wi-Fi.

Off until switched on in Settings → Phone access. Then:
  * a second server listens on the local network (port 8766), separate from the app's own page server
    (which stays on 127.0.0.1 only);
  * it speaks HTTPS with a certificate made on this computer; the pairing QR code carries the
    certificate's fingerprint, and the phone refuses any other certificate, so nobody else on the
    network can listen in or pretend to be this computer;
  * only paired phones get in (each has its own token; remove a phone and its token stops working),
    and only to a fixed list of requests: inventory, printers and the shopping list. Never the USB
    reader, file dialogs, backups, restore or app settings;
  * it announces itself on the network (mDNS, "_spoolhouse._tcp"), so the phone finds it again if the
    computer's address changes.
"""
import base64
import datetime
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import ssl
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler

import cfs_gui
import inventory as inv

PORT = 8766
SERVICE = "_spoolhouse._tcp.local."
PAIR_MINUTES = 10
PAIR_TRIES = 5

# what a paired phone may ask for (the same requests the app's own page uses)
ALLOWED = {
    "/api/inv/list", "/api/inv/find", "/api/inv/save", "/api/inv/settings", "/api/inv/restore", "/api/serial",
    "/api/printers/list", "/api/printer/status", "/api/printer/history", "/api/printer/files",
    "/api/printer/job_plan", "/api/printer/check_file", "/api/printer/link", "/api/shopping",
    "/api/status",
    "/api/inv/import",  # a phone switching from "On this phone" brings its spools across (2.8.0+)
}

STATE = {"server": None, "zeroconf": None, "info": None, "pairing": None, "error": None}
_LOCK = threading.Lock()


# ---------------------------------------------------------------- certificate
def _cert_dir():
    return os.path.join(inv.DATA_DIR, "phone-access")


def ensure_certificate():
    """This computer's own certificate (made once, kept with the data). Returns (cert, key, fingerprint)."""
    d = _cert_dir()
    cert_path, key_path = os.path.join(d, "certificate.pem"), os.path.join(d, "private-key.pem")
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        os.makedirs(d, exist_ok=True)
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Spoolhouse on {computer_name()}"[:64])])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=365 * 20))
                .sign(key, hashes.SHA256()))
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
        os.chmod(key_path, 0o600)
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(cert_path, "rb") as f:
        der = ssl.PEM_cert_to_DER_cert(f.read().decode())
    return cert_path, key_path, hashlib.sha256(der).hexdigest().upper()


# ---------------------------------------------------------------- network details
def computer_name():
    """The name people know the computer by (System Settings → General → About on a Mac)."""
    name = ""
    try:
        if cfs_gui.PLATFORM == "windows":
            name = os.environ.get("COMPUTERNAME", "")
        else:
            import subprocess
            name = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True,
                                  timeout=3).stdout.strip()
    except Exception:
        pass
    return name or socket.gethostname().split(".")[0] or "this computer"


def local_addresses():
    """This computer's addresses on the local network (best first), for the QR code."""
    found = []
    try:  # the address used to reach the outside world is almost always the right one
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # nothing is sent: this only picks a route
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        import ifaddr
        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if isinstance(ip.ip, str) and ip.ip not in found:
                    found.append(ip.ip)
    except Exception:
        pass
    usable = [a for a in found if ipaddress.ip_address(a).is_private
              and not ipaddress.ip_address(a).is_loopback and not a.startswith("169.254.")]
    return usable[:4]


# ---------------------------------------------------------------- pairing
def start_pairing():
    """A new one-time pairing code (valid for 10 minutes), and the QR code for the phone to scan."""
    if STATE["server"] is None:
        raise IOError("Turn on Phone access first.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    with _LOCK:
        STATE["pairing"] = {"code": code, "until": time.time() + PAIR_MINUTES * 60, "tries": 0}
    info = STATE["info"]
    return {"code": code, "minutes": PAIR_MINUTES, **pair_link(code), **status()}


def pair_link(code):
    """The pairing link and its QR code. Kept short, so the code has as few squares as possible: the two best
    addresses (the phone finds the computer on the network if it moves), the port only if it isn't the usual
    one, and the certificate fingerprint in base64url (43 characters, not 64)."""
    info = STATE["info"]
    fields = {"h": ",".join(info["addresses"][:2]), "c": code,
              "f": base64.urlsafe_b64encode(bytes.fromhex(info["fingerprint"])).rstrip(b"=").decode(),
              "n": info["name"]}
    if PORT != 8766:
        fields["p"] = PORT
    link = "spoolhouse://pair?" + urllib.parse.urlencode(fields)
    import segno
    qr = segno.make(link, error="m")
    # every square a whole number of pixels with crisp edges (blurred edges are what cameras struggle with
    # on a screen), and the full 4-square white margin QR codes are meant to have
    svg = qr.svg_inline(scale=QR_SCALE, dark="#000000", light="#ffffff", border=4)
    svg = svg.replace("<svg ", '<svg shape-rendering="crispEdges" ', 1)
    return {"link": link, "qr_svg": svg, "qr_px": qr.symbol_size(scale=QR_SCALE, border=4)[0]}


QR_SCALE = 6


def _redeem(code, phone_name):
    with _LOCK:
        p = STATE["pairing"]
        if not p or time.time() > p["until"]:
            raise PermissionError("That pairing code has expired. Make a new one on the computer.")
        p["tries"] += 1
        if p["tries"] > PAIR_TRIES:
            STATE["pairing"] = None
            raise PermissionError("Too many wrong codes. Make a new one on the computer.")
        if not secrets.compare_digest(str(code), p["code"]):
            raise PermissionError("That code isn't right.")
        STATE["pairing"] = None  # one phone per code
    return inv.add_phone(phone_name)


# ---------------------------------------------------------------- the server
class PhoneHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def setup(self):
        self.request.settimeout(30)  # the TLS handshake happens here, on this connection's own thread
        super().setup()

    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/phone/pair":
                token = _redeem(body.get("code", ""), body.get("name", ""))
                return self._send(200, {"token": token, **hello()})
            auth = self.headers.get("Authorization", "")
            phone = inv.phone_for_token(auth[7:] if auth.startswith("Bearer ") else "")
            if phone is None:
                return self._send(401, {"error": "This phone isn't paired (or was removed). Pair it again."})
            if self.path == "/api/phone/hello":
                return self._send(200, {**hello(), "phone": phone["name"]})
            if self.path == "/api/phone/events":
                return self._send(200, events(body.get("since")))
            if self.path not in ALLOWED:
                return self._send(403, {"error": "The phone can't do that."})
            if self.path == "/api/inv/save" and body.get("id"):
                body = _merged(body)
            result = cfs_gui.light_api(self.path, body)
            if result is None:
                return self._send(403, {"error": "The phone can't do that."})
            self._send(200, result)
        except PermissionError as e:
            self._send(403, {"error": str(e)})
        except Exception as e:
            cfs_gui.on_error(f"phone {self.path}: " + traceback.format_exc())
            self._send(200, {"error": str(e)})


class PhoneServer(cfs_gui.LocalServer):
    allow_reuse_address = True

    def __init__(self, address, context):
        self.context = context
        super().__init__(address, PhoneHandler)

    def get_request(self):
        sock, addr = self.socket.accept()
        # handshake later, on the handler's thread, so one slow phone can't hold up the others
        return self.context.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr

    def server_bind(self):
        import socketserver
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "0.0.0.0", self.server_address[1]


def _merged(body):
    """A spool update from the phone, on top of the stored spool: anything the phone didn't send is kept
    (saving replaces every field, so a missing one would otherwise be wiped)."""
    with inv._db() as con:
        row = con.execute("SELECT * FROM spools WHERE id = ? AND deleted_at IS NULL", (int(body["id"]),)).fetchone()
    if row is None:
        raise IOError("That spool is no longer in your inventory.")
    merged = {**{k: row[k] for k in inv.FIELDS}, **{k: v for k, v in body.items() if k in inv.FIELDS or k == "id"}}
    # weighed while away: that was right *then*, so take off anything printed from it since
    measured = body.get("measured_at")
    if measured and "remaining_g" in body:
        with inv._db() as con:
            used = con.execute("SELECT COALESCE(SUM(grams), 0) FROM usage WHERE spool_id = ? AND at > ?",
                               (int(body["id"]), float(measured))).fetchone()[0]
        merged["remaining_g"] = max(0.0, float(body["remaining_g"]) - used)
    return merged


def events(since):
    """Alerts since the phone last looked, plus whether a print is running (so it can look again sooner)."""
    found, latest = inv.events_since(since)
    printing = any((cfs_gui.pstate(p["id"])["job"] or {}).get("state") in ("printing", "paused")
                   for p in inv.list_printers())
    return {"events": found, "latest": latest, "printing": printing}


def hello():
    return {"app": cfs_gui.APP_NAME, "version": cfs_gui.APP_VERSION, "computer": computer_name(),
            "fingerprint": (STATE["info"] or {}).get("fingerprint")}


def enabled():
    return inv.get_pref("phone_access", "0") == "1"


def start(port=PORT, host="0.0.0.0", announce=True):
    """Start listening (if not already). Raises OSError if the port is taken."""
    with _LOCK:
        if STATE["server"] is not None:
            return status()
        cert, key, fingerprint = ensure_certificate()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        srv = PhoneServer((host, port), ctx)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        STATE.update(server=srv, error=None, info={
            "port": srv.server_address[1], "fingerprint": fingerprint, "name": computer_name(),
            "addresses": local_addresses() or ["127.0.0.1"]})
    if announce:
        threading.Thread(target=_announce, daemon=True).start()
    cfs_gui.on_error(f"phone access on port {srv.server_address[1]}")
    return status()


def _announce():
    """Tell phones on the network where to find us (mDNS), with the certificate's fingerprint."""
    try:
        from zeroconf import ServiceInfo, Zeroconf
        info = STATE["info"]
        zc = Zeroconf()
        zc.register_service(ServiceInfo(
            SERVICE, f"Spoolhouse on {info['name']}.{SERVICE}",
            addresses=[socket.inet_aton(a) for a in info["addresses"]], port=info["port"],
            properties={"fp": info["fingerprint"][:32], "v": "1"}, server=f"{_host_label(info['name'])}.local."))
        STATE["zeroconf"] = zc
    except Exception as e:
        cfs_gui.on_error(f"phone access: couldn't announce on the network: {e}")


def _host_label(name):
    """A valid network host name: letters, digits and dashes only (e.g. "Richards-MacBook-Pro-spoolhouse")."""
    import re
    return (re.sub(r"[^A-Za-z0-9]+", "-", name.replace("’", "").replace("'", "")).strip("-") or "computer") + "-spoolhouse"


def stop():
    with _LOCK:
        srv, zc = STATE["server"], STATE["zeroconf"]
        STATE.update(server=None, zeroconf=None, pairing=None)
    if zc is not None:
        try:
            zc.unregister_all_services()
            zc.close()
        except Exception:
            pass
    if srv is not None:
        srv.shutdown()
        srv.server_close()


def set_enabled(on):
    inv.set_pref("phone_access", "1" if on else "0")
    if on:
        try:
            start()
        except OSError as e:
            STATE["error"] = f"Couldn't start Phone access: {e}"
            raise IOError(STATE["error"])
    else:
        stop()
    return status()


def start_if_enabled():
    if enabled():
        try:
            start()
        except OSError as e:
            STATE["error"] = f"Couldn't start Phone access: {e}"
            cfs_gui.on_error(STATE["error"])


def status():
    info = STATE["info"] if STATE["server"] else None
    return {"enabled": enabled(), "running": STATE["server"] is not None, "error": STATE["error"],
            "addresses": info["addresses"] if info else [], "port": info["port"] if info else PORT,
            "fingerprint": info["fingerprint"] if info else None, "computer": computer_name(),
            "phones": inv.list_phones()}


def api(path, body):
    """The desktop page's own requests about Phone access (Settings)."""
    if path == "/api/phone/status":
        return status()
    if path == "/api/phone/enable":
        return set_enabled(bool(body.get("on")))
    if path == "/api/phone/pair_start":
        return start_pairing()
    if path == "/api/phone/remove":
        inv.remove_phone(body.get("id"))
        return status()
    return None
