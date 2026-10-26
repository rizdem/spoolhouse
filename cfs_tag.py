#!/usr/bin/env python3
"""
cfs_tag.py - write/read Creality CFS (K2 / K1 / Hi) filament RFID tags offline
from a Mac (or Linux/Windows) using any PC/SC USB NFC reader (ACR122U, ACR1252U ...).

Based on the tag format published by DnG-Crafts (github.com/DnG-Crafts/K2-RFID).
No account, no cloud.

Setup (once):
    python3 -m pip install pyscard cryptography

Usage:
    python3 cfs_tag.py materials                 # list material IDs
    python3 cfs_tag.py read                      # decode a tag
    python3 cfs_tag.py write -m 00001 -c FF6B35  # Generic PLA, orange, 1 kg
    python3 cfs_tag.py write -m 00003 -c 000000 -w 750g --count 2
    python3 cfs_tag.py format                    # wipe back to blank/default keys

Quit SimplyPrint NFC Agent (or anything else using the reader) first.
"""
import argparse
import sys
import threading
import time

try:
    from smartcard.System import readers
    from smartcard.scard import SCARD_LEAVE_CARD, SCARD_RESET_CARD
    from smartcard.Exceptions import SmartcardException
except ImportError:
    sys.exit("Missing pyscard:  python3 -m pip install pyscard cryptography")
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    sys.exit("Missing cryptography:  python3 -m pip install cryptography")

# ---- Creality constants (same values used by the printer firmware / DnG tools)
UID_KEY = b"q3bu^t1nqfZ(pf$1"   # derives the per-tag sector-1 MIFARE key from the UID
DATA_KEY = b"H@CFkRnz@KAtBJp2"  # encrypts the 48-byte spool record in sector 1
KEY_DEFAULT = bytes([0xFF] * 6)
VENDOR_CREALITY = "0276"

WEIGHTS = {"1kg": "0330", "750g": "0247", "600g": "0198", "500g": "0165", "250g": "0082"}

MATERIALS = {
    "00001": "Generic PLA", "00002": "Generic PLA-Silk", "00003": "Generic PETG",
    "00004": "Generic ABS", "00005": "Generic TPU", "00006": "Generic PLA-CF",
    "00007": "Generic ASA", "00008": "Generic PA", "00009": "Generic PA-CF",
    "00010": "Generic BVOH", "00011": "Generic PVA", "00012": "Generic HIPS",
    "00013": "Generic PET-CF", "00014": "Generic PETG-CF", "00015": "Generic PA6-CF",
    "00016": "Generic PAHT-CF", "00017": "Generic PPS", "00018": "Generic PPS-CF",
    "00019": "Generic PP", "00020": "Generic PET", "00021": "Generic PC",
    "00026": "Generic TPU 64D", "00027": "Generic PETG-GF", "00032": "Generic PCTG",
    "00033": "Generic ASA-CF",
    "01001": "Creality Hyper PLA", "01601": "Creality Soleyin Ultra PLA",
    "02001": "Creality Hyper PLA-CF", "03001": "Creality Hyper ABS",
    "04001": "Creality CR-PLA", "05001": "Creality CR-Silk", "06001": "Creality CR-PETG",
    "06002": "Creality Hyper PETG", "07001": "Creality CR-ABS", "07002": "Creality Hyper PC",
    "08001": "Creality Ender-PLA", "09001": "Creality EN-PLA+", "09002": "Creality Ender Fast PLA",
    "10001": "Creality HP-TPU", "11001": "Creality CR-Nylon", "12002": "Creality Hyper PPA-CF",
    "12003": "Creality Hyper PAHT-CF", "13001": "Creality CR-PLA Carbon",
    "14001": "Creality CR-PLA Matte", "15001": "Creality CR-PLA Fluo", "16001": "Creality CR-TPU",
    "17001": "Creality CR-Wood", "18001": "Creality HP Ultra PLA", "19001": "Creality HP-ASA",
}


# ---------------------------------------------------------------- crypto
def _aes(key):
    return Cipher(algorithms.AES(key), modes.ECB())


def derive_key(uid: bytes) -> bytes:
    """Sector-1 MIFARE key = first 6 bytes of AES-ECB(UID_KEY, uid[0:4] repeated x4)."""
    block = bytes(uid[i % 4] for i in range(16))
    enc = _aes(UID_KEY).encryptor()
    return (enc.update(block) + enc.finalize())[:6]


def encrypt48(data: bytes) -> bytes:
    enc = _aes(DATA_KEY).encryptor()
    return enc.update(data) + enc.finalize()


def decrypt48(data: bytes) -> bytes:
    dec = _aes(DATA_KEY).decryptor()
    return dec.update(data) + dec.finalize()


def build_record(material: str, color: str, length: str, serial: str, printer: str) -> bytes:
    # date(5) vendor(4) batch(2) filamentId(6) color(7) length(4) serial(6) reserve(14) = 48
    s = ("AB124" + VENDOR_CREALITY + "A2" + "1" + material + "0" + color.upper()
         + length + serial + "0" * 14 + printer)
    assert len(s) >= 48
    return s.ljust(96).encode("ascii")


