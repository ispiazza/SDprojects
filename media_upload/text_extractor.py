#!/usr/bin/env python3
# backend/media_upload/text_extractor.py
"""
Script to process all B (back) images using OpenAI API to extract text.
Creates JSON files containing extracted text with special focus on ID numbers.
"""

import os
import json
import base64
from pathlib import Path
import logging
from typing import Dict, List, Optional
import argparse
from openai import OpenAI
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# OpenAI Configuration
api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=api_key)
VISION_MODEL = "gpt-4o"

# Rate limiting configuration
REQUESTS_PER_MINUTE = 50 
REQUEST_DELAY = 60 / REQUESTS_PER_MINUTE


def encode_image_to_base64(image_path: Path) -> str:
    """
    Encode image to base64 string for OpenAI API.
    """
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logging.error(f"Error encoding image {image_path}: {e}")
        return None


def extract_text_from_image(image_path: Path, directory_name: str) -> Dict:
    """
    Use OpenAI Vision API to extract text from back image.
    Focus on ID number in bottom left and categorize other text as metadata.
    """
    try:
        # Encode image
        base64_image = encode_image_to_base64(image_path)
        if not base64_image:
            return {"error": "Failed to encode image"}
        
        # Prepare the prompt 
        system_prompt = """You are an expert text extraction specialist analyzing the back of museum/archive photographs. These images contain crucial identification numbers and various metadata.

Your task is to:
1. CRITICALLY IMPORTANT: Find and extract the ID number - this could be in the bottom left corner (for portrait images) OR top left corner (for landscape images). The ID is usually handwritten and may be in formats like "27.42", "63.8" or "2.43", etc.
2. Extract ALL other visible text including handwritten notes, printed labels, addresses, stamps, and any other markings
3. Organize this information in a structured JSON format

Be extremely thorough and extract even faded, partial, or unclear text. If text is unclear, include it but note the uncertainty."""

        user_prompt = f"""Please analyze this back image from directory "{directory_name}" and extract ALL text content.

CRITICAL: Look for the ID number which will be either:
- Bottom left corner (if portrait orientation)
- Top left corner (if landscape orientation)

Extract everything you can see including:
1. The ID number (MOST IMPORTANT, it could be in formats like "23.82", "3.82" or "23.8" ONLY)
2. Any handwritten notes or annotations  
3. Printed labels with names and addresses
4. Stamps or official markings
5. Any other text or numbers anywhere on the image

Return the data in this exact JSON format:
{{
  "id_number": "the ID found in corner",
  "metadata": {{
    "handwritten_notes": ["list of handwritten text"],
    "printed_labels": ["list of printed text"],
    "addresses": ["any addresses found"],
    "other_markings": ["any other text/numbers"]
  }},
  "extraction_notes": "any notes about unclear text or extraction confidence"
}}"""

        # Make API request with rate limiting
        time.sleep(REQUEST_DELAY)
        
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "system", 
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.1  # Low temperature for accurate text extraction
        )
        
        extracted_content = response.choices[0].message.content
        
        try:
            json_start = extracted_content.find('{')
            json_end = extracted_content.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_content = extracted_content[json_start:json_end]
                parsed_data = json.loads(json_content)
            else:
                # Fallback: create structured data from text response
                parsed_data = {
                    "id_number": "not_found",
                    "metadata": {
                        "raw_extraction": extracted_content,
                        "handwritten_notes": [],
                        "printed_labels": [],
                        "addresses": [],
                        "other_markings": []
                    },
                    "extraction_notes": "Could not parse as structured JSON, raw text included"
                }
        except json.JSONDecodeError:
            # Create fallback structure
            parsed_data = {
                "id_number": "parsing_error", 
                "metadata": {
                    "raw_extraction": extracted_content,
                    "handwritten_notes": [],
                    "printed_labels": [],
                    "addresses": [],
                    "other_markings": []
                },
                "extraction_notes": "JSON parsing failed, raw extraction included"
            }
        
        # Add processing metadata
        parsed_data["processing_info"] = {
            "image_path": str(image_path),
            "directory": directory_name,
            "processed_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "model_used": VISION_MODEL
        }
        
        logging.info(f"✓ Extracted text from {image_path.name}")
        logging.info(f"  ID found: {parsed_data.get('id_number', 'not_found')}")
        
        return parsed_data
        
    except Exception as e:
        logging.error(f"Error processing {image_path}: {e}")
        return {
            "error": str(e),
            "image_path": str(image_path),
            "directory": directory_name,
            "processed_at": time.strftime('%Y-%m-%d %H:%M:%S')
        }


