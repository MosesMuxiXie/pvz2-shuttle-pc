#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
bake_actors.py -- extract authentic DragonBones actor packs from the live
Cocos web build of PvZ2 Gardendless (https://play.pvzge.com/) over CDP.

WHAT IT DOES
------------
For every job (one Cocos prefab path) it opens the prefab in the running
headless-Chrome page, walks the node tree, finds the first
``dragonBones.ArmatureDisplay`` component, and writes:

    assets/db/<key>/skeleton.json   DragonBones 5.5 JSON (armature/bone/slot/skin/animation)
    assets/db/<key>/atlas.json      DragonBones texture-atlas JSON (SubTexture[])
    assets/db/<key>/texture.png     atlas texture, decoded from the site AVIF -> RGBA PNG
    assets/db/<key>/meta.json       provenance + armature/animation/size inventory

and finally ``assets/db/MANIFEST.json``::

    {
      "generated": "2026-11-09T15:02:11+08:00",
      "source": {"site": ..., "release": ..., "bundle": "resources"},
      "count": 69,
      "actors": [ {"key","prefab","armature","animations","size",
                   "texture_size","armatures","dir"} , ... ],
      "aliases": { "ConeheadZOMBIE": {"key": ..., "armature": "Cone", ...} },
      "failures": [ {"key","prefab","stage","error"} ]
    }

Read the actor rows with ``json.load(f)["actors"]``.

USAGE
-----
    # extract the whole curated list (see tools/actors.json)
    python tools/bake_actors.py --jobs tools/actors.json

    # one-off / re-run selected keys
    python tools/bake_actors.py --jobs tools/actors.json --only plants/PeashooterPLANT
    python tools/bake_actors.py --jobs tools/actors.json --only plants/PeashooterPLANT --force

    # validate already-baked output (parses JSON + opens every PNG)
    python tools/bake_actors.py --verify-all
    python tools/bake_actors.py --verify 3

    # plain text job list also works: one 'key|prefab' or 'prefab' per line
    python tools/bake_actors.py --jobs my_list.txt --out assets/db

NOTES / GOTCHAS (learned the hard way)
--------------------------------------
* The page must be the live game: chrome --headless=new --remote-debugging-port=9333.
  If the port is dead the tool tells you the exact relaunch command.
* Skeleton strings are 30 KB - 300 KB; they are returned by CDP ``returnByValue``
  in a single ``Runtime.evaluate`` per actor (~1-4 s each). No chunking needed.
* The resources bundle base is relative ("assets/resources/"); the real release
  root is discovered at runtime from ``performance.getEntriesByType('resource')``
  (first ``/releases/<40 hex>/`` URL) so the tool keeps working after a game update.
  ``--release <url>`` overrides it.
* Atlas textures are AVIF; Pillow >= 11 with the ``avif`` feature decodes them.
  Textures are de-duplicated by asset uuid in a local cache.
* Many prefabs share an identical skeleton (all world base zombies share one
  292 KB skeleton). Identical files are hard-linked where the filesystem allows
  it (``os.link``) and copied otherwise, so every ``db/<key>/`` directory is
  complete and self-contained. ``--no-hardlink`` forces copies. Note that
  OneDrive-synced folders may break links later; the db stays small either way
  because only ~60 distinct skeletons/atlases/textures back the 70 actors.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    import websocket  # websocket-client
except ImportError:  # pragma: no cover
    websocket = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
GAME_ROOT = os.path.dirname(TOOLS_DIR)                     # PvZ2SHUTTLE
DEFAULT_OUT = os.path.join(GAME_ROOT, "assets", "db")
DEFAULT_JOBS = os.path.join(TOOLS_DIR, "actors.json")
DEFAULT_MANIFEST = os.path.join(DEFAULT_OUT, "MANIFEST.json")

SITE = "https://play.pvzge.com/"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #


def log(msg=""):
    print(msg, flush=True)


def now_iso():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def link_or_copy(src, dst):
    """Place ``src`` at ``dst`` using a hard link when possible (dedupes big
    shared skeletons on NTFS), falling back to a copy."""
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def dump_json(path, obj, compact=False):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        if compact:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
            fh.write("\n")


# --------------------------------------------------------------------------- #
# CDP client (one persistent websocket, reconnect on failure)
# --------------------------------------------------------------------------- #

_CDP_PAGE_EXPR = r"""
(async () => {
  /* ---- returns bundle + release root, used once per run ---- */
  const b = cc.assetManager.getBundle('resources');
  let release = null;
  try {
    const urls = performance.getEntriesByType('resource').map(e => e.name);
    const hit = urls.find(u => /\/releases\/[0-9a-f]{40}\//.test(u));
    if (hit) release = hit.match(/^(.*?\/releases\/[0-9a-f]{40}\/)/)[1];
  } catch (e) {}
  if (!release) {
    const m = (location.href || '').match(/^(.*?\/releases\/[0-9a-f]{40}\/)/);
    if (m) release = m[1];
  }
  return JSON.stringify({
    release: release,
    bundleBase: b ? (b.base || null) : null,
    version: (cc.ENGINE_VERSION || null),
  });
})()
"""

# %s -> json-quoted prefab path
_CDP_ACTOR_EXPR = r"""
(async () => {
  const PREFAB = %s;
  const bundle = cc.assetManager.getBundle('resources');
  if (!bundle) throw new Error('resources bundle not loaded');
  const pf = await new Promise((res, rej) =>
    bundle.load(PREFAB, cc.Prefab, (e, x) => e ? rej(e) : res(x)));
  const root = cc.instantiate(pf);
  const displays = [];
  const nodes = [];
  (function walk(n, path, depth) {
    let size = null;
    const ut = n.getComponent && n.getComponent('cc.UITransform');
    if (ut) size = [ut.contentSize.width, ut.contentSize.height];
    nodes.push({path: path, active: n.activeInHierarchy, size: size});
    for (const c of n.components) {
      if (!c.dragonAsset || !c.dragonAsset._dragonBonesJson) continue;
      const atlasAsset = c.dragonAtlasAsset || null;
      let texUrl = null, texUuid = null, texW = null, texH = null;
      try {
        const img = atlasAsset && atlasAsset.texture && atlasAsset.texture.image;
        if (img) {
          texUrl = img.nativeUrl || img._nativeUrl || null;
          texUuid = img.uuid || img._uuid || null;
          texW = img.width || null;
          texH = img.height || null;
        }
      } catch (e) {}
      displays.push({
        node: path,
        active: n.activeInHierarchy,
        armature: c._armatureName || null,
        animation: c._animationName || null,
        drawOrder: (typeof c._zIndex === 'number') ? c._zIndex : null,
        playTimes: (typeof c.playTimes === 'number') ? c.playTimes : null,
        nodeSize: size,
        nodeScale: [n.scale.x, n.scale.y],
        skeleton: c.dragonAsset._dragonBonesJson,
        skeletonUuid: c.dragonAsset._uuid || null,
        atlas: atlasAsset ? (atlasAsset._atlasJson || null) : null,
        atlasUuid: atlasAsset ? (atlasAsset._uuid || null) : null,
        textureUrl: texUrl, textureUuid: texUuid,
        textureW: texW, textureH: texH
      });
    }
    for (const ch of n.children) walk(ch, path + '/' + ch.name, depth + 1);
  })(root, root.name, 0);
  let rootSize = null;
  const rut = root.getComponent && root.getComponent('cc.UITransform');
  if (rut) rootSize = [rut.contentSize.width, rut.contentSize.height];
  const out = {
    prefab: PREFAB, prefabUuid: pf._uuid || null,
    rootName: root.name, rootSize: rootSize,
    rootScale: [root.scale.x, root.scale.y],
    displays: displays, nodes: nodes
  };
  root.destroy();
  return JSON.stringify(out);
})()
"""


class CDPError(RuntimeError):
    pass


class Page:
    """Minimal single-target CDP page wrapper."""

    def __init__(self, port=9333, timeout=300.0, verbose=False):
        if websocket is None:
            raise CDPError("websocket-client is not installed")
        self.port = port
        self.timeout = timeout
        self.verbose = verbose
        self.ws = None
        self._id = 0
        self.info = {}

    # -- connection -------------------------------------------------------
    def _targets(self):
        url = f"http://127.0.0.1:{self.port}/json/list"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001
            raise CDPError(
                f"cannot reach CDP on 127.0.0.1:{self.port} ({exc}).\n"
                "Relaunch headless Chrome:\n"
                '  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
                "--headless=new --remote-debugging-port=%d "
                "--user-data-dir=D:\\OneDrive\\文档\\pvz_shuttle\\work\\chrome-prof "
                "--window-size=1280,720 --enable-unsafe-swiftshader "
                "--angle=swiftshader \"https://play.pvzge.com/\"\n"
                "then wait ~25 s for the game to boot." % self.port
            ) from exc

    def connect(self):
        pages = [t for t in self._targets() if t.get("type") == "page"]
        if not pages:
            raise CDPError("no page target on the CDP endpoint")
        page = next((p for p in pages if "pvzge" in (p.get("url") or "")), pages[0])
        self.ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], timeout=self.timeout,
            max_size=256 * 1024 * 1024)
        self.info = {"title": page.get("title"), "url": page.get("url")}
        if self.verbose:
            log(f"  CDP page: {page.get('title')!r} {page.get('url')}")
        return self

    def close(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:  # noqa: BLE001
                pass
            self.ws = None

    # -- evaluate ---------------------------------------------------------
    def eval(self, expr, timeout=None):
        if self.ws is None:
            self.connect()
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({
            "id": mid,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "awaitPromise": True,
                       "returnByValue": True, "timeout": int((timeout or self.timeout) * 1000)},
        }))
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            raw = self.ws.recv()
            if not raw:
                raise CDPError("CDP socket closed")
            msg = json.loads(raw)
            if msg.get("id") != mid:
                continue
            res = msg.get("result") or {}
            if "exceptionDetails" in res:
                det = res["exceptionDetails"]
                text = ""
                try:
                    text = det["exception"]["description"]
                except Exception:  # noqa: BLE001
                    text = det.get("text") or str(det)
                raise CDPError(text.strip().splitlines()[0][:400])
            return res.get("result", {}).get("value")
        raise CDPError("Runtime.evaluate timed out after %.0fs" % (timeout or self.timeout))


