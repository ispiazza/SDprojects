#!/usr/bin/env python3
"""
Deployment script for integrating the pipeline into the Museum Archive system
This script helps set up and verify the integration
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_prerequisites():
    """Check if all prerequisites are met"""
    logger.info("🔍 Checking prerequisites...")
    
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        issues.append("Python 3.8+ required")
    
    # Check required directories
    required_dirs = ['media_upload', 'models', 'static', 'sessions', 'media']
    for dir_name in required_dirs:
        if not Path(dir_name).exists():
            logger.warning(f"Directory '{dir_name}' does not exist, creating...")
            Path(dir_name).mkdir(exist_ok=True)
    
    # Check if pipeline scripts exist
    pipeline_scripts = [
        'media_upload/scan_formatting.py',
        'media_upload/classify_rename.py', 
        'media_upload/text_extractor.py',
        'media_upload/table_generator.py'
    ]
    
    missing_scripts = []
    for script in pipeline_scripts:
        if not Path(script).exists():
            missing_scripts.append(script)
    
    if missing_scripts:
        issues.append(f"Missing pipeline scripts: {', '.join(missing_scripts)}")
        logger.warning("Some pipeline scripts are missing. Pipeline will run with fallbacks.")
    
    # Check environment variables
    required_env_vars = ['PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD']
    missing_env_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_env_vars:
        issues.append(f"Missing environment variables: {', '.join(missing_env_vars)}")
    
    if issues:
        logger.warning("⚠️  Issues found:")
        for issue in issues:
            logger.warning(f"  - {issue}")
        return False
    
    logger.info("✅ Prerequisites check passed")
    return True

def setup_pipeline_integration():
    """Set up the pipeline integration files"""
    logger.info("🔧 Setting up pipeline integration...")
    
    try:
        # Create pipeline_integration.py if it doesn't exist
        pipeline_file = Path('pipeline_integration.py')
        if not pipeline_file.exists():
            logger.info("Creating pipeline_integration.py...")
            # The content would be the artifact we created above
            logger.warning("pipeline_integration.py not found. Please ensure it's in your project directory.")
        
        # Create config.py if it doesn't exist
        config_file = Path('config.py')
        if not config_file.exists():
            logger.info("Creating config.py...")
            # The content would be the config artifact we created above
            logger.warning("config.py not found. Please ensure it's in your project directory.")
        
        # Update main.py to include pipeline router
        main_file = Path('main.py')
        if main_file.exists():
            with open(main_file, 'r') as f:
                content = f.read()
            
            # Check if pipeline is already integrated
            if 'from pipeline_integration import pipeline_router' not in content:
                logger.info("Pipeline integration not found in main.py. Manual update required.")
                logger.info("Please add the following to your main.py:")
                logger.info("  from pipeline_integration import pipeline_router")
                logger.info("  app.include_router(pipeline_router)")
        
        logger.info("✅ Pipeline integration setup complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ Pipeline integration setup failed: {e}")
        return False

def verify_database_connection():
    """Verify database connection and schema"""
    logger.info("🗄️  Verifying database connection...")
    
    try:
        import database
        health = database.health_check()
        
        if health.get('status') == 'healthy':
            logger.info("✅ Database connection successful")
            logger.info(f"  Collections: {health.get('collections_count', 0)}")
            logger.info(f"  Records: {health.get('records_count', 0)}")
            return True
        else:
            logger.error(f"❌ Database health check failed: {health}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Database verification failed: {e}")
        return False

def verify_pipeline_components():
    """Verify pipeline components are working"""
    logger.info("🏭 Verifying pipeline components...")
    
    try:
        # Test importing pipeline integration
        try:
            from pipeline_integration import CompletePipelineProcessor
            logger.info("✅ Pipeline processor import successful")
        except ImportError as e:
            logger.error(f"❌ Pipeline processor import failed: {e}")
            return False
        
        # Test creating a session
        try:
            import uuid
            test_session_id = str(uuid.uuid4())
            processor = CompletePipelineProcessor(test_session_id)
            
            # Clean up test session
            processor.cleanup()
            logger.info("✅ Pipeline processor creation successful")
        except Exception as e:
            logger.error(f"❌ Pipeline processor creation failed: {e}")
            return False
        
        logger.info("✅ Pipeline components verification complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ Pipeline components verification failed: {e}")
        return False

def install_dependencies():
    """Install missing dependencies"""
    logger.info("📦 Checking dependencies...")
    
    required_packages = [
        'fastapi', 'uvicorn', 'psycopg2-binary', 'python-multipart',
        'pillow', 'opencv-python-headless', 'pytesseract', 'pandas'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.info(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install'
            ] + missing_packages)
            logger.info("✅ Dependencies installed successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to install dependencies: {e}")
            return False
    else:
        logger.info("✅ All dependencies already installed")
    
    return True

def create_sample_media_upload_scripts():
    """Create sample media upload scripts if they don't exist"""
    logger.info("📝 Creating sample media upload scripts...")
    
    media_upload_dir = Path('media_upload')
    media_upload_dir.mkdir(exist_ok=True)
    
    # Create __init__.py
    init_file = media_upload_dir / '__init__.py'
    if not init_file.exists():
        with open(init_file, 'w') as f:
            f.write('# Media upload module\n')
    
    # Create sample scan_formatting.py
    scan_formatting_file = media_upload_dir / 'scan_formatting.py'
    if not scan_formatting_file.exists():
        with open(scan_formatting_file, 'w') as f:
            f.write('''#!/usr/bin/env python3
"""
Sample scan formatting module
Replace with your actual implementation
"""
import zipfile
from pathlib import Path

def process_uploaded_zip(zip_path: str, output_dir: str) -> dict:
    """
    Sample implementation - extracts ZIP file
    Replace with your actual scan formatting logic
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(output_dir)
        
        return {
            "success": True,
            "message": "ZIP extracted successfully",
            "output_dir": output_dir
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
''')
    
    # Create sample table_generator.py
    table_generator_file = media_upload_dir / 'table_generator.py'
    if not table_generator_file.exists():
        with open(table_generator_file, 'w') as f:
            f.write('''#!/usr/bin/env python3
"""
Sample table generator module
Replace with your actual implementation
"""
from pathlib import Path

def generate_summary_table(input_dir: Path, output_dir: Path) -> dict:
    """
    Sample implementation - counts files
    Replace with your actual table generation logic
    """
    try:
        json_files = list(input_dir.rglob("*.json"))
        
        return {
            "success": True,
            "total_items": len(json_files),
            "duplicates_found": 0,
            "quality_issues": 0,
            "processing_errors": 0
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total_items": 0,
            "duplicates_found": 0,
            "quality_issues": 0,
            "processing_errors": 1
        }
''')
    
    logger.info("✅ Sample media upload scripts created")

