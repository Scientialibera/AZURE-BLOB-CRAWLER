"""
Azure File Processing Microservice - Entry Point

This file serves as the main entry point for the Azure File Processing Microservice.

For development purposes, this file redirects to the new modular main.py file.

- config/: Configuration and settings
- utils/: Utility functions (retry logic, chunking)
- azure/: Azure client implementations
- processing/: File processing and document handling
- services/: Service Bus and messaging
- api/: HTTP API handlers
- main.py: Application orchestration and startup
"""

import logging
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


if __name__ == '__main__':
    """
    Main entry point that redirects to the new modular architecture
    """
    
    # Debug: Check Python path and installed packages
    logger.info(f"Python path: {sys.path}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    # Test critical imports before proceeding
    try:
        import azure.identity
        logger.info("azure.identity import: SUCCESS")
    except ImportError as e:
        logger.error(f"azure.identity import: FAILED - {e}")
    
    try:
        import aiohttp
        logger.info("aiohttp import: SUCCESS")
    except ImportError as e:
        logger.error(f"aiohttp import: FAILED - {e}")
    
    # Import and run the new main application
    try:
        from main import main
        import asyncio
        asyncio.run(main())
    except ImportError as e:
        logger.error(f"Failed to import new main module: {e}")
        logger.error("Please ensure all dependencies are installed and modules are properly structured")
        
        # Additional debugging
        logger.error("Attempting to list installed packages...")
        try:
            import pkg_resources
            installed_packages = [d.project_name for d in pkg_resources.working_set]
            logger.error(f"Installed packages: {sorted(installed_packages)}")
        except Exception as pkg_error:
            logger.error(f"Could not list packages: {pkg_error}")
        
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)
