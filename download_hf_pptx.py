#!/usr/bin/env python3
"""
Downloads PPTX files from HuggingFace noxneural/pptx_collection_templates,
filters out Chinese content, USA content, empty files, and files under 2MB.
Clean files go to hf_clean_pptx/ folder.
"""

import hashlib
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError:
    print("Installing huggingface_hub...")
    os.system(f"{sys.executable} -m pip install huggingface_hub --break-system-packages -q")
    from huggingface_hub import snapshot_download

# --- Config ---
REPO_ID = "noxneural/pptx_collection_templates"
RAW_DIR = Path("hf_raw_download")       # Raw download from HuggingFace
CLEAN_DIR = Path("hf_clean_pptx")       # Filtered clean files go here
REJECT_DIR = Path("hf_rejected")        # Rejected files (for inspection)
MIN_SIZE = 2 * 1024 * 1024              # 2 MB minimum

# Keywords in filename that indicate USA content
USA_KEYWORDS = [
    "american", "united states", "usa ", "u.s.", "fourth of july", "4th of july",
    "independence day", "thanksgiving", "memorial day", "veterans day",
    "presidents day", "martin luther king", "mlk", "super bowl",
    "nfl", "nba", "mlb", "us election", "us president",
    "washington", "lincoln", "obama", "trump", "biden",
    "us constitution", "bill of rights", "american revolution",
    "civil war", "us history", "american history",
    "us government", "american flag", "stars and stripes",
    "pledge of allegiance", "state of the union",
]

# Keywords for Chinese/HK/Taiwan content  
CHINA_KEYWORDS = [
    "chinese", "china", "hong kong", "taiwan", "beijing", "shanghai",
    "mandarin", "cantonese", "lunar new year", "spring festival",
    "mid-autumn", "dragon boat", "confuci",
]

def is_usa_filename(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in USA_KEYWORDS)

def is_china_filename(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in CHINA_KEYWORDS)

def has_chinese_content(filepath: Path) -> bool:
    """Check if PPTX contains significant Chinese characters."""
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            for name in z.namelist():
                if "slide1.xml" in name or "slide/slide1.xml" in name:
                    data = z.read(name).decode("utf-8", errors="ignore")
                    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", data))
                    if cn_chars > 50:
                        return True
                    break
    except:
        pass
    return False

def has_us_content(filepath: Path) -> bool:
    """Check if PPTX slide content is heavily US-focused."""
    us_terms = ["united states", "american", "u.s.a", "washington d.c", 
                "congress", "senate", "house of representatives",
                "federal government", "constitution of the united"]
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            text = ""
            for name in z.namelist():
                if "slide" in name and name.endswith(".xml"):
                    text += z.read(name).decode("utf-8", errors="ignore").lower()
                    if len(text) > 50000:
                        break
            hits = sum(1 for term in us_terms if term in text)
            return hits >= 3  # 3+ US-specific terms = US content
    except:
        pass
    return False

def is_valid_pptx(filepath: Path) -> bool:
    """Check magic bytes: PK (PPTX/ZIP) or D0CF (old PPT)."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
        return header[:2] == b"PK" or header[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except:
        return False

def load_existing_tags() -> set:
    """Load existing dedup tags to avoid re-adding duplicates."""
    tags = set()
    tag_file = Path("logs/master_seen_tags.txt")
    if tag_file.exists():
        with open(tag_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    tags.add(line)
    return tags

def main():
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    REJECT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Download from HuggingFace
    print("=" * 60)
    print("📥 Step 1: Downloading from HuggingFace...")
    print(f"   Repo: {REPO_ID}")
    print(f"   This may take a while (20.2 GB)...")
    print("=" * 60)

    local_path = snapshot_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        allow_patterns=["*.pptx", "*.ppt"],
        local_dir=str(RAW_DIR),
    )
    raw_path = Path(local_path)

    # Step 2: Collect all PPTX files
    all_files = list(raw_path.rglob("*.pptx")) + list(raw_path.rglob("*.ppt"))
    print(f"\n📂 Found {len(all_files)} presentation files in download.")

    # Load existing tags for dedup
    existing_tags = load_existing_tags()
    print(f"🔗 Loaded {len(existing_tags)} existing dedup tags.")

    # Step 3: Filter
    stats = {
        "total": len(all_files),
        "too_small": 0,
        "invalid": 0,
        "china_filename": 0,
        "china_content": 0,
        "usa_filename": 0,
        "usa_content": 0,
        "duplicate": 0,
        "kept": 0,
    }

    print("\n🔍 Step 2: Filtering files...")
    for i, f in enumerate(all_files, 1):
        if i % 100 == 0:
            print(f"   Processing {i}/{len(all_files)}...")

        reason = None

        # Check size
        try:
            size = f.stat().st_size
        except:
            reason = "invalid"
            stats["invalid"] += 1

        if not reason and size < MIN_SIZE:
            reason = "too_small"
            stats["too_small"] += 1

        # Check valid PPT format
        if not reason and not is_valid_pptx(f):
            reason = "invalid"
            stats["invalid"] += 1

        # Check filename for China/USA
        if not reason and is_china_filename(f.name):
            reason = "china_filename"
            stats["china_filename"] += 1

        if not reason and is_usa_filename(f.name):
            reason = "usa_filename"
            stats["usa_filename"] += 1

        # Dedup check
        if not reason:
            tag = hashlib.sha1(f.name.encode()).hexdigest()[:10]
            if tag in existing_tags:
                reason = "duplicate"
                stats["duplicate"] += 1

        # Deep content check (only for files that passed above)
        if not reason and has_chinese_content(f):
            reason = "china_content"
            stats["china_content"] += 1

        if not reason and has_us_content(f):
            reason = "usa_content"
            stats["usa_content"] += 1

        # Move to appropriate folder
        if reason:
            dest = REJECT_DIR / f"{reason}" 
            dest.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(f, dest / f.name)
            except:
                pass
        else:
            # Clean file — keep it
            try:
                shutil.copy2(f, CLEAN_DIR / f.name)
                stats["kept"] += 1
            except Exception as e:
                print(f"   ⚠️ Error copying {f.name}: {e}")

    # Step 4: Print summary
    print("\n" + "=" * 60)
    print("📊 FILTERING RESULTS")
    print("=" * 60)
    print(f"   Total files found:      {stats['total']}")
    print(f"   ❌ Too small (<2MB):     {stats['too_small']}")
    print(f"   ❌ Invalid format:       {stats['invalid']}")
    print(f"   ❌ China (filename):     {stats['china_filename']}")
    print(f"   ❌ China (content):      {stats['china_content']}")
    print(f"   ❌ USA (filename):       {stats['usa_filename']}")
    print(f"   ❌ USA (content):        {stats['usa_content']}")
    print(f"   ❌ Duplicate:            {stats['duplicate']}")
    print(f"   ✅ KEPT (clean):         {stats['kept']}")
    print("=" * 60)
    print(f"\n✅ Clean files saved to: {CLEAN_DIR.absolute()}")
    print(f"🗑️  Rejected files in:   {REJECT_DIR.absolute()}")

if __name__ == "__main__":
    main()
