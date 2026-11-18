import json
T = {
 "light": dict(bg="#f3f4f6", surface="#ffffff", surface2="#e9ebef", text="#14161b", muted="#555b69",
   border="#d6d9e0", control="#767d90", primary="#3242c0", onprimary="#ffffff", primaryhover="#26339c",
   selbg="#e5e8fb", seltext="#26339c", live="#c4221a", livebg="#fdecea", draft="#11733b", draftbg="#e4f4ea",
   warn="#875000", warnbg="#fff3dc", err="#b3261e", errbg="#fdeceb", disabled="#646a7b", disabledbg="#eceef2"),
 "dark": dict(bg="#0e1014", surface="#161920", surface2="#1d2129", text="#e8ebf1", muted="#a2a9b8",
   border="#2b303a", control="#737b8f", primary="#93a3ff", onprimary="#0e1014", primaryhover="#b3beff",
   selbg="#262d4d", seltext="#c7cfff", live="#ff6b5f", livebg="#3a1a17", draft="#52d18d", draftbg="#11301f",
   warn="#f0b44a", warnbg="#33270e", err="#ff7b6e", errbg="#3a1b19", disabled="#8f96a6", disabledbg="#1d2129"),
 "stage": dict(stage="#08090c", body="#1b1e25", line="#6d7588", text="#eef0f4", sel="#93a3ff", warn="#f0b44a", draft="#52d18d", live="#ff6b5f", hatch="#2a2e37", pill="#08090c", screen="#0d0f13", pagedark="#000000"),
}
def lum(h):
    h=h.lstrip('#'); c=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    c=[x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4 for x in c]
    return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]
def cr(a,b):
    la,lb=lum(a),lum(b); return (max(la,lb)+0.05)/(min(la,lb)+0.05)
rows=[]
for th in ("light","dark"):
    t=T[th]
    pairs=[("text","surface",4.5),("text","bg",4.5),("text","surface2",4.5),("muted","surface",4.5),("muted","surface2",4.5),("muted","bg",4.5),
      ("onprimary","primary",4.5),("onprimary","primaryhover",4.5),("primary","surface",4.5),("seltext","selbg",4.5),
      ("live","livebg",4.5),("live","surface",4.5),("draft","draftbg",4.5),("draft","surface",4.5),("warn","warnbg",4.5),("warn","surface",4.5),
      ("err","errbg",4.5),("err","surface",4.5),("control","surface",3),("control","surface2",3),("primary","bg",3),("disabled","disabledbg",4.5)]
    for f,b,m in pairs: rows.append((th,f,b,round(cr(t[f],t[b]),2),m))
s=T["stage"]
for f,b,m in [("text","stage",4.5),("text","body",4.5),("line","stage",3),("sel","stage",3),("sel","body",3),("warn","stage",4.5),("warn","body",4.5),("draft","stage",3),("live","stage",3),("text","hatch",4.5),("text","pill",4.5),("warn","pill",4.5),("sel","screen",4.5),("line","body",3),("sel","pagedark",3)]:
    rows.append(("stage",f,b,round(cr(s[f],s[b]),2),m))
bad=0
for r in rows:
    ok = r[4] is None or r[3]>=r[4]; bad+= not ok
    print(f"| {r[0]} | {r[1]} on {r[2]} | {r[3]}:1 | {'≥'+str(r[4]) if r[4] else 'exempt'} | {'pass' if ok else 'FAIL'} |")
print("FAILS",bad)

