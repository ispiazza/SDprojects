#!/usr/bin/env python3
# backend/media_upload/scan_formatting.py
"""
Uploads a zip file of numbered images and separates every two scans into individual directories.
Each directory is named after the first image number in the pair.
"""

import os
import zipfile
import shutil
from pathlib import Path
import re
import sys
import logging
from typing import List, Tuple


logging.basicConfig(
    level=logging.INFO, 
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def process_uploaded_zip(zip_path: str, output_dir: str = "scans/processed_images") -> dict:
    """
    Process a zip file containing numbered images.
    """
    try:
        zip_path = Path(zip_path)
        output_dir = Path(output_dir)
        
        if not zip_path.exists():
            return {"success": False, "error": f"Zip file not found: {zip_path}"}
        
        if not zip_path.suffix.lower() == '.zip':
            return {"success": False, "error": "File must be a .zip file"}
        
        # Create output dir
        output_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Output directory: {output_dir.absolute()}")

        logging.info(f"Processing zip file: {zip_path}")

        # 1. Extract zip file
        temp_dir = extract_zip(zip_path, output_dir)

        # 2. Get all images and organise them
        images = get_sorted_images(temp_dir)
        
        if len(images) < 2:
            return {"success": False, "error": f"Need at least 2 images, found {len(images)}"}
        
        # 3. Create pairs and organize into dirs
        pairs_created = create_image_pairs(images, output_dir)
        
        # 4. Clean up temporary dir
        shutil.rmtree(temp_dir)
        
        return {
            "success": True,
            "message": f"Successfully processed {pairs_created} image pairs",
            "pairs_created": pairs_created,
            "output_directory": str(output_dir.absolute())
        }
        
    except Exception as e:
        return {"success": False, "error": f"Processing failed: {str(e)}"}


def extract_zip(zip_path: Path, output_dir: Path) -> Path:
    """
    Extract zip file to a temporary directory.
    """
    temp_dir = output_dir / f"temp_{zip_path.stem}"
    temp_dir.mkdir(exist_ok=True)

    logging.info(f"Extracting to temporary directory: {temp_dir}")

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
    
    return temp_dir


def get_sorted_images(directory: Path) -> List[Path]:
    """
    Get all image files from directory and sort them numerically.
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
    
    images = []
    for file_path in directory.rglob('*'):
        if file_path.suffix.lower() in image_extensions:
            images.append(file_path)
    
    def get_sort_key(path):
        numbers = re.findall(r'\d+', path.stem)
        if numbers:
            return int(max(numbers, key=len))
        else:
            return float('inf'), path.stem.lower()
    
    images.sort(key=get_sort_key)

    logging.info(f"Found {len(images)} images:")
    for i, img in enumerate(images[:10]):
        logging.info(f"  {i+1}. {img.name}")
    if len(images) > 10:
        logging.info(f"  ... and {len(images) - 10} more")

    return images


def create_image_pairs(images: List[Path], output_dir: Path) -> int:
    """
    Create directories for image pairs and copy images.
    Returns: number of pairs created
    """
    pairs_created = 0
    
    for i in range(0, len(images), 2):
        if i + 1 >= len(images):
            logging.warning(f"Odd number of images. Skipping last image: {images[i].name}")
            break
        
        img1, img2 = images[i], images[i + 1]
        
        dir_name = extract_number_for_directory(img1.name)
        
        # make dir for pair
        pair_dir = output_dir / dir_name
        pair_dir.mkdir(exist_ok=True)
        
        # copy images to dir
        img1_dest = pair_dir / img1.name
        img2_dest = pair_dir / img2.name
        
        shutil.copy2(img1, img1_dest)
        shutil.copy2(img2, img2_dest)
        
        pairs_created += 1
    
    return pairs_created


def extract_number_for_directory(filename: str) -> str:
    """
    Extract number from filename to use as directory name.
    """
    numbers = re.findall(r'\d+', filename)
    
    if numbers:
        number = int(numbers[0])
        return f"{number:03d}"
    else:
        return Path(filename).stem


def main():    
    if len(sys.argv) != 2:
        sys.exit(1)
    
    zip_file = sys.argv[1]
    
    result = process_uploaded_zip(zip_file)
    
    if result["success"]:
        logging.info(f"SUCCESS: {result['message']}")
        logging.info(f"Output directory: {result['output_directory']}")
    else:
        logging.error(f"ERROR: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()