import requests
from bs4 import BeautifulSoup
from datetime import datetime, UTC
import json

URL = "https://arxiv.org/list/cond-mat/new"

def fetch_condmat_new():
    r = requests.get(URL)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    papers = []
    sections = []
    # find all section headers
    for h3 in soup.find_all("h3"):
        sec = h3.get_text(strip=True)
        if not any(k in sec for k in ["New submissions", "Cross", "Replacements"]):
            continue
        sections.append((sec, h3))

    for sec_name, h3 in sections:
        # everything until the next <h3> belongs to this section
        nxt = h3.find_next("h3")
        elements = []
        node = h3.next_sibling
        while node and node != nxt:
            if getattr(node, "name", None) in ["dt", "dd"]:
                elements.append(node)
            node = node.next_sibling

        dts = [el for el in elements if el.name == "dt"]
        dds = [el for el in elements if el.name == "dd"]
        for dt, dd in zip(dts, dds):
            a_abs = dt.find("a", title="Abstract")
            if not a_abs:
                continue
            link = f"https://arxiv.org{a_abs['href']}"
            arx_id = a_abs.text.strip()
            title = dd.find("div", class_="list-title")
            title = title.get_text(" ", strip=True).replace("Title:", "").strip() if title else ""
            authors = dd.find("div", class_="list-authors")
            authors = authors.get_text(" ", strip=True).replace("Authors:", "").strip() if authors else ""
            subj = dd.find("div", class_="list-subjects")
            subj = subj.get_text(" ", strip=True).replace("Subjects:", "").strip() if subj else ""
            abs_p = dd.find("p", class_="mathjax")
            abstract = abs_p.get_text(" ", strip=True).replace("Abstract:","").strip() if abs_p else ""
            papers.append({
                "id": arx_id,
                "title": title,
                "authors": authors,
                "link": link,
                "subjects": subj,
                "abstract": abstract,
                "section": sec_name,
            })

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out_name = f"condmat_new_{today}.json"
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(papers)} papers to {out_name}")
    return papers

if __name__ == "__main__":
    fetch_condmat_new()