# --------------------------------------------------------------------------- #
# texture download / decode
# --------------------------------------------------------------------------- #


class TextureCache:
    """uuid -> decoded PNG bytes. Survives per-run reconnects; optional disk cache."""

    def __init__(self, cache_dir=None, release=None, retries=3, verbose=False):
        self.mem = {}
        self.dir = cache_dir
        self.release = release
        self.retries = retries
        self.verbose = verbose
        if cache_dir:
            ensure_dir(cache_dir)

    def resolve_url(self, native_url):
        if not native_url:
            return None
        if native_url.startswith("http://") or native_url.startswith("https://"):
            return native_url
        if not self.release:
            raise CDPError("release root unknown; pass --release https://host/releases/<hash>/")
        return self.release + native_url.lstrip("/")

    def _download(self, url):
        last = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": USER_AGENT, "Referer": SITE,
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                })
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.read()
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code in (403, 404):
                    break
                time.sleep(0.6 * (attempt + 1))
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(0.6 * (attempt + 1))
        raise CDPError(f"texture download failed: {url} ({last})")

    def png_bytes(self, native_url, uuid=None):
        key = uuid or native_url
        if key in self.mem:
            return self.mem[key]
        disk = os.path.join(self.dir, f"{(uuid or hashlib.sha1(native_url.encode()).hexdigest())}.png") \
            if self.dir else None
        if disk and os.path.exists(disk):
            with open(disk, "rb") as fh:
                data = fh.read()
            self.mem[key] = data
            return data
        url = self.resolve_url(native_url)
        raw = self._download(url)
        if Image is None:
            raise CDPError("Pillow not available; cannot decode texture")
        try:
            im = Image.open(io.BytesIO(raw))
            im.load()
        except Exception as exc:  # noqa: BLE001
            raise CDPError(f"cannot decode texture {url}: {exc}") from exc
        src_fmt = im.format
        im = im.convert("RGBA")
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=False, compress_level=6)
        data = buf.getvalue()
        self.mem[key] = data
        self._last = {"format": src_fmt, "bytes": len(raw), "size": list(im.size)}
        if disk:
            with open(disk, "wb") as fh:
                fh.write(data)
        return data

    def info(self, native_url, uuid=None):
        self.png_bytes(native_url, uuid)
        return getattr(self, "_last", {})


