"""Driver for pyvz2's OBB/1BSR unpacker (GPL-3.0, github.com/nineteendo/pyvz2).

Reuses the archive parsing logic from OBBEdit/unpack.py without its interactive
prompts: extracts every named file of an 1BSR (OBB) and decodes RTON to JSON.

Usage: python work/obb_unpack.py <obb> <out_dir>
"""
import sys
import traceback
from io import BytesIO
from os import makedirs
from os.path import dirname, isdir, isfile, join as osjoin, sep
from struct import unpack
from zlib import decompress
import zstandard as zstd

_zstd = zstd.ZstdDecompressor()

def uncompress(buf, want=0):
    if buf[:4] == b"\x28\xb5\x2f\xfd":
        try:
            return _zstd.decompress(buf, max_output_size=want or (256 << 20))
        except Exception:
            return _zstd.stream_reader(BytesIO(buf)).read()
    return decompress(buf)

sys.path.insert(0, r"D:\OneDrive\文档\pvz_shuttle\work\deps\pyvz2-main\OBBEdit")
from libraries.pyvz2rijndael import RijndaelCBC  # noqa: E402
from libraries.pyvz2rton import RTONDecoder  # noqa: E402

OBB = sys.argv[1]
OUT = sys.argv[2]
LEVEL = 7  # decode RTON to JSON

warning_count = 0
written_count = 0


def warning_message(msg, *args):
    global warning_count
    warning_count += 1
    print("[warn]", msg, *args)


_seen_errors = set()

def error_message(e, *args):
    print("[error]", type(e).__name__, e, *args)
    key = type(e).__name__
    if key not in _seen_errors:
        _seen_errors.add(key)
        traceback.print_exc()


# RTON JSON style
comma = b","
doublePoint = b": "
indent = b"    "
current_indent = b"\r\n"
parse_root_object = RTONDecoder(comma, current_indent, doublePoint, False, indent,
                                False, False, False, warning_message).parse_root_object
rijndael_cbc = RijndaelCBC(b"00000000000000000000000000000000", 24)

pathStartsWith = ""
pathEndsWith = ""
rsgStartsWith = ""
rsgEndsWith = ""