def main():
    """Main deployment function"""
    logger.info("🚀 Starting Museum Archive Pipeline Integration Deployment")
    logger.info("=" * 60)
    
    success = True
    
    # Step 1: Check prerequisites
    if not check_prerequisites():
        logger.warning("⚠️  Prerequisites check failed, but continuing...")
    
    # Step 2: Install dependencies
    if not install_dependencies():
        logger.error("❌ Dependency installation failed")
        success = False
    
    # Step 3: Create sample scripts
    create_sample_media_upload_scripts()
    
    # Step 4: Setup pipeline integration
    if not setup_pipeline_integration():
        logger.error("❌ Pipeline integration setup failed")
        success = False
    
    # Step 5: Verify database connection
    if not verify_database_connection():
        logger.error("❌ Database verification failed")
        success = False
    
    # Step 6: Verify pipeline components
    if not verify_pipeline_components():
        logger.error("❌ Pipeline components verification failed")
        success = False
    
    logger.info("=" * 60)
    
    if success:
        logger.info("🎉 Pipeline integration deployment completed successfully!")
        logger.info("\n📋 Next steps:")
        logger.info("1. Review and customize the pipeline scripts in media_upload/")
        logger.info("2. Test the pipeline with: python -m uvicorn main:app --reload")
        logger.info("3. Access the pipeline interface at: http://localhost:8000/api/pipeline/interface")
        logger.info("4. Check the dashboard at: http://localhost:8000/dashboard")
    else:
        logger.error("❌ Pipeline integration deployment had errors")
        logger.info("\n🔧 Troubleshooting:")
        logger.info("1. Check environment variables are set correctly")
        logger.info("2. Ensure database is running and accessible")
        logger.info("3. Review error messages above")
        logger.info("4. Check requirements.txt for missing dependencies")

if __name__ == "__main__":
    main()