# --------------------------------------------------------------------------- #
# skeleton / atlas analysis
# --------------------------------------------------------------------------- #


def analyse_skeleton(skel):
    """Return (armatures, warnings) with per-armature inventory."""
    out = []
    warns = []
    for arm in skel.get("armature", []) or []:
        name = arm.get("name") or ""
        if not name:
            warns.append("armature without name")
        animations = []
        for anim in arm.get("animation", []) or []:
            if anim.get("name"):
                animations.append(anim["name"])
        default_anim = None
        for act in arm.get("defaultActions", []) or []:
            got = (act.get("gotoAndPlay") or "")
            if got:
                default_anim = got
                break
        aabb = arm.get("aabb") or {}
        size = None
        if aabb:
            size = [round(float(aabb.get("width", 0)), 2),
                    round(float(aabb.get("height", 0)), 2)]
        slots = arm.get("slot", []) or []
        bones = arm.get("bone", []) or []
        # dragonbones 5.5: skin is a list of {name, slot:[{name, display:[{name,path,type}]}]}
        # NOTE: display.path (not name) is the texture-atlas SubTexture key whenever
        # the exporter wrote a path, so both have to be kept for atlas cross-checking.
        display_refs = []
        for skin in arm.get("skin", []) or []:
            for slot in skin.get("slot", []) or []:
                for disp in slot.get("display", []) or []:
                    if disp.get("type", 0) == 0:
                        display_refs.append({"name": disp.get("name"),
                                             "path": disp.get("path")})
        displays = [d["name"] or d["path"] for d in display_refs if (d["name"] or d["path"])]
        out.append({
            "name": name,
            "frameRate": arm.get("frameRate"),
            "type": arm.get("type"),
            "animations": animations,
            "animation_count": len(animations),
            "default_animation": default_anim,
            "size": size,
            "aabb": {k: round(float(aabb.get(k, 0)), 2) for k in ("x", "y", "width", "height")} if aabb else None,
            "bones": len(bones),
            "slots": len(slots),
            "displays": len(display_refs),
            "display_names": displays,
            "display_refs": display_refs,
        })
    return out, warns


