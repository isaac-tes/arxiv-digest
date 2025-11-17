import json, re

# adjust filename if needed
FNAME = "condmat_new_2025-10-30.json"

core_keywords = [
    "mps","dmrg","matrix product","tensor","tensor network","purification","tebd",
    "lindblad","dissipative","open quantum","reservoir","reservoir engineering",
    "quantum gas","1d","one-dimensional","ladder","chain","boson","bosonic","mott",
    "doublon","holon","hubbard","supersolid","chiral","topolog","topological",
    "spin chain","kitaev","ising","heisenberg","frustrat","anyon","entanglement",
    "mpo","scar"
]
named_authors = ["barbiero","lewenstein","giamarchi","pollmann","goldman","pelster","chepiga"]
low_priority_kw = ["film","heterostructure","photoemission","device","junction","transport",
                   "measurement","spectroscopy","microscopy","epitaxial","mbe","growth",
                   "fabrication","magnetization","stm","arpes","rixs"]

def score(p):
    txt = " ".join([p.get("title",""), p.get("abstract",""), p.get("authors",""), p.get("subjects","")]).lower()
    s = 0
    for kw in core_keywords:
        if kw in txt: s += 6
    for name in named_authors:
        if name in txt: s += 8
    subj = p.get("subjects","").lower()
    if "cond-mat.quant-gas" in subj: s += 6
    if "quant-ph" in subj: s += 3
    if any(lp in txt for lp in low_priority_kw): s -= 5
    if len(p.get("abstract","")) > 200: s += 1
    return s

def summarize(abs_txt):
    a = re.sub(r'\s+',' ', abs_txt.strip())
    if not a: return "(No abstract available.)"
    parts = re.split(r'(?<=[.!?])\s+', a)
    return " ".join(parts[:2])

with open(FNAME, "r", encoding="utf-8") as f:
    papers = json.load(f)

for p in papers:
    for k in ("title","authors","abstract","link","subjects","id"):
        p.setdefault(k,"")
    p["score"] = score(p)

papers_sorted = sorted(papers, key=lambda x: (-x["score"], x.get("title","")))
top15 = papers_sorted[:15]

print("Daily arXiv cond-mat digest — (real papers)")
print(f"Total papers in feed: {len(papers)}. Showing top 15 by relevance.\n")
for i,p in enumerate(top15,1):
    title = p.get("title","").strip()
    authors = p.get("authors","").strip()
    link = p.get("link","").strip()
    summary = summarize(p.get("abstract",""))
    print(f"{i}. {title}")
    print(f"   {authors}")
    print(f"   {link}")
    print(f"   {summary}\n")