def rsg_extract(RSG_NAME, file, pathout_data, out, pathout, level):
    global written_count
    try:
        HEADER = file.read(4)
        VERSION = unpack("<I", file.read(4))[0]
        file.seek(8, 1)
        COMPRESSION_FLAGS = unpack("<I", file.read(4))[0]
        HEADER_LENGTH = unpack("<I", file.read(4))[0]

        DATA_OFFSET = unpack("<I", file.read(4))[0]
        COMPRESSED_DATA_SIZE = unpack("<I", file.read(4))[0]
        DECOMPRESSED_DATA_SIZE = unpack("<I", file.read(4))[0]

        file.seek(4, 1)
        IMAGE_DATA_OFFSET = unpack("<I", file.read(4))[0]
        COMPRESSED_IMAGE_DATA_SIZE = unpack("<I", file.read(4))[0]
        DECOMPRESSED_IMAGE_DATA_SIZE = unpack("<I", file.read(4))[0]

        file.seek(20, 1)
        INFO_SIZE = unpack("<I", file.read(4))[0]
        INFO_OFFSET = unpack("<I", file.read(4))[0]
        INFO_LIMIT = INFO_OFFSET + INFO_SIZE

        data = None
        image_data = None
        if COMPRESSION_FLAGS & 2 == 0:
            data = bytearray(pathout_data[DATA_OFFSET: DATA_OFFSET + COMPRESSED_DATA_SIZE])
        elif COMPRESSED_DATA_SIZE != 0:
            data = bytearray(uncompress(pathout_data[DATA_OFFSET: DATA_OFFSET + COMPRESSED_DATA_SIZE], DECOMPRESSED_DATA_SIZE))
        if DECOMPRESSED_IMAGE_DATA_SIZE != 0:
            if COMPRESSION_FLAGS & 1 == 0:
                image_data = bytearray(pathout_data[IMAGE_DATA_OFFSET: IMAGE_DATA_OFFSET + COMPRESSED_IMAGE_DATA_SIZE])
            else:
                image_data = bytearray(uncompress(pathout_data[IMAGE_DATA_OFFSET: IMAGE_DATA_OFFSET + COMPRESSED_IMAGE_DATA_SIZE], DECOMPRESSED_IMAGE_DATA_SIZE))

        NAME_DICT = {}
        temp = INFO_OFFSET
        file.seek(INFO_OFFSET)
        while temp < INFO_LIMIT:
            FILE_NAME = b""
            for key in list(NAME_DICT.keys()):
                if NAME_DICT[key] + INFO_OFFSET < temp:
                    NAME_DICT.pop(key)
                else:
                    FILE_NAME = key
            BYTE = b""
            while BYTE != b"\0":
                FILE_NAME += BYTE
                BYTE = file.read(1)
                LENGTH = 4 * unpack("<I", file.read(3) + b"\0")[0]
                if LENGTH != 0:
                    NAME_DICT[FILE_NAME] = LENGTH

            DECODED_NAME = FILE_NAME.decode(errors="replace").replace("\\", sep)
            NAME_CHECK = DECODED_NAME.replace("\\", "/").lower()
            IS_IMAGE = unpack("<I", file.read(4))[0] == 1
            FILE_OFFSET = unpack("<I", file.read(4))[0]
            FILE_SIZE = unpack("<I", file.read(4))[0]
            if IS_IMAGE:
                file.seek(20, 1)
            if DECODED_NAME and NAME_CHECK.startswith(pathStartsWith) and NAME_CHECK.endswith(pathEndsWith):
                if IS_IMAGE:
                    if image_data is None:
                        warning_message("missing image data " + file.name + ":" + DECODED_NAME)
                        temp = file.tell()
                        continue
                    file_data = image_data[FILE_OFFSET: FILE_OFFSET + FILE_SIZE]
                else:
                    file_data = data[FILE_OFFSET: FILE_OFFSET + FILE_SIZE]

                if NAME_CHECK[-5:] == ".rton" and file_data[:2] == b"\x10\0" and 5 < level:
                    file_data = rijndael_cbc.decrypt(file_data[2:])
                if NAME_CHECK[-5:] == ".rton" and 6 == level and file_data[:4] != b"RTON":
                    warning_message("No RTON " + file.name + ":" + DECODED_NAME)
                else:
                    file_path = osjoin(out, DECODED_NAME)
                    makedirs(dirname(file_path), exist_ok=True)
                    wrote = False
                    if level > 6 and NAME_CHECK[-5:] == ".rton":
                        try:
                            file_path = osjoin(out, DECODED_NAME[:-5] + ".JSON")
                            source = BytesIO(file_data)
                            source.name = file.name + ":" + DECODED_NAME
                            source.read(4)
                            file_data = parse_root_object(source)
                            open(file_path, "wb").write(file_data)
                            wrote = True
                        except Exception as e:
                            error_message(e, " in " + file.name + ": " + RSG_NAME + ":" + DECODED_NAME)
                    if not wrote:
                        open(file_path, "wb").write(file_data)
                    written_count += 1
                    if written_count % 200 == 0:
                        print(f"[{written_count}] {DECODED_NAME}")
            temp = file.tell()
    except Exception as e:
        error_message(e, " while extracting " + getattr(file, "name", "?"))