def parse_record(txt: str) -> dict:
    return {
        "date": txt[0:5], "vendor": txt[5:9], "batch": txt[9:11],
        "material": txt[12:17], "material_name": MATERIALS.get(txt[12:17], "?"),
        "color": "#" + txt[18:24], "length": txt[24:28],
        "weight": next((k for k, v in WEIGHTS.items() if v == txt[24:28]), "?"),
        "serial": txt[28:34], "printer": txt[48:].strip(),
    }


# ---------------------------------------------------------------- reader (ACR122-style pseudo-APDUs)
class ReaderStuck(IOError):
    """A PC/SC call never returned - macOS's smart-card service has wedged on the reader."""


PCSC_TIMEOUT = 4.0  # seconds; every real reader call finishes in well under one


def _guard(fn, *args, **kw):
    """Run one PC/SC call with a time limit, so a wedged reader can't freeze the app.
    The stuck call is left on a daemon thread; unplugging the reader releases it."""
    box = {}

    def run():
        try:
            box["v"] = fn(*args, **kw)
        except BaseException as e:  # noqa: B902 - re-raised in the caller's thread
            box["e"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(PCSC_TIMEOUT)
    if th.is_alive():
        raise ReaderStuck("The NFC reader stopped responding. Unplug it, plug it back in, then try again.")
    if "e" in box:
        raise box["e"]
    return box.get("v")


class Tag:
    def __init__(self, reader_index=0):
        rs = readers()
        if not rs:
            sys.exit("No PC/SC reader found. Plug it in, and quit NFC Agent / other NFC apps.")
        self.reader = rs[reader_index]
        self.conn = None

    def wait(self, prompt="Place tag on reader...", timeout=None, exclude_uid=None, cancel=None):
        """Block until a tag answers. Returns its UID, or None on timeout / when the
        `cancel` threading.Event is set.
        Transient reader/tag errors are retried; exclude_uid skips a tag you just handled."""
        if prompt:
            print(prompt, flush=True)
        end = time.time() + timeout if timeout else None
        while end is None or time.time() < end:
            if cancel is not None and cancel.is_set():
                return None
            try:
                self.conn = self.reader.createConnection()
                _guard(self.conn.connect, disposition=SCARD_LEAVE_CARD)
                time.sleep(0.15)  # let the tag finish powering up
                uid = bytes(self._tx([0xFF, 0xCA, 0x00, 0x00, 0x00]))
                if exclude_uid and uid.hex() == exclude_uid.lower():
                    self._drop()
                    time.sleep(0.5)
                    continue
                self.uid = uid
                return uid
            except ReaderStuck:
                raise  # retrying would only pile up more stuck calls
            except (SmartcardException, IOError):
                self._drop()
                time.sleep(0.3)
        return None

    def _drop(self):
        # SCARD_LEAVE_CARD: don't cut power, or the reader re-detects the tag and beeps
        conn, self.conn = self.conn, None
        if conn is None:
            return
        try:
            _guard(conn.disconnect)
        except Exception:
            pass

    close = _drop

    def wait_removed(self):
        while True:
            try:
                c = self.reader.createConnection()
                _guard(c.connect, disposition=SCARD_LEAVE_CARD)
                _guard(c.disconnect)
                time.sleep(0.3)
            except SmartcardException:
                return

    def _tx(self, apdu, ok=True):
        try:
            data, sw1, sw2 = _guard(self.conn.transmit, list(apdu))
        except ReaderStuck:
            raise
        except SmartcardException as e:  # tag moved/removed, reader hiccup
            raise IOError(f"Lost contact with the tag ({e}). Hold it still on the reader and retry.")
        if ok and (sw1, sw2) != (0x90, 0x00):
            raise IOError(f"APDU {bytes(apdu[:2]).hex()} failed: {sw1:02X}{sw2:02X}")
        return data if (sw1, sw2) == (0x90, 0x00) else None

    def _reselect(self):
        # A failed MIFARE auth halts the card. Reset it in place on the same handle;
        # dropping power and opening a brand-new connection right away can wedge macOS PC/SC.
        for _ in range(5):
            try:
                _guard(self.conn.reconnect, disposition=SCARD_RESET_CARD)
                time.sleep(0.1)
                return
            except ReaderStuck:
                raise
            except SmartcardException:
                time.sleep(0.2)
        raise IOError("Lost contact with the tag. Hold it still on the reader and retry.")

    def auth(self, block, key: bytes) -> bool:
        if self._tx([0xFF, 0x82, 0x00, 0x00, 0x06, *key], ok=False) is None:
            self._tx([0xFF, 0x82, 0x20, 0x00, 0x06, *key])
        res = self._tx([0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, block, 0x60, 0x00], ok=False)
        if res is None:
            self._reselect()
            return False
        return True

    def read(self, block) -> bytes:
        return bytes(self._tx([0xFF, 0xB0, 0x00, block, 16]))

    def write(self, block, data: bytes):
        assert len(data) == 16
        self._tx([0xFF, 0xD6, 0x00, block, 16, *data])


# ---------------------------------------------------------------- operations
def sector1_key(tag) -> bytes:
    """Return whichever key opens sector 1 (derived = already a CFS tag, default = blank)."""
    k = derive_key(tag.uid)
    if tag.auth(4, k):
        return k
    if tag.auth(4, KEY_DEFAULT):
        return KEY_DEFAULT
    raise IOError("Can't authenticate sector 1 (not blank, not CFS - official tags work too).")


def do_write(tag, record: bytes):
    k_cfs = derive_key(tag.uid)
    key = sector1_key(tag)
    enc = encrypt48(record[:48])
    for i in range(3):
        tag.write(4 + i, enc[i * 16:(i + 1) * 16])
    if key == KEY_DEFAULT:
        trailer = tag.read(7)
        access = trailer[6:10] if trailer[6:10] != b"\x00" * 4 else bytes.fromhex("FF078069")
        tag.write(7, k_cfs + access + k_cfs)
    if not tag.auth(8, KEY_DEFAULT):
        raise IOError("Can't authenticate sector 2 with default key")
    for i in range(3):
        tag.write(8 + i, record[48 + i * 16:48 + (i + 1) * 16])
    # verify
    tag.auth(4, k_cfs) or sys.exit("Verify failed: new key not accepted")
    got = decrypt48(b"".join(tag.read(b) for b in (4, 5, 6)))
    if got != record[:48]:
        raise IOError("Verify mismatch after write")


def do_read(tag) -> dict:
    key = sector1_key(tag)
    raw = b"".join(tag.read(b) for b in (4, 5, 6))
    if raw == bytes(48):
        raise IOError("Tag is blank (no CFS data written yet).")
    dec = decrypt48(raw)
    if key == KEY_DEFAULT or not dec.isascii() or dec[5:9] != VENDOR_CREALITY.encode():
        raise IOError("Tag doesn't contain a valid CFS record (not written by this tool/Creality).")
    txt = dec.decode("ascii")
    tail = ""
    if tag.auth(8, KEY_DEFAULT):
        tail = b"".join(tag.read(b) for b in (8, 9, 10)).decode("ascii", "replace")
    return parse_record(txt + tail)


def do_format(tag):
    key = sector1_key(tag)
    for b in (4, 5, 6):
        tag.write(b, bytes(16))
    if key != KEY_DEFAULT:
        trailer = tag.read(7)
        tag.write(7, KEY_DEFAULT + trailer[6:10] + KEY_DEFAULT)
    if tag.auth(8, KEY_DEFAULT):
        for b in (8, 9, 10):
            tag.write(b, bytes(16))


def main():
    p = argparse.ArgumentParser(description="Offline Creality CFS RFID tag tool")
    p.add_argument("--reader", type=int, default=0, help="reader index if you have several")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("materials")
    sub.add_parser("read")
    sub.add_parser("format")
    w = sub.add_parser("write")
    w.add_argument("-m", "--material", required=True, help="5-digit ID, e.g. 00001 (see 'materials')")
    w.add_argument("-c", "--color", required=True, help="hex RGB, e.g. FF6B35")
    w.add_argument("-w", "--weight", default="1kg", choices=WEIGHTS)
    w.add_argument("-p", "--printer", default="K2", choices=["K2", "K1", "HI"])
    w.add_argument("-s", "--serial", help="6 digits; default random (same for both tags of a spool)")
    w.add_argument("--count", type=int, default=2, help="tags per spool (CFS spools use 2)")
    a = p.parse_args()

    if a.cmd == "materials":
        for k, v in MATERIALS.items():
            print(k, v)
        return

    tag = Tag(a.reader)
    if a.cmd == "read":
        uid = tag.wait()
        print("UID", uid.hex().upper())
        for k, v in do_read(tag).items():
            print(f"  {k:14} {v}")
    elif a.cmd == "format":
        uid = tag.wait()
        do_format(tag)
        print("Formatted", uid.hex().upper())
    elif a.cmd == "write":
        color = a.color.lstrip("#")
        if len(color) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in color):
            sys.exit("Colour must be 6 hex digits, e.g. FF6B35")
        if not (len(a.material) == 5 and a.material.isdigit()):
            sys.exit("Material must be a 5-digit ID (see 'materials')")
        if a.serial:
            serial = a.serial
        else:
            import inventory  # shares the app's serial register so serials never repeat
            serial = inventory.new_serial()
        rec = build_record(a.material, color, WEIGHTS[a.weight], serial, a.printer)
        print(f"{MATERIALS.get(a.material, a.material)}  #{color.upper()}  {a.weight}  serial {serial}")
        for n in range(a.count):
            uid = tag.wait(f"[{n + 1}/{a.count}] Place tag on reader...")
            do_write(tag, rec)
            print(f"  wrote + verified {uid.hex().upper()}  - remove tag")
            tag.wait_removed()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
    except (IOError, SmartcardException) as e:
        sys.exit(f"Error: {e}")
