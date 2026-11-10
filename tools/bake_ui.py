#!/usr/bin/env python
"""Bake PvZ2SHUTTLE UI / world-map / lawn art from the live PvZ2 Gardendless build.

Every image is rendered *inside* the running page through a cc.RenderTexture camera
instead of a browser screenshot: that keeps advertising overlays out of the picture
and preserves real alpha for sprites.

Requirements: headless Chrome with the game open on a CDP port (default 9333), the
`websocket-client` and `Pillow` Python packages.

  python tools/bake_ui.py                  # everything
  python tools/bake_ui.py --only ui        # just assets/ui
  python tools/bake_ui.py --only lawn --worlds egypt,pirate
  python tools/bake_ui.py --only world --port 9333

Outputs (relative to the game root):
  assets/world/<world>.png   1280x720  world-map background
  assets/lawn/<world>.png    1280x720  day lawn board
  assets/ui/{sun,seedpacket,panel}.png

How each group is sourced
  world : prefab worldmaps/<Name>WORLDMAP instantiated over the worldMapScene nebula
          backdrop (the scene's own `background` node), scene chrome hidden.
  lawn  : prefab lawns/<Name>LAWN instantiated with its one game-logic component
          stripped (it throws in onEnable without a running level), then rendered.
  ui    : SunBigDP prefab (sun), PlantCardTemplate prefab (seed packet card) and the
          windowCommon 9-slice sprite (panel) rendered with a transparent clear.

Re-running is safe: outputs are overwritten and the size/statistics of every image are
printed. Add --keep-raw to also keep the untrimmed renders under work/ui_bake/.
"""
import argparse
import base64
import json
import os
import sys
import tempfile
import time
import urllib.request

try:
    import websocket        # websocket-client
except ImportError:         # pragma: no cover
    sys.exit("pip install websocket-client")
try:
    from PIL import Image
except ImportError:         # pragma: no cover
    sys.exit("pip install Pillow")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                     # PvZ2SHUTTLE
RAW_DIR = os.path.join(tempfile.gettempdir(), "pvz_bake_ui")

WORLDS = [                                       # (world id, prefab name)
    ("frontyard", "Modern"), ("egypt", "Egypt"), ("pirate", "Pirate"),
    ("cowboy", "Cowboy"), ("future", "Future"), ("dark", "Dark"),
    ("beach", "Beach"), ("lostcity", "LostCity"),
    ("iceage", "Iceage"), ("kongfu", "Kongfu"), ("dino", "Dino"),
    ("eighties", "Eighties"), ("modern", "Modern"), ("sky", "Sky"),
]
LAWNS = [
    ("frontyard", "Modern"), ("egypt", "Egypt"), ("pirate", "Pirate"),
    ("cowboy", "Cowboy"), ("future", "Future"), ("dark", "Dark"),
    ("beach", "Beach"), ("lostcity", "LostCity"),
    ("iceage", "Iceage"), ("kongfu", "Kongfu"), ("dino", "Dino"),
    ("eighties", "Eighties"), ("modern", "Modern"), ("sky", "Sky"),
]
UI = [
    # (file, mode, ident, size, scale, stretch)
    ("sun.png", "prefab", "78c0db98-54b5-45f6-a53a-c8c6d0a8d329", (512, 512), 4.0, None),
    ("seedpacket.png", "prefab", "f5b49039-25f1-495b-ab19-afac972d1467", (512, 512), 1.0, None),
    ("panel.png", "sprite", "675b41ad-c77a-4770-8608-a9aa1e463010@f9941", (640, 420), 1.0, (640, 420)),
]
CHROME = ['WMChooserSlot', 'Buttons', 'TutorialEpicLevels', 'TutorialPremium', 'NPC_Controller',
          'SettingWindow', 'GitHubLevelWindow', 'ArcadeWindow', 'QuestionEpic', 'LODEntrance',
          'MouseListener', 'WheelListener', 'background_cover', 'FPSLabel', 'LoaderFlower',
          'GamingTips']

# ---------------------------------------------------------------- CDP plumbing
class CDP:
    def __init__(self, port=9333, timeout=180):
        with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=10) as r:
            targets = json.load(r)
        page = next((t for t in targets if t.get("type") == "page" and "pvzge" in t.get("url", "")), None) \
            or next(t for t in targets if t.get("type") == "page")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=timeout,
                                              max_size=400 * 1024 * 1024)
        self._id = 0
        self.call("Runtime.enable")

    def call(self, method, params=None, timeout=120):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(1, deadline - time.time()))
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                return m
        raise TimeoutError(method)

    def evaluate(self, expr):
        m = self.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True,
                                           "returnByValue": True, "userGesture": True})
        r = m.get("result", {})
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:2000])
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass

# --------------------------------------------------------------- RT primitives
# Shared render-texture camera: orthographic, transparent clear, on top of everything,
# all other Canvas children disabled so only our node is visible.
RT_CAM = r"""
  const rt = new cc.RenderTexture(); rt.reset({width: P.w, height: P.h});
  const camNode = new cc.Node('__bakeCam'); scene.addChild(camNode);
  const cam = camNode.addComponent(cc.Camera);
  cam.projection = cc.Camera.ProjectionType.ORTHO;
  cam.orthoHeight = P.h / 2;
  cam.clearFlags = cc.Camera.ClearFlag.SOLID_COLOR;
  cam.clearColor = new cc.Color(P.bg[0], P.bg[1], P.bg[2], P.bg[3]);
  cam.priority = 100000; cam.targetTexture = rt; cam.visibility = 0xffffffff;
  camNode.setPosition(P.cx, P.cy, 1000);
  state.hidden = [];
  const gameCam = canvas.children.find(c => c.getComponent(cc.Camera));
  canvas.children.forEach(c => { if (c !== cont && c !== gameCam && c.active) { c.active = false; state.hidden.push(c); } });
"""

READ_PNG = r"""
(async()=>{
  const s = window.__bake; if(!s) throw new Error('no bake state');
  await new Promise(r=>setTimeout(r, 350));
  const buf = s.rt.readPixels();
  const W = s.w, H = s.h;
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d'); const img = ctx.createImageData(W, H); const row = W*4;
  for(let y=0; y<H; y++) img.data.set(buf.subarray((H-1-y)*row, (H-y)*row), y*row);
  ctx.putImageData(img,0,0);
  return cv.toDataURL('image/png');
})()
"""

TEARDOWN = r"""
(()=>{ const s = window.__bake; if(!s) return 'noop';
  try{ if(s.cam) s.cam.targetTexture = null; }catch(e){}
  try{ if(s.camNode && s.camNode.isValid) s.camNode.destroy(); }catch(e){}
  try{ if(s.cont && s.cont.isValid) s.cont.destroy(); }catch(e){}
  (s.hidden||[]).forEach(n=>{ if(n && n.isValid) n.active = true; });
  try{ if(s.rt) s.rt.destroy(); }catch(e){}
  (s.restore||[]).forEach(n=>{ if(n && n.isValid) n.active = true; });
  window.__bake = null; return 'ok'; })()
"""


def _run(cdp, setup_js, out, w, h):
    cdp.evaluate(setup_js)
    url = cdp.evaluate(READ_PNG)
    cdp.evaluate(TEARDOWN)
    data = base64.b64decode(url.split(",", 1)[1])
    with open(out, "wb") as f:
        f.write(data)
    return len(data)


def bake_world(cdp, world, prefab, out):
    """Prefab over the worldMapScene nebula background."""
    setup = r"""
(async()=>{
  const P = %s;
  const scene = cc.director.getScene();
  const canvas = cc.director.getScene().getChildByName('Canvas');
  const b = cc.assetManager.getBundle('resources');
  const pf = await new Promise((res,rej)=>b.load(P.prefab, cc.Prefab, (e,x)=>e?rej(e):res(x)));
  const root = cc.instantiate(pf);
  ['Level_Islands','moveButtons'].forEach(n => { const c = root.getChildByName(n); if(c) c.active = false; });
  const cont = new cc.Node('__bakeRoot');
  canvas.addChild(cont);
  cont.setPosition(0, 0, 0); cont.setScale(P.scale, P.scale, 1); cont.addChild(root);
  const state = {cont:cont, restore:[]};
  %s
  window.__bake = state; state.rt = rt; state.cam = cam; state.camNode = camNode;
  state.w = P.w; state.h = P.h;
  return JSON.stringify({ok:true, scene: cc.director.getScene().name});
})()
""" % (json.dumps({"prefab": "worldmaps/%sWORLDMAP" % prefab, "w": 1280, "h": 720, "scale": 1.12,
                   "cx": 512, "cy": 320, "bg": [0, 0, 0, 255]}), RT_CAM)

    # the world map lives in worldMapScene; switch there before rendering
    cdp.evaluate("""(async()=>{ const s = cc.director.getScene();
      if (s.name !== 'worldMapScene') {
        await new Promise(res => cc.director.loadScene('worldMapScene', res));
        await new Promise(r => setTimeout(r, 1500));
      }
      return cc.director.getScene().name; })()""")
    # hide world-map scene chrome once per session
    cdp.evaluate("""(()=>{ const c = cc.director.getScene().getChildByName('Canvas');
      if(!c) return 'no canvas';
      (window.__bakeChrome||[]).forEach(n=>{ if(n && n.isValid) n.active = true; });
      const hidden = [];
      %s.forEach(name => { const n = c.getChildByName(name); if(n && n.active){ n.active = false; hidden.push(n); } });
      window.__bakeChrome = hidden; return hidden.length; })()""" % json.dumps(CHROME))
    return _run(cdp, setup, out, 1280, 720)


