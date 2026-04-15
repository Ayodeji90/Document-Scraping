import os
import zipfile
import subprocess
import glob
from pathlib import Path

def count_pptx_slides(filepath):
    """Count slides in a .pptx file by counting XML files in the zip structure."""
    try:
        with zipfile.ZipFile(filepath, 'r') as zip_ref:
            # Slides are stored as ppt/slides/slide1.xml, ppt/slides/slide2.xml, etc.
            slide_files = [f for f in zip_ref.namelist() if f.startswith('ppt/slides/slide') and f.endswith('.xml')]
            return len(slide_files)
    except Exception as e:
        print(f"Error reading {filepath.name}: {e}")
        return 0

def count_ppt_slides(filepath):
    """Count slides in a .ppt file using exiftool."""
    try:
        # exiftool -Slides -s -S returns just the number if it exists
        result = subprocess.run(
            ['exiftool', '-Slides', '-s', '-S', str(filepath)],
            capture_output=True,
            text=True
        )
        output = result.stdout.strip()
        if output.isdigit():
            return int(output)
        else:
            # Fallback: some .ppt files use "SlideCount"
            result = subprocess.run(
                ['exiftool', '-SlideCount', '-s', '-S', str(filepath)],
                capture_output=True,
                text=True
            )
            output = result.stdout.strip()
            return int(output) if output.isdigit() else 0
    except Exception as e:
        print(f"Error running exiftool on {filepath.name}: {e}")
        return 0

def main():
    target_dir = Path("downloaded_ppts")
    if not target_dir.exists():
        print(f"Directory {target_dir} not found.")
        return

    files = list(target_dir.glob("*.ppt*"))
    total_slides = 0
    pptx_count = 0
    ppt_count = 0
    errors = 0

    print(f"Analyzing {len(files)} files in {target_dir}...")

    for f in files:
        count = 0
        if f.suffix.lower() == '.pptx':
            count = count_pptx_slides(f)
            pptx_count += 1
        elif f.suffix.lower() == '.ppt':
            count = count_ppt_slides(f)
            ppt_count += 1
        
        if count == 0:
            errors += 1
        
        total_slides += count

    print("\n" + "="*40)
    print(f"SLIDE COUNT SUMMARY")
    print("="*40)
    print(f"Total .pptx files: {pptx_count}")
    print(f"Total .ppt files:  {ppt_count}")
    print(f"Files with 0 or error: {errors}")
    print("-"*40)
    print(f"TOTAL SLIDES:      {total_slides}")
    print("="*40)

if __name__ == "__main__":
    main()
