#!/usr/bin/env python3
"""Generates 20 new country scrapers from a proven template."""
from pathlib import Path

COUNTRIES = [
    # (slug, class, region_dir, code, native_kws, domains, broad_domains)
    ("china", "China", "asia", "CN",
     ["讲座", "课件", "演示文稿", "教学材料", "研讨会", "人工智能", "机器学习", "计算机科学", "工程", "物理", "化学", "生物", "数学", "医学", "经济学", "法学"],
     ["site:tsinghua.edu.cn","site:pku.edu.cn","site:fudan.edu.cn","site:sjtu.edu.cn","site:zju.edu.cn","site:ustc.edu.cn","site:hit.edu.cn","site:nju.edu.cn","site:whu.edu.cn","site:buaa.edu.cn"],
     ["site:edu.cn","site:tsinghua.edu.cn","site:pku.edu.cn","site:cn"]),
    ("iran", "Iran", "asia", "IR",
     ["اسلاید", "ارائه", "جزوه", "سمینار", "هوش مصنوعی", "مهندسی", "فیزیک", "شیمی", "ریاضی", "پزشکی", "اقتصاد", "حقوق"],
     ["site:ut.ac.ir","site:sharif.edu","site:aut.ac.ir","site:iust.ac.ir","site:modares.ac.ir","site:sbu.ac.ir","site:kntu.ac.ir","site:guilan.ac.ir","site:shirazu.ac.ir","site:um.ac.ir"],
     ["site:ac.ir","site:ut.ac.ir","site:sharif.edu","site:ir"]),
    ("russia", "Russia", "europe", "RU",
     ["лекция", "презентация", "учебные материалы", "семинар", "информатика", "инженерия", "физика", "химия", "биология", "математика", "медицина", "экономика", "право"],
     ["site:msu.ru","site:spbu.ru","site:mipt.ru","site:hse.ru","site:nsu.ru","site:urfu.ru","site:tpu.ru","site:itmo.ru","site:bmstu.ru","site:mephi.ru"],
     ["site:ru","site:msu.ru","site:spbu.ru","site:mipt.ru"]),
    ("morocco", "Morocco", "africa", "MA",
     ["cours magistral", "diaporama", "présentation", "matériel pédagogique", "محاضرة", "شرائح", "informatique", "ingénierie", "physique", "chimie", "mathématiques", "médecine", "économie"],
     ["site:um5.ac.ma","site:uca.ac.ma","site:um6p.ma","site:uir.ac.ma","site:uae.ac.ma","site:umi.ac.ma","site:univ-oujda.ac.ma","site:uit.ac.ma","site:usms.ac.ma","site:usmba.ac.ma"],
     ["site:ac.ma","site:ma","site:um5.ac.ma","site:uca.ac.ma"]),
    ("venezuela", "Venezuela", "south_america", "VE",
     ["diapositivas", "presentación", "material de clase", "clase magistral", "seminario", "ingeniería", "física", "química", "biología", "matemáticas", "medicina", "economía", "derecho"],
     ["site:ucv.ve","site:usb.ve","site:uc.edu.ve","site:luz.edu.ve","site:ula.ve","site:unexpo.edu.ve","site:unimet.edu.ve","site:ucab.edu.ve","site:unet.edu.ve","site:uneg.edu.ve"],
     ["site:edu.ve","site:ve","site:ucv.ve","site:usb.ve"]),
    ("bulgaria", "Bulgaria", "europe", "BG",
     ["лекция", "презентация", "учебни материали", "семинар", "информатика", "инженерство", "физика", "химия", "биология", "математика", "медицина", "икономика", "право"],
     ["site:uni-sofia.bg","site:tu-sofia.bg","site:uni-plovdiv.bg","site:uni-vt.bg","site:nbu.bg","site:aubg.edu","site:mu-sofia.bg","site:tu-varna.bg","site:btu.bg","site:unwe.bg"],
     ["site:bg","site:uni-sofia.bg","site:tu-sofia.bg","site:uni-plovdiv.bg"]),
    ("slovakia", "Slovakia", "europe", "SK",
     ["prednáška", "prezentácia", "študijné materiály", "seminár", "informatika", "inžinierstvo", "fyzika", "chémia", "biológia", "matematika", "medicína", "ekonómia", "právo"],
     ["site:stuba.sk","site:uniba.sk","site:tuke.sk","site:uniza.sk","site:ukf.sk","site:uniag.sk","site:upjs.sk","site:umb.sk","site:ucm.sk","site:tvu.sk"],
     ["site:sk","site:stuba.sk","site:uniba.sk","site:tuke.sk"]),
    ("lithuania", "Lithuania", "europe", "LT",
     ["paskaita", "prezentacija", "mokomoji medžiaga", "seminaras", "informatika", "inžinerija", "fizika", "chemija", "biologija", "matematika", "medicina", "ekonomika", "teisė"],
     ["site:vu.lt","site:ktu.lt","site:vgtu.lt","site:lsmu.lt","site:vdu.lt","site:ku.lt","site:mruni.eu","site:lsu.lt","site:ism.lt","site:ef.vu.lt"],
     ["site:lt","site:vu.lt","site:ktu.lt","site:vgtu.lt"]),
    ("slovenia", "Slovenia", "europe", "SI",
     ["predavanje", "predstavitev", "študijsko gradivo", "seminar", "informatika", "inženirstvo", "fizika", "kemija", "biologija", "matematika", "medicina", "ekonomija", "pravo"],
     ["site:uni-lj.si","site:um.si","site:upr.si","site:feri.um.si","site:fe.uni-lj.si","site:fmf.uni-lj.si","site:ef.uni-lj.si","site:fri.uni-lj.si","site:fs.uni-lj.si","site:pf.uni-lj.si"],
     ["site:si","site:uni-lj.si","site:um.si","site:upr.si"]),
    ("estonia", "Estonia", "europe", "EE",
     ["loeng", "esitlus", "õppematerjalid", "seminar", "informaatika", "inseneeria", "füüsika", "keemia", "bioloogia", "matemaatika", "meditsiin", "majandus", "õigus"],
     ["site:ut.ee","site:taltech.ee","site:tlu.ee","site:emu.ee","site:ebs.ee","site:artun.ee","site:cs.ut.ee","site:kul.ee"],
     ["site:ee","site:ut.ee","site:taltech.ee","site:tlu.ee"]),
    ("jordan", "Jordan", "asia", "JO",
     ["محاضرة", "شرائح", "عرض تقديمي", "مادة دراسية", "ندوة", "علوم حاسوب", "هندسة", "فيزياء", "كيمياء", "أحياء", "رياضيات", "طب", "اقتصاد", "قانون"],
     ["site:just.edu.jo","site:ju.edu.jo","site:yu.edu.jo","site:hu.edu.jo","site:bau.edu.jo","site:aau.edu.jo","site:psut.edu.jo","site:gju.edu.jo"],
     ["site:edu.jo","site:jo","site:just.edu.jo","site:ju.edu.jo"]),
    ("lebanon", "Lebanon", "asia", "LB",
     ["محاضرة", "شرائح", "عرض تقديمي", "cours", "présentation", "diaporama", "lecture slides", "engineering", "computer science", "medicine", "business", "physics", "chemistry"],
     ["site:aub.edu.lb","site:lau.edu.lb","site:usj.edu.lb","site:ul.edu.lb","site:ndu.edu.lb","site:bau.edu.lb","site:balamand.edu.lb","site:auce.edu.lb"],
     ["site:edu.lb","site:lb","site:aub.edu.lb","site:lau.edu.lb"]),
    ("qatar", "Qatar", "asia", "QA",
     ["محاضرة", "شرائح", "عرض تقديمي", "lecture slides", "presentation", "course materials", "engineering", "computer science", "medicine", "business", "physics", "chemistry", "petroleum"],
     ["site:qu.edu.qa","site:hbku.edu.qa","site:cmu.edu.qa","site:qatar.tamu.edu","site:wcm-q.edu.qa","site:udst.edu.qa","site:gust.edu.kw"],
     ["site:edu.qa","site:qa","site:qu.edu.qa","site:hbku.edu.qa"]),
    ("ghana", "Ghana", "africa", "GH",
     ["lecture slides", "presentation", "course materials", "tutorial", "computer science", "engineering", "physics", "chemistry", "biology", "mathematics", "medicine", "economics", "business", "agriculture", "law"],
     ["site:ug.edu.gh","site:knust.edu.gh","site:ucc.edu.gh","site:uew.edu.gh","site:uds.edu.gh","site:gimpa.edu.gh","site:ashesi.edu.gh","site:upsa.edu.gh"],
     ["site:edu.gh","site:gh","site:ug.edu.gh","site:knust.edu.gh"]),
    ("tunisia", "Tunisia", "africa", "TN",
     ["cours magistral", "diaporama", "présentation", "matériel pédagogique", "محاضرة", "شرائح", "informatique", "ingénierie", "physique", "chimie", "mathématiques", "médecine"],
     ["site:ucar.rnu.tn","site:enit.rnu.tn","site:fst.rnu.tn","site:isi.rnu.tn","site:isg.rnu.tn","site:ensi.rnu.tn","site:enis.tn","site:supcom.tn"],
     ["site:rnu.tn","site:tn","site:enit.rnu.tn","site:fst.rnu.tn"]),
    ("costa_rica", "CostaRica", "south_america", "CR",
     ["diapositivas", "presentación", "material de clase", "seminario", "ingeniería", "física", "química", "biología", "matemáticas", "medicina", "economía", "derecho"],
     ["site:ucr.ac.cr","site:tec.ac.cr","site:una.ac.cr","site:uned.ac.cr","site:ulacit.ac.cr","site:uia.ac.cr"],
     ["site:ac.cr","site:cr","site:ucr.ac.cr","site:tec.ac.cr"]),
    ("uruguay", "Uruguay", "south_america", "UY",
     ["diapositivas", "presentación", "material de clase", "seminario", "ingeniería", "física", "química", "biología", "matemáticas", "medicina", "economía", "derecho"],
     ["site:udelar.edu.uy","site:ort.edu.uy","site:um.edu.uy","site:ucudal.edu.uy","site:uni.edu.uy","site:claeh.edu.uy"],
     ["site:edu.uy","site:uy","site:udelar.edu.uy","site:ort.edu.uy"]),
    ("cuba", "Cuba", "south_america", "CU",
     ["diapositivas", "presentación", "material de clase", "conferencia", "ingeniería", "física", "química", "biología", "matemáticas", "medicina", "economía"],
     ["site:uh.cu","site:cujae.edu.cu","site:uclv.edu.cu","site:uo.edu.cu","site:ucm.edu.cu","site:upr.edu.cu","site:instec.cu"],
     ["site:cu","site:edu.cu","site:uh.cu","site:cujae.edu.cu"]),
    ("sri_lanka", "SriLanka", "asia", "LK",
     ["lecture slides", "presentation", "course materials", "tutorial", "computer science", "engineering", "physics", "chemistry", "biology", "mathematics", "medicine", "economics", "business"],
     ["site:cmb.ac.lk","site:pdn.ac.lk","site:mrt.ac.lk","site:ruh.ac.lk","site:jfn.ac.lk","site:sjp.ac.lk","site:kln.ac.lk","site:sab.ac.lk"],
     ["site:ac.lk","site:lk","site:cmb.ac.lk","site:mrt.ac.lk"]),
    ("kazakhstan", "Kazakhstan", "asia", "KZ",
     ["лекция", "презентация", "учебные материалы", "семинар", "дәріс", "информатика", "инженерия", "физика", "химия", "биология", "математика", "медицина", "экономика"],
     ["site:kaznu.kz","site:nu.edu.kz","site:satbayev.university","site:enu.kz","site:kbtu.kz","site:aitu.edu.kz","site:iitu.edu.kz","site:kimep.kz"],
     ["site:kz","site:edu.kz","site:kaznu.kz","site:nu.edu.kz"]),
]

TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""{country}-focused PPTX scraper — Search-Engine-Driven ({region} Series)"""

import sys, os
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path: sys.path.insert(0, _root)

import argparse, hashlib, logging, random, re, time, warnings
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse
from src.utils.persistence import load_master_tags, save_new_tag
import requests, urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from ddgs import DDGS
    try:
        from ddgs.exceptions import RatelimitException
    except ImportError:
        class RatelimitException(Exception): pass
except ImportError:
    raise SystemExit("ddgs not installed. Run: pip install ddgs --break-system-packages")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

PRESENTATION_RE = re.compile(r"\\.pptx?($|[?#&\\s])", re.IGNORECASE)
BITSTREAM_RE = re.compile(r"/(?:bitstream(?:/handle)?/[\\d./]+|retrieve/\\d+|download/\\d+|file|attachment|get)/[^\\"\\'\\'\\s>{{}}[\\]\\\\]+\\.pptx?", re.IGNORECASE)
RAW_PPT_URL_RE = re.compile(r"https?://[^\\"\\'\\'\\s>{{}}[\\]\\\\]+\\.pptx?", re.IGNORECASE)
SKIP_EXTENSIONS = (".jpg",".jpeg",".png",".gif",".svg",".webp",".css",".js",".ico",".zip",".pdf",".doc",".docx",".mp4",".mp3",".avi",".mov",".woff",".ttf")

TOPICS: List[str] = {topics}

SITE_DOMAINS: List[str] = {domains}

ENGLISH_TOPICS = [
    "lecture slides", "presentation", "course materials", "seminar", "tutorial",
    "computer science", "artificial intelligence", "machine learning",
    "engineering", "electrical engineering", "civil engineering",
    "physics", "chemistry", "biology", "mathematics", "statistics",
    "medicine", "economics", "business", "law", "education",
]

def build_query_list() -> List[str]:
    queries = []
    for b in {broad}:
        queries.append(f"filetype:pptx {{b}}")
        queries.append(f"filetype:ppt {{b}}")
    remaining = []
    all_topics = TOPICS + ENGLISH_TOPICS
    for domain in SITE_DOMAINS:
        for topic in all_topics:
            remaining.append(f'"{{topic}}" filetype:pptx {{domain}}')
            if random.random() < 0.2:
                remaining.append(f'"{{topic}}" filetype:ppt {{domain}}')
    random.shuffle(remaining)
    return queries + remaining

class {classname}Scraper:
    def __init__(self, out_dir="downloaded_ppts_{slug}", request_timeout=20, delay_seconds=5.0, verify_ssl=True, max_results_per_query=300):
        self.out_dir = Path(out_dir); self.out_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = request_timeout; self.delay = delay_seconds; self.verify_ssl = verify_ssl
        self.max_results_per_query = max_results_per_query; self.session = self._build_session()
        self._seen_urls: Set[str] = set(); self._seen_tags: Set[str] = set()
        self._preload_seen_from_disk()
        if not verify_ssl:
            warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

    def _preload_seen_from_disk(self):
        self._seen_tags.update(load_master_tags())
        if self.out_dir.exists():
            for p in self.out_dir.glob("*_*"):
                tag = p.name.split("_")[0]
                if len(tag) == 10: self._seen_tags.add(tag)
        if self._seen_tags:
            logger.info("Resuming: Loaded %d seen tags.", len(self._seen_tags))

    def _build_session(self):
        s = requests.Session()
        s.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[429,500,502,503,504])))
        s.mount("http://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5)))
        s.headers.update({{"User-Agent": "Mozilla/5.0 {code}_Scraper/1.0 (Academic Research)"}}); return s

    def _search_ddgs(self, query):
        found = []
        for attempt in range(3):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=self.max_results_per_query))
                for r in results:
                    if r.get("href"): found.append(r["href"])
                break
            except RatelimitException:
                time.sleep(45 * (attempt + 1))
            except Exception as exc:
                if "Timeout" in str(exc) and attempt < 2: time.sleep(5); continue
                break
        return found

    def _extract_from_page(self, url):
        try:
            resp = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
            if not resp.ok or "html" not in resp.headers.get("Content-Type","").lower(): return []
            html = resp.text; found = []
            for m in RAW_PPT_URL_RE.finditer(html): found.append(m.group(0))
            for m in BITSTREAM_RE.finditer(html): found.append(urljoin(url, m.group(0)))
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                if PRESENTATION_RE.search(a["href"]): found.append(urljoin(url, a["href"].strip()))
            return list(set(found))
        except: return []

    def _safe_filename(self, url):
        tag = hashlib.sha1(url.encode()).hexdigest()[:10]
        name = Path(urlparse(url).path).name or "file.pptx"
        if not name.lower().endswith((".pptx", ".ppt")):
            return None, None
        clean = re.sub(r'[^\\w.\\-]', '_', name)
        return tag, f"{{tag}}_{{clean}}"

    def _download(self, url):
        tag, fname = self._safe_filename(url)
        if tag is None: return None
        dest = self.out_dir / fname
        if dest.exists(): self._seen_tags.add(tag); return dest
        try:
            resp = self.session.get(url, timeout=self.timeout, stream=True, verify=self.verify_ssl)
            if not resp.ok: return None
            if "text/html" in resp.headers.get("Content-Type","").lower() and not PRESENTATION_RE.search(url): return None
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(65536): f.write(chunk)
            if dest.stat().st_size < 5242880:
                dest.unlink(missing_ok=True); return None
            with open(dest, "rb") as chk:
                header = chk.read(8)
            if not (header[:2] == b"PK" or header[:8] == b"\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1"):
                dest.unlink(missing_ok=True); return None
            save_new_tag(tag)
            logger.info("  Downloaded: %s (%d KB)", dest.name, dest.stat().st_size // 1024); return dest
        except: return None

    def scrape(self, target=10000, follow_pages=True):
        queries = build_query_list(); count = 0
        logger.info("Starting {country} Scale-Up: Target=%d, Queries=%d", target, len(queries))
        for i, query in enumerate(queries, 1):
            if count >= target: break
            logger.info("[%d/%d] %s", i, len(queries), query)
            for url in self._search_ddgs(query):
                if count >= target: break
                tag = hashlib.sha1(url.encode()).hexdigest()[:10]
                if url in self._seen_urls or tag in self._seen_tags: continue
                self._seen_urls.add(url); to_download = []
                if PRESENTATION_RE.search(url): to_download.append(url)
                elif follow_pages and not any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                    for iu in self._extract_from_page(url):
                        itag = hashlib.sha1(iu.encode()).hexdigest()[:10]
                        if iu not in self._seen_urls and itag not in self._seen_tags:
                            to_download.append(iu); self._seen_urls.add(iu)
                for dl_url in to_download:
                    if count >= target: break
                    if self._download(dl_url): count += 1; logger.info("  Total Downloaded: [%d]", count)
            time.sleep(self.delay + random.uniform(0.1, 0.4))

def main():
    parser = argparse.ArgumentParser(description="{country} Academic PPTX Scraper")
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--no-verify-ssl", action="store_true")
    parser.add_argument("--no-follow", action="store_true")
    args = parser.parse_args()
    {classname}Scraper(verify_ssl=not args.no_verify_ssl).scrape(target=args.target, follow_pages=not args.no_follow)

if __name__ == "__main__": main()
'''

REGION_MAP = {"asia": "Asia", "europe": "Europe", "south_america": "South America", "africa": "Africa"}

for slug, classname, region, code, native_kws, domains, broad in COUNTRIES:
    content = TEMPLATE.format(
        country=classname.replace("CostaRica","Costa Rica").replace("SriLanka","Sri Lanka"),
        region=REGION_MAP.get(region, region.title()),
        classname=classname, slug=slug, code=code,
        topics=native_kws, domains=domains, broad=broad,
    )
    out_path = Path(region) / f"{slug}_pptx_scraper.py"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Created: {out_path}")

print(f"\nDone! Created {len(COUNTRIES)} new scrapers.")