def bake_lawn(cdp, world, prefab, out):
    setup = r"""
(async()=>{
  const P = %s;
  const scene = cc.director.getScene();
  const canvas = scene.getChildByName('Canvas');
  const b = cc.assetManager.getBundle('resources');
  const pf = await new Promise((res,rej)=>b.load(P.prefab, cc.Prefab, (e,x)=>e?rej(e):res(x)));
  const root = cc.instantiate(pf);
  // strip game-logic components: the lawn controller throws in onEnable without a level
  const allowed = /^(cc\.(UITransform|Sprite|Label|Layout|Widget|Mask|Graphics|UIOpacity|Renderable2D)|dragonBones\.ArmatureDisplay)$/;
  const strip = n => { (n._components||[]).slice().forEach(c => {
      if(!allowed.test(cc.js.getClassName(c))) { try{ c.destroy(); }catch(e){} } });
    (n._children||[]).forEach(strip); };
  strip(root);
  const cont = new cc.Node('__bakeRoot'); canvas.addChild(cont);
  cont.setPosition(0, 0, 0); cont.setScale(P.scale, P.scale, 1); cont.addChild(root);
  const state = {cont:cont, restore:[]};
  %s
  window.__bake = state; state.rt = rt; state.cam = cam; state.camNode = camNode;
  state.w = P.w; state.h = P.h;
  return JSON.stringify({ok:true});
})()
""" % (json.dumps({"prefab": prefab, "w": 1600, "h": 1000, "scale": 1.0,
                   "cx": 512, "cy": 320, "bg": [0, 0, 0, 255]}), RT_CAM)
    return _run(cdp, setup, out, 1600, 1000)


def bake_ui(cdp, mode, ident, out, size, scale, stretch):
    setup = r"""
(async()=>{
  const P = %s;
  const scene = cc.director.getScene();
  const canvas = scene.getChildByName('Canvas');
  const load = uuid => new Promise((res,rej)=>cc.assetManager.loadAny({uuid}, (e,x)=>e?rej(e):res(x)));
  const b = cc.assetManager.getBundle('resources');
  let root;
  if (P.mode === 'sprite') {
    const sf = await load(P.ident);
    const n = new cc.Node('__bakeSprite'); const sp = n.addComponent(cc.Sprite);
    sp.spriteFrame = sf; sp.sizeMode = cc.Sprite.SizeMode.CUSTOM;
    if (P.stretch) { sp.type = cc.Sprite.Type.SLICED; n.setContentSize(P.stretch[0], P.stretch[1]); }
    else { sp.type = cc.Sprite.Type.SIMPLE; n.setContentSize(sf.originalSize.width, sf.originalSize.height); }
    root = n;
  } else {
    const pf = P.ident.indexOf('/') >= 0
      ? await new Promise((res,rej)=>b.load(P.ident, cc.Prefab, (e,x)=>e?rej(e):res(x)))
      : await load(P.ident);
    root = cc.instantiate(pf);
  }
  const cont = new cc.Node('__bakeRoot'); canvas.addChild(cont);
  cont.setPosition(0, 0, 0); cont.setScale(P.scale, P.scale, 1); cont.addChild(root);
  root.setPosition(0, 0, 0);
  const state = {cont:cont, restore:[]};
  %s
  window.__bake = state; state.rt = rt; state.cam = cam; state.camNode = camNode;
  state.w = P.w; state.h = P.h;
  return JSON.stringify({ok:true});
})()
""" % (json.dumps({"mode": mode, "ident": ident, "w": size[0], "h": size[1], "scale": scale,
                   "stretch": list(stretch) if stretch else None,
                   "cx": 512, "cy": 320, "bg": [0, 0, 0, 0]}), RT_CAM)
    return _run(cdp, setup, out, size[0], size[1])