def analyse_atlas(atlas):
    subs = atlas.get("SubTexture") or []
    info = {
        "imagePath": atlas.get("imagePath"),
        "name": atlas.get("name"),
        "width": atlas.get("width"),
        "height": atlas.get("height"),
        "subtextures": len(subs),
        "subtexture_names": [s.get("name") for s in subs if s.get("name")],
        "has_frames": any(("frameX" in s) for s in subs),
    }
    return info


def cross_check(armatures, atlas_info):
    """Slots referencing displays absent from the atlas (a real data bug worth reporting)."""
    have = set(atlas_info.get("subtexture_names") or [])
    if not have:
        return []
    missing = []
    for arm in armatures:
        for ref in arm.get("display_refs") or []:
            name, path = ref.get("name"), ref.get("path")
            if (name in have) or (path in have):
                continue
            missing.append(f"{arm['name']}:{name or path}")
    return sorted(set(missing))


# --------------------------------------------------------------------------- #
# job list
# --------------------------------------------------------------------------- #


def _norm_job(entry, origin="?"):
    if isinstance(entry, str):
        entry = {"prefab": entry}
    prefab = entry.get("prefab") or entry.get("key")
    if not prefab:
        raise ValueError(f"job without prefab/key in {origin}: {entry!r}")
    key = entry.get("key") or prefab
    job = {
        "key": key,
        "prefab": prefab,
        "requested": entry.get("requested") or entry.get("name"),
        "armature": entry.get("armature"),
        "note": entry.get("note"),
        "group": entry.get("group"),
    }
    if entry.get("alias_of"):
        job["alias_of"] = entry["alias_of"]
    return job


def load_jobs(path):
    """Accept JSON (list or {"actors":[...]}) or a text file of 'key|prefab' lines.

    Returns ``(jobs, extras)``.  A JSON job file may carry

    * ``"armature_aliases"``: requested-name -> {key, armature, note} for actors
      that only exist as an extra armature inside another skeleton
      (e.g. "ConeheadZOMBIE" -> zombies/BasicZOMBIE + armature "Cone");
    * ``"armor_prefabs"``: armour prefab -> {key, armature, note}, verified
      mappings from armors/*ARMOR onto the baked zombie skeleton that holds the
      armature (so consumers do not have to ship duplicate skeletons).
    """
    if not os.path.exists(path):
        raise SystemExit(f"job list not found: {path}")
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        data = json.loads(text)
        extras = {}
        if isinstance(data, dict):
            extras = {k: (data.get(k) or {}) for k in ("armature_aliases", "armor_prefabs")}
            data = data.get("actors") or data.get("jobs") or []
        return [_norm_job(e, path) for e in data], extras
    jobs = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            key, _, prefab = line.partition("|")
        else:
            key, prefab = line, line
        jobs.append(_norm_job({"key": key.strip(), "prefab": prefab.strip()}, f"{path}:{lineno}"))
    return jobs, {}


# --------------------------------------------------------------------------- #
# extraction of one actor
# --------------------------------------------------------------------------- #


def pick_primary(displays):
    """Choose the gameplay armature display (node *Body preferred)."""
    if not displays:
        return None
    for d in displays:
        if d.get("armature") and d["node"].split("/")[-1].lower() == "body":
            return d
    for d in displays:
        if d.get("armature"):
            return d
    return displays[0]


