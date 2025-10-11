#!/usr/bin/env python3
# backend/media_upload/table_generator.py
"""
Generates a comprehensive data table from processed JSON files with flagging for issues.
"""

import json
import csv
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple
import logging
from collections import defaultdict
import re

def extract_issue_flags(extraction_notes: str) -> List[str]:
    """
    Analyze extraction notes and return flags for potential issues.
    """
    flags = []
    if not extraction_notes:
        return flags
    
    notes_lower = extraction_notes.lower()
    
    # Check for text quality issues
    quality_issues = [
        'faint text', 'faded text', 'unclear text', 'blurry text',
        'not able to read', 'cannot read', 'unreadable', 'illegible',
        'partially visible', 'hard to read', 'difficult to read',
        'poor quality', 'damaged', 'worn', 'scratched'
    ]
    
    for issue in quality_issues:
        if issue in notes_lower:
            flags.append('quality_issue')
            break
    
    # Check for missing or no text
    no_text_issues = [
        'no text', 'no other text', 'blank', 'empty', 
        'nothing visible', 'no content'
    ]
    
    for issue in no_text_issues:
        if issue in notes_lower:
            flags.append('no_text')
            break
    
    return flags

def find_duplicate_ids(data_rows: List[Dict]) -> Dict[str, List[int]]:
    """
    Find duplicate ID numbers and return mapping of ID -> list of row indices.
    """
    id_to_rows = defaultdict(list)
    
    for i, row in enumerate(data_rows):
        id_number = row.get('id_number', '').strip()
        if id_number and id_number not in ['not_found', 'parsing_error', '']:
            id_to_rows[id_number].append(i)
    
    # Only return IDs that appear more than once
    return {id_num: rows for id_num, rows in id_to_rows.items() if len(rows) > 1}

def generate_data_table(base_path: Path) -> Tuple[List[Dict], Dict]:
    """
    Generate comprehensive data table from all JSON files.
    Returns: (data_rows, summary_stats)
    """
    if not base_path.exists():
        raise FileNotFoundError(f"Base path does not exist: {base_path}")
    
    data_rows = []
    stats = {
        'total_items': 0,
        'duplicates': 0,
        'quality_issues': 0,
        'processing_errors': 0,
        'missing_ids': 0
    }
    
    # Find all JSON files
    json_files = list(base_path.rglob("*.json"))
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract directory name (item identifier)
            directory_name = json_file.parent.name
            
            # Find corresponding front and back images
            front_image = None
            back_image = None
            
            for img_file in json_file.parent.iterdir():
                if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp']:
                    if img_file.stem.endswith('A'):
                        front_image = str(img_file.relative_to(base_path))
                    elif img_file.stem.endswith('B'):
                        back_image = str(img_file.relative_to(base_path))
            
            # Create row data
            row = {
                'directory': directory_name,
                'id_number': data.get('id_number', ''),
                'front_image_path': front_image or '',
                'back_image_path': back_image or '',
                'extraction_notes': data.get('extraction_notes', ''),
                'processed_at': data.get('processing_info', {}).get('processed_at', ''),
                'model_used': data.get('processing_info', {}).get('model_used', ''),
                'handwritten_notes': ', '.join(data.get('metadata', {}).get('handwritten_notes', [])),
                'printed_labels': ', '.join(data.get('metadata', {}).get('printed_labels', [])),
                'addresses': ', '.join(data.get('metadata', {}).get('addresses', [])),
                'other_markings': ', '.join(data.get('metadata', {}).get('other_markings', [])),
                'has_error': 'error' in data,
                'error_message': data.get('error', ''),
                'flags': []  # Will be populated later
            }
            
            # Extract flags from extraction notes
            flags = extract_issue_flags(row['extraction_notes'])
            row['flags'] = flags
            
            # Update statistics
            if 'quality_issue' in flags:
                stats['quality_issues'] += 1
            
            if row['has_error']:
                stats['processing_errors'] += 1
            
            if row['id_number'] in ['not_found', 'parsing_error', '']:
                stats['missing_ids'] += 1
            
            data_rows.append(row)
            stats['total_items'] += 1
            
        except Exception as e:
            logging.error(f"Error processing {json_file}: {e}")
            # Create error row
            row = {
                'directory': json_file.parent.name,
                'id_number': 'ERROR',
                'front_image_path': '',
                'back_image_path': '',
                'extraction_notes': f'Failed to process JSON: {str(e)}',
                'processed_at': '',
                'model_used': '',
                'handwritten_notes': '',
                'printed_labels': '',
                'addresses': '',
                'other_markings': '',
                'has_error': True,
                'error_message': str(e),
                'flags': ['processing_error']
            }
            data_rows.append(row)
            stats['total_items'] += 1
            stats['processing_errors'] += 1
    
    # Find duplicate IDs
    duplicates = find_duplicate_ids(data_rows)
    
    # Flag duplicate rows
    for id_number, row_indices in duplicates.items():
        for idx in row_indices:
            if 'duplicate_id' not in data_rows[idx]['flags']:
                data_rows[idx]['flags'].append('duplicate_id')
        stats['duplicates'] += len(row_indices)
    
    return data_rows, stats

