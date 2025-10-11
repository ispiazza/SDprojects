#!/usr/bin/env python3
# backend/media_upload/classify_and_rename.py
"""
Script to identify front and back images in organized directories and rename them accordingly.
Front images (A)
Back images (B) - Back images are typically mainly white with text/scribbles.
"""

import os
import cv2
import numpy as np
from pathlib import Path
import logging
from typing import List, Tuple, Dict
import argparse
from PIL import Image, ImageStat


logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def analyze_image_characteristics(image_path: Path) -> Dict[str, float]:
    """
    Analyze image characteristics to determine if it's the back (white with text).
    Returns dictionary with various metrics.
    """
    try:
        # PIL for better color analysis
        pil_image = Image.open(image_path)
        
        # Convert to RGB if needed
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        
        # Get basic stats
        stat = ImageStat.Stat(pil_image)
        
        # Calculate brightness (average of RGB means)
        brightness = sum(stat.mean) / 3
        
        # OpenCV for more detailed analysis
        cv_image = cv2.imread(str(image_path))
        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        
        # Convert to grayscale
        gray = cv2.cvtColor(cv_image, cv2.COLOR_RGB2GRAY)
        
        # Calculate whiteness percentage (pixels above threshold)
        white_threshold = 200
        white_pixels = np.sum(gray > white_threshold)
        total_pixels = gray.shape[0] * gray.shape[1]
        whiteness_ratio = white_pixels / total_pixels
        
        # Calculate edge density (text/scribbles have more edges)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / total_pixels
        
        # Calculate standard deviation (text areas have more variation)
        std_dev = np.std(gray)
        
        # Calculate histogram peak (white background should have peak near 255)
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist_peak_position = np.argmax(hist)
        hist_peak_value = np.max(hist) / total_pixels
        
        return {
            'brightness': brightness,
            'whiteness_ratio': whiteness_ratio,
            'edge_density': edge_density,
            'std_dev': std_dev,
            'hist_peak_position': hist_peak_position,
            'hist_peak_value': hist_peak_value,
            'file_size_mb': image_path.stat().st_size / (1024 * 1024)
        }
        
    except Exception as e:
        logging.error(f"Error analyzing {image_path}: {e}")
        return {}