# ------------------------------------------------------------- post-processing
def trim_alpha(path, pad=2):
    im = Image.open(path).convert("RGBA")
    bbox = im.getbbox()
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    im = im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))
    im.save(path)
    return im.size


def finish_world(raw, out):
    """World shots carry ~14 px of the scene mesh border on each side: crop and refit."""
    im = Image.open(raw).convert("RGB")
    im = im.crop((14, 0, im.width - 14, im.height)).resize((1280, 720), Image.LANCZOS)
    im.save(out, optimize=True)
    return im.size


def finish_lawn(raw, out, w=1280, h=720):
    im = Image.open(raw).convert("RGB")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    s = min(w / im.width, h / im.height)
    im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), (0, 0, 0))
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    canvas.save(out, optimize=True)
    return canvas.size


def stats(path):
    im = Image.open(path).convert("L")
    px = list(im.getdata())
    m = sum(px) / len(px)
    return round(m, 1), round((sum((p - m) ** 2 for p in px) / len(px)) ** 0.5, 1)


# ---------------------------------------------------------------------- driver
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=["world", "lawn", "ui", "all"], default="all")
    ap.add_argument("--worlds", default="", help="comma separated subset of world ids")
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--keep-raw", action="store_true")
    a = ap.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    want = set(w.strip() for w in a.worlds.split(",") if w.strip())
    cdp = CDP(a.port)
    failures = []
    try:
        if a.only in ("world", "all"):
            os.makedirs(os.path.join(ROOT, "assets", "world"), exist_ok=True)
            for wid, name in WORLDS:
                if want and wid not in want:
                    continue
                raw = os.path.join(RAW_DIR, "world_%s.png" % wid)
                try:
                    bake_world(cdp, wid, name, raw)
                    dst = os.path.join(ROOT, "assets", "world", wid + ".png")
                    finish_world(raw, dst)
                    print("world %-9s %s mean/std=%s" % (wid, finish_world(raw, dst), stats(dst)))
                except Exception as e:
                    failures.append(("world", wid, str(e)[:200]))
                    print("world %-9s FAILED %s" % (wid, str(e)[:160]))

        if a.only in ("lawn", "all"):
            os.makedirs(os.path.join(ROOT, "assets", "lawn"), exist_ok=True)
            for wid, name in LAWNS:
                if want and wid not in want:
                    continue
                raw = os.path.join(RAW_DIR, "lawn_%s.png" % wid)
                try:
                    bake_lawn(cdp, wid, "lawns/%sLAWN" % name, raw)
                    dst = os.path.join(ROOT, "assets", "lawn", wid + ".png")
                    finish_lawn(raw, dst)
                    print("lawn  %-9s %sx%s mean/std=%s" % (wid, *Image.open(dst).size, stats(dst)))
                except Exception as e:
                    failures.append(("lawn", wid, str(e)[:200]))
                    print("lawn  %-9s FAILED %s" % (wid, str(e)[:160]))

        if a.only in ("ui", "all"):
            os.makedirs(os.path.join(ROOT, "assets", "ui"), exist_ok=True)
            for fname, mode, ident, size, scale, stretch in UI:
                raw = os.path.join(RAW_DIR, fname)
                try:
                    bake_ui(cdp, mode, ident, raw, size, scale, stretch)
                    if mode in ("sprite", "prefab"):
                        trim_alpha(raw)
                    dst = os.path.join(ROOT, "assets", "ui", fname)
                    Image.open(raw).save(dst, optimize=True)
                    print("ui    %-14s %sx%s mean/std=%s" % (fname, *Image.open(dst).size, stats(dst)))
                except Exception as e:
                    failures.append(("ui", fname, str(e)[:200]))
                    print("ui    %-14s FAILED %s" % (fname, str(e)[:160]))
    finally:
        cdp.close()

    if not a.keep_raw:
        for f in os.listdir(RAW_DIR):
            if f.endswith(".png"):
                try:
                    os.remove(os.path.join(RAW_DIR, f))
                except OSError:
                    pass
    if failures:
        print("\n%d failure(s): %s" % (len(failures), failures))
        return 1
    print("\nDone. If the page is not on the game yet, open https://play.pvzge.com/ first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

