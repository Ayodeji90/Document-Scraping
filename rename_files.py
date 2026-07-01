import os
import argparse
from pathlib import Path

def rename_files_sequentially(target_dir="downloaded_ppts", start_index=1):
    directory = Path(target_dir)
    if not directory.exists():
        print(f"Error: Directory '{target_dir}' not found.")
        return

    # Get all files and sort them alphabetically
    # Filter for .ppt and .pptx files only
    valid_extensions = {".ppt", ".pptx"}
    files = sorted([f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions])
    
    if not files:
        print("No .ppt/.pptx files found in directory.")
        return

    print(f"Found {len(files)} files. Renaming sequentially starting from {start_index:06d}...")
    
    mapping_file = directory / "rename_mapping.log"
    
    # Open in append mode to keep history if needed, but for a clean rename 
    # the user might want to overwrite. We'll append for safety.
    with open(mapping_file, "a", encoding="utf-8") as log:
        log.write(f"\n--- Rename Session starting at {start_index:06d} ---\n")
        log.write("New Name | Original Name\n")
        log.write("-" * 50 + "\n")
        
        for i, file_path in enumerate(files, start=start_index):
            extension = file_path.suffix
            new_name = f"{i:06d}{extension}"
            new_path = directory / new_name
            
            # Skip if it's already named that way (to avoid errors on re-runs)
            if file_path.name == new_name:
                continue
                
            # Log the change
            log.write(f"{new_name} | {file_path.name}\n")
            
            # Perform the rename
            try:
                os.rename(file_path, new_path)
            except Exception as e:
                print(f"  ❌ Error renaming {file_path.name}: {e}")

    print(f"Successfully processed {len(files)} files.")
    print(f"A log of the original filenames has been saved/appended to: {mapping_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename PPT files sequentially.")
    parser.add_argument("--start", type=int, default=1, help="Starting index for naming (e.g. 577)")
    parser.add_argument("--dir", type=str, default="downloaded_ppts", help="Target directory")
    
    args = parser.parse_args()
    rename_files_sequentially(target_dir=args.dir, start_index=args.start)