def create_csv_table(data_rows: List[Dict], output_path: Path) -> None:
    """
    Create CSV file from data rows.
    """
    if not data_rows:
        logging.warning("No data rows to write to CSV")
        return
    
    # Define column order
    columns = [
        'directory',
        'id_number', 
        'front_image_path',
        'back_image_path',
        'extraction_notes',
        'handwritten_notes',
        'printed_labels',
        'addresses',
        'other_markings',
        'processed_at',
        'model_used',
        'has_error',
        'error_message',
        'flags'
    ]
    
    # Create CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        
        for row in data_rows:
            # Convert flags list to string
            row_copy = row.copy()
            row_copy['flags'] = ', '.join(row['flags']) if row['flags'] else ''
            writer.writerow(row_copy)
    
    logging.info(f"✓ CSV table created: {output_path}")

def truncate_text(text: str, max_length: int = 50) -> tuple[str, bool]:
    """
    Truncate text to max_length and return (truncated_text, was_truncated)
    """
    if not text or len(text) <= max_length:
        return text, False
    return text[:max_length] + "...", True

def create_tooltip_cell(content: str, max_length: int = 50) -> str:
    """
    Create a table cell with tooltip for long content
    """
    if not content:
        return ""
    
    truncated, was_truncated = truncate_text(content, max_length)
    
    if was_truncated:
        # Escape HTML characters in content
        escaped_content = content.replace('"', '&quot;').replace("'", '&#39;').replace('<', '&lt;').replace('>', '&gt;')
        return f'''
        <div class="tooltip truncated-cell">
            {truncated}
            <span class="tooltiptext">{escaped_content}</span>
        </div>
        '''
    else:
        return truncated