def classify_back_image(metrics1: Dict, metrics2: Dict, filename1: str, filename2: str) -> Tuple[bool, str]:
    """
    Classify which image is the back based on metrics.
    Returns (is_first_image_back, reasoning)
    """
    if not metrics1 or not metrics2:
        return False, "Could not analyze one or both images"
    
    score1 = 0
    score2 = 0
    reasoning_parts = []
    
    # Brightness score (back images tend to be brighter/whiter)
    if metrics1['brightness'] > metrics2['brightness']:
        score1 += 2
        reasoning_parts.append(f"{filename1} is brighter ({metrics1['brightness']:.1f} vs {metrics2['brightness']:.1f})")
    else:
        score2 += 2
        reasoning_parts.append(f"{filename2} is brighter ({metrics2['brightness']:.1f} vs {metrics1['brightness']:.1f})")
    
    # Whiteness ratio score
    if metrics1['whiteness_ratio'] > metrics2['whiteness_ratio']:
        score1 += 3
        reasoning_parts.append(f"{filename1} has more white pixels ({metrics1['whiteness_ratio']:.2f} vs {metrics2['whiteness_ratio']:.2f})")
    else:
        score2 += 3
        reasoning_parts.append(f"{filename2} has more white pixels ({metrics2['whiteness_ratio']:.2f} vs {metrics1['whiteness_ratio']:.2f})")
    
    # Edge density (text/scribbles create edges, but too many edges might indicate complex front)
    # Moderate edge density is good for back images with text
    optimal_edge_density = 0.05  # Adjust based on your images
    edge_diff1 = abs(metrics1['edge_density'] - optimal_edge_density)
    edge_diff2 = abs(metrics2['edge_density'] - optimal_edge_density)
    
    if edge_diff1 < edge_diff2:
        score1 += 1
        reasoning_parts.append(f"{filename1} has more suitable edge density for text ({metrics1['edge_density']:.3f})")
    else:
        score2 += 1
        reasoning_parts.append(f"{filename2} has more suitable edge density for text ({metrics2['edge_density']:.3f})")
    
    # Histogram peak position (white backgrounds peak near 255)
    if metrics1['hist_peak_position'] > metrics2['hist_peak_position']:
        score1 += 1
        reasoning_parts.append(f"{filename1} has whiter histogram peak ({metrics1['hist_peak_position']} vs {metrics2['hist_peak_position']})")
    else:
        score2 += 1
        reasoning_parts.append(f"{filename2} has whiter histogram peak ({metrics2['hist_peak_position']} vs {metrics1['hist_peak_position']})")
    
    # File size consideration (back images tend to be smaller)
    if metrics1['file_size_mb'] < metrics2['file_size_mb']:
        score1 += 0.5
        reasoning_parts.append(f"{filename1} is smaller file ({metrics1['file_size_mb']:.2f}MB vs {metrics2['file_size_mb']:.2f}MB)")
    else:
        score2 += 0.5
        reasoning_parts.append(f"{filename2} is smaller file ({metrics2['file_size_mb']:.2f}MB vs {metrics1['file_size_mb']:.2f}MB)")
    
    is_first_back = score1 > score2
    winner = filename1 if is_first_back else filename2
    winner_score = score1 if is_first_back else score2
    
    reasoning = f"Classified {winner} as back (score: {winner_score:.1f}). Reasoning: {'; '.join(reasoning_parts)}"
    
    return is_first_back, reasoning