def rsb_extract(file, pathout_data, out, level, pathout):
    VERSION = unpack('<L', file.read(4))[0]
    file.seek(4, 1)
    HEADER_SIZE = unpack('<L', file.read(4))[0]
    FILE_LIST_SIZE = unpack('<L', file.read(4))[0]
    FILE_LIST_OFFSET = unpack('<L', file.read(4))[0]
    file.seek(8, 1)
    SUBGROUP_LIST_SIZE = unpack('<L', file.read(4))[0]
    SUBGROUP_LIST_OFFSET = unpack('<L', file.read(4))[0]
    SUBGROUP_INFO_ENTRIES = unpack("<I", file.read(4))[0]
    SUBGROUP_INFO_OFFSET = unpack("<I", file.read(4))[0]
    SUBGROUP_INFO_ENTRY_SIZE = unpack('<L', file.read(4))[0]
    GROUP_INFO_ENTRIES = unpack('<L', file.read(4))[0]
    GROUP_INFO_OFFSET = unpack('<L', file.read(4))[0]
    GROUP_INFO_ENTRY_SIZE = unpack('<L', file.read(4))[0]
    GROUP_LIST_SIZE = unpack('<L', file.read(4))[0]
    GROUP_LIST_OFFSET = unpack('<L', file.read(4))[0]
    AUTOPOOL_INFO_ENTRIES = unpack('<L', file.read(4))[0]
    AUTOPOOL_INFO_OFFSET = unpack('<L', file.read(4))[0]
    AUTOPOOL_INFO_ENTRY_SIZE = unpack('<L', file.read(4))[0]
    PTX_INFO_ENTRIES = unpack('<L', file.read(4))[0]
    PTX_INFO_OFFSET = unpack('<L', file.read(4))[0]
    PTX_INFO_ENTRY_SIZE = unpack('<L', file.read(4))[0]
    DIRECTORY_7_OFFSET = unpack('<L', file.read(4))[0]
    DIRECTORY_8_OFFSET = unpack('<L', file.read(4))[0]
    DIRECTORY_9_OFFSET = unpack('<L', file.read(4))[0]
    if VERSION == 4:
        HEADER_SIZE_2 = unpack('<L', file.read(4))[0]

    print(f"1BSR v{VERSION}: subgroups={SUBGROUP_INFO_ENTRIES} entries, groups={GROUP_INFO_ENTRIES}, ptx={PTX_INFO_ENTRIES}")

    file.seek(SUBGROUP_INFO_OFFSET)
    for i in range(0, SUBGROUP_INFO_ENTRIES):
        info_start = file.tell()
        RSG_NAME = file.read(128).strip(b"\0").decode(errors="replace")
        RSG_OFFSET = unpack("<I", file.read(4))[0]
        RSG_SIZE = unpack("<I", file.read(4))[0]
        SUBGROUP_ID = unpack("<I", file.read(4))[0]
        RSG_COMPRESSION_FLAGS = unpack("<I", file.read(4))[0]
        RSG_HEADER_LENGTH = unpack("<I", file.read(4))[0]
        RSG_DATA_OFFSET = unpack("<I", file.read(4))[0]
        RSG_COMPRESSED_DATA_SIZE = unpack("<I", file.read(4))[0]
        RSG_DECOMPRESSED_DATA_SIZE = unpack("<I", file.read(4))[0]
        RSG_DECOMPRESSED_DATA_SIZE_B = unpack("<I", file.read(4))[0]
        RSG_IMAGE_DATA_OFFSET = unpack("<I", file.read(4))[0]
        RSG_COMPRESSED_IMAGE_DATA_SIZE = unpack("<I", file.read(4))[0]
        RSG_DECOMPRESSED_IMAGE_DATA_SIZE = unpack("<I", file.read(4))[0]
        file.seek(20, 1)
        IMAGE_ENTRIES = unpack("<I", file.read(4))[0]
        IMAGE_ID = unpack("<I", file.read(4))[0]

        RSG_CHECK = RSG_NAME.lower()
        RSG_SIZE = RSG_IMAGE_DATA_OFFSET + RSG_COMPRESSED_IMAGE_DATA_SIZE
        if RSG_CHECK.startswith(rsgStartsWith) and RSG_CHECK.endswith(rsgEndsWith):
            subdata = time_slice = pathout_data[RSG_OFFSET: RSG_OFFSET + RSG_SIZE]
            subdata = bytearray(subdata)
            subdata[:4] = b"pgsr"
            subdata[16:36] = pathout_data[info_start + 140:info_start + 160]
            subdata[40:52] = pathout_data[info_start + 164:info_start + 176]
            if level < 4:
                open(osjoin(out, RSG_NAME + ".rsg"), "wb").write(subdata)
            else:
                subfile = BytesIO(subdata)
                subfile.name = getattr(file, "name", "?") + ":" + RSG_NAME
                rsg_extract(RSG_NAME, subfile, subdata, out, pathout, level)
        if i % 100 == 0:
            print(f"subgroup {i}/{SUBGROUP_INFO_ENTRIES} {RSG_NAME}")


def main():
    makedirs(OUT, exist_ok=True)
    with open(OBB, "rb") as f:
        HEADER = f.read(4)
        COMPRESSED = HEADER == b"\xD4\xFE\xAD\xDE"
        if COMPRESSED:
            raise SystemExit("compressed 1BSR not supported by this driver")
        if HEADER != b"1bsr":
            raise SystemExit("not a 1bsr: " + HEADER.hex())
        pathout_data = HEADER + f.read()
        f.seek(4)
        rsb_extract(f, bytearray(pathout_data), OUT, LEVEL, OUT)
    print(f"done: {written_count} files, {warning_count} warnings")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