def find_back_images(base_path: Path) -> List[tuple]:
    """
    Find all B (back) images in subdirectories.
    Returns list of (image_path, directory_name) tuples.
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
    back_images = []
    
    for directory in base_path.iterdir():
        if directory.is_dir():
            for file_path in directory.iterdir():
                if (file_path.suffix.lower() in image_extensions and 
                    file_path.is_file() and 
                    file_path.stem.endswith('B')):
                    back_images.append((file_path, directory.name))
    
    return back_images


def process_all_back_images(base_path: Path) -> Dict:
    """
    Process all back images and create JSON files in the same directory as the images.
    """
    if not base_path.exists():
        return {"error": f"Base path does not exist: {base_path}"}
    
    back_images = find_back_images(base_path)
    
    if not back_images:
        return {"error": "No back images (ending with 'B') found"}
    
    logging.info(f"Found {len(back_images)} back images to process")
    
    processed = 0
    failed = 0
    results = {}
    
    for image_path, directory_name in back_images:
        logging.info(f"Processing {directory_name}/{image_path.name}")
        
        # Extract text from image
        extraction_result = extract_text_from_image(image_path, directory_name)
        
        if "error" not in extraction_result:
            # Save JSON file in the same directory as the images
            json_filename = f"{directory_name}.json"
            json_path = image_path.parent / json_filename  
            
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(extraction_result, f, ensure_ascii=False, indent=2)
                
                processed += 1
                results[directory_name] = {
                    "status": "success",
                    "json_file": str(json_path),
                    "id_extracted": extraction_result.get("id_number", "not_found")
                }
                logging.info(f"✓ Saved {json_filename} in {image_path.parent}")
                
            except Exception as e:
                failed += 1
                results[directory_name] = {
                    "status": "failed",
                    "error": f"Failed to save JSON: {e}"
                }
                logging.error(f"Failed to save {json_filename}: {e}")
        else:
            failed += 1
            results[directory_name] = {
                "status": "failed", 
                "error": extraction_result["error"]
            }
            logging.error(f"Failed to process {directory_name}: {extraction_result['error']}")
    
    return {
        "status": "completed",
        "total_images": len(back_images),
        "processed": processed,
        "failed": failed,
        "results": results
    }


def main():
    parser = argparse.ArgumentParser(description='Extract text from back images using OpenAI Vision API')
    parser.add_argument('input_path', help='Path to directory containing image directories')
    parser.add_argument('--dry-run', action='store_true', help='List files that would be processed without processing them')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    base_path = Path(args.input_path)
    
    if args.dry_run:
        logging.info("DRY RUN MODE - Finding back images...")
        back_images = find_back_images(base_path)
        
        print(f"\nFound {len(back_images)} back images:")
        for image_path, directory_name in back_images:
            json_filename = f"{directory_name}.json"
            print(f"  Directory: {directory_name}")
            print(f"    Image: {image_path.name}")
            print(f"    Will create: {json_filename} (in same directory)")
            print()
        
        return 0
    
    logging.info(f"Processing back images in: {base_path}")
    logging.info(f"Using OpenAI model: {VISION_MODEL}")
    
    result = process_all_back_images(base_path)
    
    if result.get("status") == "completed":
        print(f"\n{'='*60}")
        print(f"TEXT EXTRACTION COMPLETE")
        print(f"{'='*60}")
        print(f"Total back images: {result['total_images']}")
        print(f"Successfully processed: {result['processed']}")
        print(f"Failed: {result['failed']}")
        print(f"JSON files saved in each image directory")
        
        # Show some example results
        print(f"\nEXAMPLE EXTRACTIONS:")
        shown = 0
        for dir_name, result_info in result['results'].items():
            if result_info['status'] == 'success' and shown < 5:
                print(f"  Directory {dir_name}:")
                print(f"    Created: {dir_name}.json")
                print(f"    ID extracted: {result_info['id_extracted']}")
                shown += 1
        
        if result['processed'] > 5:
            print(f"  ... and {result['processed'] - 5} more successful extractions")
            
        # Show failed extractions
        if result['failed'] > 0:
            print(f"\nFAILED EXTRACTIONS:")
            for dir_name, result_info in result['results'].items():
                if result_info['status'] == 'failed':
                    print(f"  {dir_name}: {result_info['error']}")
    else:
        print(f"ERROR: {result.get('error', 'Unknown error')}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())