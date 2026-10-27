"""Tag format: keys, encryption and the 48-byte spool record."""
import cfs_tag
import printer


def test_sector_key_derived_from_uid():
    # value seen on a real blank tag (UID 4575510A) with the ACR122U
    assert cfs_tag.derive_key(bytes.fromhex("4575510A")).hex() == "61d0b4abc566"


def test_encrypt_round_trip():
    data = bytes(range(48))
    enc = cfs_tag.encrypt48(data)
    assert enc != data and len(enc) == 48
    assert cfs_tag.decrypt48(enc) == data


def test_record_build_and_parse():
    rec = cfs_tag.build_record("01001", "FF6B35", cfs_tag.WEIGHTS["1kg"], "123456", "K2")
    assert len(rec) == 96
    parsed = cfs_tag.parse_record(rec.decode())
    assert parsed["vendor"] == cfs_tag.VENDOR_CREALITY
    assert parsed["material"] == "01001"
    assert parsed["material_name"] == "Creality Hyper PLA"
    assert parsed["color"] == "#FF6B35"
    assert parsed["weight"] == "1kg"
    assert parsed["serial"] == "123456"
    assert parsed["printer"] == "K2"


def test_printer_reads_the_same_record():
    # the CFS reports the decrypted record it read; the app must parse what it writes
    rec = cfs_tag.build_record("09001", "FF0000", cfs_tag.WEIGHTS["1kg"], "460882", "K2")[:48].decode()
    tag = printer.parse_tag_record(rec)
    assert tag == {"material": "09001", "color": "FF0000", "length": "0330", "serial": "460882", "vendor": "0276"}


def test_printer_tag_record_from_a_real_k2():
    # exactly as Klipper's 'box' object reported it on a K2 Pro
    tag = printer.parse_tag_record("AB1240276A21090010FF00000330460882000000")
    assert (tag["material"], tag["color"], tag["serial"]) == ("09001", "FF0000", "460882")
    assert printer.parse_tag_record("none") is None
    assert printer.parse_tag_record("") is None


def test_reads_crealitys_own_tags():
    """Creality's own spools: the record, then bytes that aren't text where Spoolhouse writes '0's."""
    import cfs_tag as cfs
    record = b"6C9260276A21010010FFFFFF0165000001"
    for filler in (0x00, 0xFF):
        txt = cfs.record_text(record + bytes([filler]) * (48 - len(record)))
        rec = cfs.parse_record(txt)
        assert (rec["material"], rec["color"], rec["serial"], rec["weight"]) == ("01001", "#FFFFFF", "000001", "500g")
    assert cfs.record_text(b"A" * 48) is None  # not a CFS record