def create_html_table(data_rows: List[Dict], stats: Dict, output_path: Path) -> None:
    """
    Create HTML table with styling and flagging.
    """
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Processing Results Summary</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        
        .header {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        
        .stat-item {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #007bff;
        }}
        
        .stat-number {{
            font-size: 2rem;
            font-weight: bold;
            color: #333;
        }}
        
        .table-container {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th {{
            background-color: #343a40;
            color: white;
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        td {{
            padding: 10px 8px;
            border-bottom: 1px solid #dee2e6;
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            position: relative;
        }}
        
        .truncated-cell {{
            max-width: 150px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            cursor: pointer;
        }}
        
        .truncated-cell:hover {{
            background-color: #f0f8ff;
        }}
        
        .notes-cell {{
            max-width: 200px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .long-text-cell {{
            max-width: 120px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        /* Tooltip styles */
        .tooltip {{
            position: relative;
            display: inline-block;
        }}
        
        .tooltip .tooltiptext {{
            visibility: hidden;
            width: 300px;
            background-color: #333;
            color: #fff;
            text-align: left;
            border-radius: 6px;
            padding: 10px;
            position: absolute;
            z-index: 1000;
            bottom: 125%;
            left: 50%;
            margin-left: -150px;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 0.85rem;
            line-height: 1.4;
            white-space: normal;
            word-wrap: break-word;
            max-height: 200px;
            overflow-y: auto;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        
        .tooltip:hover .tooltiptext {{
            visibility: visible;
            opacity: 1;
        }}
        
        .tooltip .tooltiptext::after {{
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: #333 transparent transparent transparent;
        }}
        
        tr:hover {{
            background-color: #f8f9fa;
        }}
        
        /* Row flagging styles */
        .row-duplicate {{
            background-color: #ffebee !important;
            border-left: 4px solid #f44336;
        }}
        
        .row-quality-issue {{
            background-color: #fff3e0 !important;
            border-left: 4px solid #ff9800;
        }}
        
        .row-error {{
            background-color: #fce4ec !important;
            border-left: 4px solid #e91e63;
        }}
        
        .flag-badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 4px;
        }}
        
        .flag-duplicate {{
            background-color: #ffcdd2;
            color: #d32f2f;
        }}
        
        .flag-quality {{
            background-color: #ffe0b2;
            color: #f57c00;
        }}
        
        .flag-error {{
            background-color: #f8bbd9;
            color: #c2185b;
        }}
        
        .image-path {{
            font-family: monospace;
            font-size: 0.85rem;
            color: #666;
        }}
        
        .legend {{
            margin-top: 20px;
            padding: 15px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .legend h3 {{
            margin-top: 0;
            color: #333;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 8px 0;
        }}
        
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 4px;
            margin-right: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🗃️ Processing Results Summary</h1>
        <p>Generated on: {stats.get('generated_at', 'N/A')}</p>
        
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-number">{stats['total_items']}</div>
                <div>Total Items</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" style="color: #f44336;">{stats['duplicates']}</div>
                <div>Duplicate IDs</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" style="color: #ff9800;">{stats['quality_issues']}</div>
                <div>Quality Issues</div>
            </div>
            <div class="stat-item">
                <div class="stat-number" style="color: #e91e63;">{stats['processing_errors']}</div>
                <div>Processing Errors</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{stats['missing_ids']}</div>
                <div>Missing IDs</div>
            </div>
        </div>
    </div>
    
    <div class="table-container">
        <div class="scroll-hint" style="text-align: center; padding: 10px; background: #f8f9fa; color: #666; font-size: 0.9rem; border-bottom: 1px solid #dee2e6;">
            💡 <strong>Tip:</strong> Scroll horizontally to see all columns
        </div>
        <table>
            <thead>
                <tr>
                    <th>Directory</th>
                    <th>ID Number</th>
                    <th>Front Image</th>
                    <th>Back Image</th>
                    <th>Extraction Notes</th>
                    <th>Handwritten Notes</th>
                    <th>Printed Labels</th>
                    <th>Addresses</th>
                    <th>Processed At</th>
                    <th>Flags</th>
                </tr>
            </thead>
            <tbody>
"""
    
    # Add data rows
    for row in data_rows:
        # Determine row class based on flags
        row_classes = []
        if 'duplicate_id' in row['flags']:
            row_classes.append('row-duplicate')
        if 'quality_issue' in row['flags']:
            row_classes.append('row-quality-issue')
        if row['has_error']:
            row_classes.append('row-error')
        
        row_class = ' '.join(row_classes)
        
        # Create flag badges
        flag_badges = ''
        for flag in row['flags']:
            if flag == 'duplicate_id':
                flag_badges += '<span class="flag-badge flag-duplicate">DUPLICATE</span>'
            elif flag == 'quality_issue':
                flag_badges += '<span class="flag-badge flag-quality">QUALITY</span>'
            elif flag == 'processing_error':
                flag_badges += '<span class="flag-badge flag-error">ERROR</span>'
        
        # Truncate long text fields with tooltips
        extraction_notes = create_tooltip_cell(row['extraction_notes'], 60)
        handwritten_notes = create_tooltip_cell(row['handwritten_notes'], 30)
        printed_labels = create_tooltip_cell(row['printed_labels'], 40)
        addresses = create_tooltip_cell(row['addresses'], 30)
        
        html_content += f"""
                <tr class="{row_class}">
                    <td><strong>{row['directory']}</strong></td>
                    <td><strong>{row['id_number']}</strong></td>
                    <td class="image-path">{row['front_image_path']}</td>
                    <td class="image-path">{row['back_image_path']}</td>
                    <td class="notes-cell">{extraction_notes}</td>
                    <td class="long-text-cell">{handwritten_notes}</td>
                    <td class="long-text-cell">{printed_labels}</td>
                    <td class="long-text-cell">{addresses}</td>
                    <td>{row['processed_at']}</td>
                    <td>{flag_badges}</td>
                </tr>
        """
    
    html_content += """
            </tbody>
        </table>
    </div>
    
    <div class="legend">
        <h3>🏷️ Legend</h3>
        <div class="legend-item">
            <div class="legend-color" style="background-color: #ffebee; border-left: 4px solid #f44336;"></div>
            <span><strong>Red rows:</strong> Duplicate ID numbers found</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background-color: #fff3e0; border-left: 4px solid #ff9800;"></div>
            <span><strong>Orange rows:</strong> Text quality issues (faint, unreadable, etc.)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background-color: #fce4ec; border-left: 4px solid #e91e63;"></div>
            <span><strong>Pink rows:</strong> Processing errors occurred</span>
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logging.info(f"✓ HTML table created: {output_path}")

def generate_summary_table(base_path: Path, output_dir: Path = None) -> Dict:
    """
    Main function to generate summary table in multiple formats.
    """
    if output_dir is None:
        output_dir = base_path
    
    output_dir.mkdir(exist_ok=True)
    
    # Generate data
    logging.info("Generating data table from JSON files...")
    data_rows, stats = generate_data_table(base_path)
    
    # Add generation timestamp
    from datetime import datetime
    stats['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create CSV table
    csv_path = output_dir / 'processing_summary.csv'
    create_csv_table(data_rows, csv_path)
    
    # Create HTML table  
    html_path = output_dir / 'processing_summary.html'
    create_html_table(data_rows, stats, html_path)
    
    # Return results
    return {
        'success': True,
        'data_rows': data_rows,
        'stats': stats,
        'csv_path': str(csv_path),
        'html_path': str(html_path),
        'total_items': stats['total_items'],
        'duplicates_found': stats['duplicates'],
        'quality_issues': stats['quality_issues'],
        'processing_errors': stats['processing_errors']
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate data table from processed images')
    parser.add_argument('path', help='Path to processed images directory')
    parser.add_argument('--output', help='Output directory (default: same as input)')
    
    args = parser.parse_args()
    
    base_path = Path(args.path)
    output_dir = Path(args.output) if args.output else base_path
    
    try:
        result = generate_summary_table(base_path, output_dir)
        
        print(f"\n{'='*60}")
        print(f"SUMMARY TABLE GENERATION COMPLETE")
        print(f"{'='*60}")
        print(f"Total items processed: {result['total_items']}")
        print(f"Duplicate IDs found: {result['duplicates_found']}")
        print(f"Quality issues flagged: {result['quality_issues']}")
        print(f"Processing errors: {result['processing_errors']}")
        print(f"\nFiles created:")
        print(f"  📊 CSV: {result['csv_path']}")
        print(f"  🌐 HTML: {result['html_path']}")
        
    except Exception as e:
        print(f"Error: {e}")
        exit(1)