def _norm_name(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


_PREFAB_SUFFIXES = ("plant", "zombie", "prj", "armor")


def prefab_base(prefab):
    """plants/UmbrellaLeafPLANT -> 'umbrellaLeaf'; zombies/EgyptBasicZOMBIE -> 'egyptbasic'."""
    base = _norm_name(prefab.split("/")[-1])
    for suf in _PREFAB_SUFFIXES:
        if base.endswith(suf) and len(base) > len(suf):
            return base[: -len(suf)]
    return base


def prefer_named_armature(prefab, armatures, current):
    """Some prefabs author a *split part* as the display armature (UmbrellaLeaf
    subscribes 'lower' while the skeleton also holds the full 'UmbrellaLeaf'
    rig).  Prefer an armature whose name matches the prefab basename, in the
    order exact -> armature-extends-basename -> basename-extends-armature."""
    names = [a["name"] for a in (armatures or []) if a.get("name")]
    base = prefab_base(prefab)
    if not base:
        return current
    for nm in names:                                   # exact
        if _norm_name(nm) == base:
            return nm
    for nm in names:                                   # 'EgyptBasicZombie' for ...ZOMBIE
        if _norm_name(nm).startswith(base):
            return nm
    for nm in names:                                   # 'Wall-nut' style truncation
        n = _norm_name(nm)
        if base.startswith(n) and len(n) >= 0.75 * len(base):
            return nm
    return current


def extract_one(page, tex_cache, job, out_root, force=False, hardlink=True,
                keep_skeleton=True):
    key = job["key"]
    prefab = job["prefab"]
    dest = os.path.join(out_root, *key.split("/"))
    skel_path = os.path.join(dest, "skeleton.json")
    if os.path.exists(skel_path) and not force:
        try:
            with open(os.path.join(dest, "meta.json"), encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception:  # noqa: BLE001
            meta = None
        tpath = os.path.join(dest, "texture.png")
        if meta and os.path.exists(tpath) and os.path.getsize(tpath) > 0:
            return {"status": "skipped", "key": key, "meta": meta}

    raw = page.eval(_CDP_ACTOR_EXPR % json.dumps(prefab))
    if not raw:
        raise CDPError("empty evaluate result")
    data = json.loads(raw)
    displays = data.get("displays") or []
    if not displays:
        raise CDPError("prefab has no DragonBones ArmatureDisplay (not an actor prefab)")

    primary = pick_primary(displays)
    try:
        skel = json.loads(primary["skeleton"])
    except Exception as exc:  # noqa: BLE001
        raise CDPError(f"skeleton JSON is not valid JSON: {exc}") from exc
    if not (skel.get("armature") and skel.get("frameRate")):
        raise CDPError("skeleton JSON lacks 'armature'/'frameRate' (not DragonBones)")

    armatures, warns = analyse_skeleton(skel)

    atlas_obj, atlas_info = None, {}
    if primary.get("atlas"):
        try:
            atlas_obj = json.loads(primary["atlas"])
        except Exception as exc:  # noqa: BLE001
            raise CDPError(f"atlas JSON is not valid JSON: {exc}") from exc
        atlas_info = analyse_atlas(atlas_obj)
        if not atlas_info.get("subtextures"):
            raise CDPError("atlas JSON has no SubTexture entries")
    else:
        warns.append("atlas display data missing (skeleton-only export)")

    # ---- texture -------------------------------------------------------
    tex_info = {}
    png = None
    if primary.get("textureUrl"):
        try:
            png = tex_cache.png_bytes(primary["textureUrl"], primary.get("textureUuid"))
            tex_info = dict(getattr(tex_cache, "_last", {}) or {})
            tex_info["source"] = primary["textureUrl"]
            tex_info["uuid"] = primary.get("textureUuid")
        except CDPError as exc:
            return {"status": "failed", "key": key, "prefab": prefab,
                    "stage": "texture", "error": str(exc)}
    else:
        warns.append("no texture nativeUrl on atlas asset")

    # ---- write ---------------------------------------------------------
    ensure_dir(dest)
    staging = tempfile.mkdtemp(prefix="bake_", dir=out_root)
    try:
        # compact skeleton/atlas: identical bytes for identical input -> hardlinks dedupe
        s_bytes = json.dumps(skel, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(os.path.join(staging, "skeleton.json"), "wb") as fh:
            fh.write(s_bytes)
        if atlas_obj is not None:
            a_bytes = json.dumps(atlas_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            with open(os.path.join(staging, "atlas.json"), "wb") as fh:
                fh.write(a_bytes)
        if png:
            with open(os.path.join(staging, "texture.png"), "wb") as fh:
                fh.write(png)

        moves = []
        for name in ("skeleton.json", "atlas.json", "texture.png"):
            src = os.path.join(staging, name)
            if os.path.exists(src):
                moves.append(name)
        for name in moves:
            src, dst = os.path.join(staging, name), os.path.join(dest, name)
            if hardlink:
                link_or_copy(src, dst)
            else:
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.copy2(src, dst)

        chosen = primary.get("armature") or (armatures[0]["name"] if armatures else None)
        # if an explicit armature was requested, honour it when present
        if job.get("armature"):
            names = {a["name"] for a in armatures}
            if job["armature"] in names:
                chosen = job["armature"]
            else:
                warns.append(f"requested armature {job['armature']!r} not in skeleton "
                             f"(have {sorted(names)[:8]})")
        else:
            better = prefer_named_armature(prefab, armatures, chosen)
            if better != chosen:
                warns.append(f"display subscribed armature {chosen!r}; using prefab-matching "
                             f"armature {better!r} (fuller rig)")
                chosen = better

        arm_meta = next((a for a in armatures if a["name"] == chosen),
                        armatures[0] if armatures else None)
        size = (arm_meta or {}).get("size") or data.get("rootSize")
        meta = {
            "key": key,
            "prefab": prefab,
            "prefab_uuid": data.get("prefabUuid"),
            "requested": job.get("requested"),
            "note": job.get("note"),
            "group": job.get("group"),
            "armature": chosen,
            "animations": (arm_meta or {}).get("animations", []),
            "default_animation": (arm_meta or {}).get("default_animation"),
            "size": size,
            "texture_size": tex_info.get("size") or [primary.get("textureW"), primary.get("textureH")],
            "aabb": (arm_meta or {}).get("aabb"),
            "armatures": [{"name": a["name"], "animations": a["animations"],
                           "size": a["size"], "bones": a["bones"], "slots": a["slots"],
                           "default_animation": a["default_animation"]}
                          for a in armatures],
            "atlas": {k: atlas_info.get(k) for k in
                      ("imagePath", "width", "height", "subtextures", "has_frames")},
            "texture": {k: tex_info.get(k) for k in ("source", "uuid", "format", "bytes", "size")},
            "skeleton": {"frameRate": skel.get("frameRate"),
                         "version": skel.get("version"),
                         "name": skel.get("name"),
                         "bytes": len(s_bytes)},
            "extra_displays": [{"node": d["node"], "armature": d.get("armature"),
                                "active": d.get("active")}
                               for d in displays if d is not primary],
            "root_scale": data.get("rootScale"),
            "root_size": data.get("rootSize"),
            "warnings": warns,
            "extracted_at": now_iso(),
            "extractor": "tools/bake_actors.py",
        }
        defs = cross_check(armatures, atlas_info)
        if defs:
            meta["warnings"].append(f"{len(defs)} display(s) missing from atlas, e.g. {defs[:3]}")
        dump_json(os.path.join(dest, "meta.json"), meta)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {"status": "ok", "key": key, "meta": meta}


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #


def verify_dirs(out_root, count=None, seed=None):
    if not os.path.isdir(out_root):
        raise SystemExit(f"output dir does not exist: {out_root}")
    dirs = []
    for root, _dirs, files in os.walk(out_root):
        if "skeleton.json" in files:
            dirs.append(root)
    dirs.sort()
    if not dirs:
        raise SystemExit("no baked actors found")
    if count is not None:
        rng = random.Random(seed)
        sample = rng.sample(dirs, min(count, len(dirs)))
    else:
        sample = dirs
    ok = bad = 0
    for d in sample:
        key = os.path.relpath(d, out_root).replace(os.sep, "/")
        problems = []
        try:
            with open(os.path.join(d, "skeleton.json"), encoding="utf-8") as fh:
                skel = json.load(fh)
            arms = [a.get("name") for a in skel.get("armature", [])]
            n_anim = sum(len(a.get("animation") or []) for a in skel.get("armature", []))
            if not arms:
                problems.append("no armatures")
        except Exception as exc:  # noqa: BLE001
            arms, n_anim = [], 0
            problems.append(f"skeleton parse: {exc}")
        atlas = None
        try:
            with open(os.path.join(d, "atlas.json"), encoding="utf-8") as fh:
                atlas = json.load(fh)
            if not atlas.get("SubTexture"):
                problems.append("atlas without SubTexture")
        except FileNotFoundError:
            problems.append("missing atlas.json")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"atlas parse: {exc}")
        tex_size = None
        try:
            p = os.path.join(d, "texture.png")
            if Image is None:
                problems.append("Pillow missing, cannot check texture")
            else:
                with Image.open(p) as im:
                    im.load()
                    tex_size = im.size
                if tex_size[0] <= 0 or tex_size[1] <= 0:
                    problems.append("zero-size texture")
                if os.path.getsize(p) < 200:
                    problems.append("suspiciously small texture file")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"texture: {exc}")
        if problems:
            bad += 1
            log(f"  FAIL {key}: {'; '.join(problems)}")
        else:
            ok += 1
            log(f"  ok   {key}: armatures={len(arms)} {arms[:3]} "
                f"anims={n_anim} tex={tex_size} subTex={atlas.get('SubTexture').__len__()}")
    log(f"\nverify: {ok} ok, {bad} bad (sample {len(sample)}/{len(dirs)})")
    return 0 if bad == 0 else 1


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(
        description="Extract DragonBones actor packs from the live PvZ2 Gardendless build.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--jobs", "--list", dest="jobs", default=None,
                    help=f"job list (json/txt). default: {DEFAULT_JOBS} if it exists")
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"output db dir (default {DEFAULT_OUT})")
    ap.add_argument("--manifest", default=None,
                    help=f"manifest path (default <out>/MANIFEST.json)")
    ap.add_argument("--only", nargs="+", default=None,
                    help="only these keys/prefabs (matches key or prefab)")
    ap.add_argument("--group", nargs="+", default=None, help="only these job groups")
    ap.add_argument("--force", action="store_true", help="re-extract even if present")
    ap.add_argument("--no-hardlink", action="store_true", help="copy files instead of hard-linking")
    ap.add_argument("--port", type=int, default=9333, help="Chrome CDP port (default 9333)")
    ap.add_argument("--release", default=None,
                    help="release root, e.g. https://host/releases/<hash>/ (auto-detected)")
    ap.add_argument("--timeout", type=float, default=300.0, help="per-actor timeout seconds")
    ap.add_argument("--texcache", default=None,
                    help="texture cache dir (default: %%TEMP%%/pvz2_db_texcache)")
    ap.add_argument("--no-texcache", action="store_true", help="disable the on-disk texture cache")
    ap.add_argument("--verify", type=int, default=None, metavar="N",
                    help="verify N random already-baked actors and exit")
    ap.add_argument("--verify-all", action="store_true", help="verify every baked actor and exit")
    ap.add_argument("--seed", type=int, default=None, help="seed for --verify sampling")
    ap.add_argument("--delay", type=float, default=0.0, help="sleep between actors (default 0)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)

    out_root = os.path.abspath(args.out)
    manifest_path = args.manifest or os.path.join(out_root, "MANIFEST.json")

    if args.verify_all or args.verify is not None:
        return verify_dirs(out_root, None if args.verify_all else (args.verify or 3), args.seed)

    jobs_path = args.jobs or (DEFAULT_JOBS if os.path.exists(DEFAULT_JOBS) else None)
    if not jobs_path:
        raise SystemExit("no job list: pass --jobs <file> (see --help)")
    jobs, job_extras = load_jobs(jobs_path)
    armature_aliases = job_extras.get("armature_aliases") or {}
    armor_prefabs = job_extras.get("armor_prefabs") or {}

    if args.group:
        want = {g.lower() for g in args.group}
        jobs = [j for j in jobs if (j.get("group") or "").lower() in want]
    if args.only:
        want = set()
        for token in args.only:
            want.add(token)
        jobs = [j for j in jobs if j["key"] in want or j["prefab"] in want or
                j["key"].split("/")[-1] in want]
        if not jobs:
            raise SystemExit(f"--only matched no job: {sorted(want)}")

    ensure_dir(out_root)
    # a killed run can leave a staging dir behind; they are never valid actors
    for name in os.listdir(out_root):
        if name.startswith("bake_"):
            shutil.rmtree(os.path.join(out_root, name), ignore_errors=True)

    cache_dir = None if args.no_texcache else (
        args.texcache or os.path.join(tempfile.gettempdir(), "pvz2_db_texcache"))

    page = Page(port=args.port, timeout=args.timeout, verbose=not args.quiet)
    try:
        page.connect()
        info = json.loads(page.eval(_CDP_PAGE_EXPR, timeout=60) or "{}")
    except CDPError as exc:
        raise SystemExit(str(exc))

    release = args.release or info.get("release")
    if not args.quiet:
        log(f"page    : {page.info.get('title')}  {page.info.get('url')}")
        log(f"release : {release or '(unknown - pass --release)'}")
        log(f"jobs    : {len(jobs)}  ->  {out_root}")
        if cache_dir:
            log(f"texcache: {cache_dir}")
        log("")

    tex_cache = TextureCache(cache_dir=cache_dir, release=release,
                             verbose=not args.quiet)

    results = []
    t0 = time.time()
    for i, job in enumerate(jobs, 1):
        tag = f"[{i:>2}/{len(jobs)}] {job['key']}"
        started = time.time()
        try:
            res = extract_one(page, tex_cache, job, out_root,
                              force=args.force, hardlink=not args.no_hardlink)
        except CDPError as exc:
            res = {"status": "failed", "key": job["key"], "prefab": job["prefab"],
                   "stage": "extract", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            res = {"status": "failed", "key": job["key"], "prefab": job["prefab"],
                   "stage": "unexpected", "error": f"{type(exc).__name__}: {exc}"}
        res["job"] = job
        res["seconds"] = round(time.time() - started, 1)
        results.append(res)
        if res["status"] == "ok":
            m = res["meta"]
            log(f"{tag}  OK   arm={m['armature']!r} anims={len(m['animations'])} "
                f"tex={m['texture_size']} {res['seconds']}s")
        elif res["status"] == "skipped":
            log(f"{tag}  skip (already baked, use --force)")
        else:
            log(f"{tag}  FAIL [{res.get('stage')}] {res.get('error')}")
        if args.delay:
            time.sleep(args.delay)

    page.close()

    # ---------------- manifest ----------------
    # Merge with any existing manifest so partial runs (--only / --group) never
    # shrink the db's actor list or drop aliases baked by earlier runs.
    actors = {}
    aliases = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                old = json.load(fh)
            if isinstance(old, list):
                old = {"actors": old}
            for row in old.get("actors") or []:
                if row.get("key"):
                    actors[row["key"]] = row
            aliases.update(old.get("aliases") or {})
        except Exception as exc:  # noqa: BLE001
            log(f"warning: could not merge existing manifest ({exc}); rewriting")
    failures = []
    for res in results:
        job = res["job"]
        if res["status"] in ("ok", "skipped"):
            m = res["meta"]
            actors[m["key"]] = {
                "key": m["key"],
                "prefab": m["prefab"],
                "armature": m["armature"],
                "animations": m["animations"],
                "size": m["size"],
                "texture_size": m["texture_size"],
                "dir": m["key"],
                "armatures": [a["name"] for a in m.get("armatures", [])],
                "group": m.get("group"),
                "requested": m.get("requested"),
            }
            if job.get("requested") and job["requested"] != m["key"]:
                aliases[job["requested"]] = {
                    "key": m["key"], "armature": m["armature"],
                    "note": job.get("note") or "requested name not present; mapped to this prefab",
                }
            elif job.get("note"):
                aliases.setdefault(m["key"], {"key": m["key"], "armature": m["armature"],
                                              "note": job["note"]})
        else:
            failures.append({"key": res["key"], "prefab": res["prefab"],
                             "stage": res.get("stage"), "error": res.get("error")})

    actors = sorted(actors.values(), key=lambda a: (a.get("group") or "", a["key"]))
    # armature-only aliases from the job file (armour/flag zombies share a skeleton)
    baked_keys = {a["key"] for a in actors}
    for name, spec in (armature_aliases or {}).items():
        entry = dict(spec) if isinstance(spec, dict) else {"key": spec}
        entry.setdefault("key", None)
        if entry.get("key") in baked_keys:
            aliases.setdefault(name, entry)
    armors = {}
    for prefab, spec in (armor_prefabs or {}).items():
        entry = dict(spec) if isinstance(spec, dict) else {"key": spec}
        if entry.get("key") in baked_keys:
            armors[prefab] = entry
    manifest = {
        "generated": now_iso(),
        "source": {
            "site": SITE,
            "release": release,
            "bundle": "resources",
            "engine": info.get("version"),
            "game": page.info.get("title"),
            "extractor": "tools/bake_actors.py",
        },
        "count": len(actors),
        "actors": actors,
        "aliases": aliases,
        "armor_prefabs": armors,
        "failures": failures,
    }
    dump_json(manifest_path, manifest)
    report_path = os.path.join(out_root, "_bake_report.json")
    dump_json(report_path, {
        "generated": manifest["generated"],
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed": len(failures),
        "elapsed_s": round(time.time() - t0, 1),
        "results": [{k: v for k, v in r.items() if k not in ("meta", "job")} for r in results],
    })

    ok = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    log("")
    log(f"done: {ok} extracted, {skipped} skipped, {len(failures)} failed "
        f"in {time.time() - t0:.0f}s")
    log(f"manifest : {manifest_path}")
    log(f"report   : {report_path}")
    if failures:
        log("\nfailures:")
        for f in failures:
            log(f"  {f['key']:<38} [{f['stage']}] {f['error'][:160]}")
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
