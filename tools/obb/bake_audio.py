"""Bake assets/audio/* from the live bundle.

Two routes:
  * native mp3 clips -> plain HTTP download (Referer required)
  * .m4a (AAC) clips -> cannot be decoded locally (no ffmpeg), so the page decodes
    them with WebAudio and we save 16-bit PCM WAV, which pygame plays natively.

Usage: python bake_audio.py [port]
"""
import base64
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_util import CDP                       # noqa: E402

BASE = "https://play.pvzge.com/releases/6ad543d5c0e0f3d0cef71f262bc146062b4f0d6e/"
OUT = r"D:\OneDrive\文档\pvz_shuttle\PvZ2SHUTTLE\assets\audio"

MP3 = [
    # (saved name, uuid)  -- extension is always .mp3 for these
    ("shoot_hit", "af3972c8-cc52-4efa-9f96-787070cac2f2"),
    ("ui_open", "b6819e5e-95c7-4491-bf32-aaae4f7a656c"),
    ("ui_close", "85ca3eea-5256-48e9-84b9-f9cdd8b8e6fa"),
    ("coin_drop", "7c75f1e4-222a-4a15-9f5d-036643b3eef1"),
    ("gem_spawn", "90690e93-e2fe-44c4-894e-0a639125deea"),
]
M4A = [
    # (saved name, uuid, extension)
    ("sun_collect", "762bedf6-5eee-42ef-920e-4d51417f73d2", ".m4a"),
    ("plant", "02f62f30-262f-4b0d-97fc-3ed02619b4e6", ".m4a"),
    ("zombie_groan", "45e96f25-6f3a-4942-a9b1-e82bf5ce0576", ".m4a"),
    ("plant_sprout", "f1bc9891-5a9c-48c7-9acb-9b79458dd004", ".m4a"),
    ("zombie_groan2", "0d9f9109-13a1-4064-885a-a7c8eadece77", ".m4a"),
]

DECODE_JS = r"""
(async()=>{
  const BASE=%s, items=%s;
  const out = {};
  for(const it of items){
    try{
      const res = await fetch(BASE+'assets/resources/native/'+it.uuid.slice(0,2)+'/'+it.uuid+it.ext);
      if(!res.ok){ out[it.name] = {err:'http '+res.status}; continue; }
      const ab = await res.arrayBuffer();
      const ac = new (window.AudioContext||window.webkitAudioContext)();
      const buf = await ac.decodeAudioData(ab.slice(0));
      const chs = buf.numberOfChannels, len = buf.length, sr = buf.sampleRate;
      const data = [];
      for(let c=0;c<chs;c++) data.push(buf.getChannelData(c));
      const bytes = new Uint8Array(44 + len*chs*2);
      const dv = new DataView(bytes.buffer);
      const wstr = (o,s)=>{ for(let i=0;i<s.length;i++) dv.setUint8(o+i, s.charCodeAt(i)); };
      wstr(0,'RIFF'); dv.setUint32(4, 36+len*chs*2, true); wstr(8,'WAVE');
      wstr(12,'fmt '); dv.setUint32(16,16,true); dv.setUint16(20,1,true); dv.setUint16(22,chs,true);
      dv.setUint32(24,sr,true); dv.setUint32(28,sr*chs*2,true); dv.setUint16(32,chs*2,true); dv.setUint16(34,16,true);
      wstr(36,'data'); dv.setUint32(40,len*chs*2,true);
      let off=44;
      for(let i=0;i<len;i++){ for(let c=0;c<chs;c++){ let s=Math.max(-1,Math.min(1,data[c][i])); dv.setInt16(off, s<0? s*0x8000 : s*0x7fff, true); off+=2; } }
      let bin=''; const CH=0x8000;
      for(let i=0;i<bytes.length;i+=CH) bin += String.fromCharCode.apply(null, bytes.subarray(i,i+CH));
      out[it.name] = {b64: btoa(bin), dur: buf.duration, sr: sr, ch: chs};
      try{ ac.close(); }catch(e){}
    }catch(e){ out[it.name] = {err:String(e)}; }
  }
  return JSON.stringify(out);
})()
"""


def download(uuid, ext, dst):
    url = BASE + "assets/resources/native/%s/%s%s" % (uuid[:2], uuid, ext)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://play.pvzge.com/",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with open(dst, "wb") as f:
        f.write(data)
    return len(data)


def main(port=9333):
    os.makedirs(OUT, exist_ok=True)
    report = []
    for name, uuid in MP3:
        dst = os.path.join(OUT, name + ".mp3")
        try:
            n = download(uuid, ".mp3", dst)
            report.append({"name": name, "file": name + ".mp3", "uuid": uuid, "bytes": n, "fmt": "mp3"})
            print("mp3  %-14s %8d bytes" % (name, n))
        except Exception as e:
            report.append({"name": name, "uuid": uuid, "error": str(e)[:200]})
            print("mp3  %-14s FAILED %s" % (name, e))

    items = [{"name": n, "uuid": u, "ext": e} for n, u, e in M4A]
    cdp = CDP(port)
    try:
        res = json.loads(cdp.eval(DECODE_JS % (json.dumps(BASE), json.dumps(items))) or "{}")
    finally:
        cdp.close()
    for name, uuid, ext in M4A:
        r = res.get(name) or {}
        if "b64" not in r:
            report.append({"name": name, "uuid": uuid, "error": r.get("err", "no data")})
            print("m4a->wav %-14s FAILED %s" % (name, r.get("err")))
            continue
        dst = os.path.join(OUT, name + ".wav")
        data = base64.b64decode(r["b64"])
        with open(dst, "wb") as f:
            f.write(data)
        report.append({"name": name, "file": name + ".wav", "uuid": uuid, "src": ext,
                       "bytes": len(data), "duration": round(r["dur"], 3),
                       "sample_rate": r["sr"], "channels": r["ch"]})
        print("wav  %-14s %8d bytes  %.2fs" % (name, len(data), r["dur"]))

    with open(os.path.join(OUT, "audio_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    return report


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 9333)