def process_directory(dir_path: Path, dry_run: bool = False) -> Dict:
    """
    Process a single directory containing two images.
    Identify which is front/back and rename accordingly.
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
    
    # Find all images in directory
    images = []
    for file_path in dir_path.iterdir():
        if file_path.suffix.lower() in image_extensions and file_path.is_file():
            images.append(file_path)
    
    if len(images) != 2:
        return {
            'status': 'error',
            'message': f"Expected 2 images, found {len(images)} in {dir_path.name}"
        }
    
    # Sort images by name for consistent processing
    images.sort(key=lambda x: x.name)
    img1, img2 = images
    
    # Analyze both images
    logging.info(f"Analyzing images in {dir_path.name}: {img1.name}, {img2.name}")
    
    metrics1 = analyze_image_characteristics(img1)
    metrics2 = analyze_image_characteristics(img2)
    
    # Classify which is back
    is_first_back, reasoning = classify_back_image(metrics1, metrics2, img1.name, img2.name)
    
    # Determine new names
    if is_first_back:
        back_img, front_img = img1, img2
    else:
        back_img, front_img = img2, img1
    
    # Create new names (remove existing A/B suffixes if present, then add new ones)
    front_stem = front_img.stem.rstrip('AB')
    back_stem = back_img.stem.rstrip('AB')
    
    front_new_name = f"{front_stem}A{front_img.suffix}"
    back_new_name = f"{back_stem}B{back_img.suffix}"
    
    front_new_path = dir_path / front_new_name
    back_new_path = dir_path / back_new_name
    
    result = {
        'status': 'success',
        'directory': dir_path.name,
        'front_original': front_img.name,
        'back_original': back_img.name,
        'front_new': front_new_name,
        'back_new': back_new_name,
        'reasoning': reasoning,
        'metrics': {
            'front': {k: round(v, 3) if isinstance(v, float) else v for k, v in (metrics2 if is_first_back else metrics1).items()},
            'back': {k: round(v, 3) if isinstance(v, float) else v for k, v in (metrics1 if is_first_back else metrics2).items()}
        }
    }
    
    # Perform renaming (if not dry run)
    if not dry_run:
        try:
            if front_img.name != front_new_name:
                if front_new_path.exists():
                    front_new_path.unlink()  # Remove existing file
                front_img.rename(front_new_path)
                
            if back_img.name != back_new_name:
                if back_new_path.exists():
                    back_new_path.unlink()  # Remove existing file
                back_img.rename(back_new_path)
                
            result['renamed'] = True
            logging.info(f"✓ Renamed files in {dir_path.name}")
            
        except Exception as e:
            result['status'] = 'error'
            result['message'] = f"Failed to rename files: {e}"
            logging.error(f"Error renaming files in {dir_path.name}: {e}")
    else:
        result['renamed'] = False
        logging.info(f"✓ Would rename files in {dir_path.name} (dry run)")
    
    return result


def process_all_directories(base_path: Path, dry_run: bool = False) -> Dict:
    """
    Process all subdirectories in the base path.
    """
    if not base_path.exists():
        return {'status': 'error', 'message': f"Base path does not exist: {base_path}"}
    
    # Find all subdirectories that contain images
    directories_to_process = []
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
    
    for item in base_path.iterdir():
        if item.is_dir():
            # Check if directory contains images
            images = [f for f in item.iterdir() if f.suffix.lower() in image_extensions and f.is_file()]
            if len(images) == 2:
                directories_to_process.append(item)
            elif len(images) > 0:
                logging.warning(f"Directory {item.name} has {len(images)} images (expected 2)")
    
    if not directories_to_process:
        return {'status': 'error', 'message': 'No directories with exactly 2 images found'}
    
    logging.info(f"Found {len(directories_to_process)} directories to process")
    
    results = []
    successful = 0
    failed = 0
    
    for directory in sorted(directories_to_process):
        result = process_directory(directory, dry_run)
        results.append(result)
        
        if result['status'] == 'success':
            successful += 1
        else:
            failed += 1
            logging.error(f"Failed to process {directory.name}: {result.get('message', 'Unknown error')}")
    
    return {
        'status': 'success',
        'total_directories': len(directories_to_process),
        'successful': successful,
        'failed': failed,
        'results': results,
        'dry_run': dry_run
    }


def main():
    parser = argparse.ArgumentParser(description='Classify and rename front/back images')
    parser.add_argument('path', help='Path to directory containing image directories')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be renamed without actually renaming')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    base_path = Path(args.path)
    
    logging.info(f"Processing images in: {base_path}")
    if args.dry_run:
        logging.info("DRY RUN MODE - No files will be renamed")
    
    result = process_all_directories(base_path, args.dry_run)
    
    if result['status'] == 'success':
        print(f"\n{'='*60}")
        print(f"PROCESSING COMPLETE")
        print(f"{'='*60}")
        print(f"Total directories processed: {result['total_directories']}")
        print(f"Successful: {result['successful']}")
        print(f"Failed: {result['failed']}")
        
        if args.dry_run:
            print(f"\nDRY RUN - No files were actually renamed")
            print(f"Run without --dry-run to perform actual renaming")
        
        # Show detailed results for failed directories
        if result['failed'] > 0:
            print(f"\nFAILED DIRECTORIES:")
            for res in result['results']:
                if res['status'] == 'error':
                    print(f"  - {res.get('directory', 'Unknown')}: {res.get('message', 'Unknown error')}")
        
        # Show some successful examples
        print(f"\nEXAMPLE CLASSIFICATIONS:")
        shown = 0
        for res in result['results']:
            if res['status'] == 'success' and shown < 5:
                print(f"  Directory: {res['directory']}")
                print(f"    Front: {res['front_original']} → {res['front_new']}")
                print(f"    Back:  {res['back_original']} → {res['back_new']}")
                print(f"    Reason: {res['reasoning'][:100]}...")
                print()
                shown += 1
        
        if result['successful'] > 5:
            print(f"  ... and {result['successful'] - 5} more successful classifications")
            
    else:
        print(f"ERROR: {result['message']}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())