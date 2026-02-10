"""
Remote short selling data fetcher for yspy.

This module allows yspy to fetch short selling data from a remote server
where update_shorts_cron.py runs daily via cron.

Supports multiple protocols:
- Local filesystem (mounted network share, NFS, Samba)
- HTTP/HTTPS (static web server)
- SSH/SFTP (secure file transfer)
- S3-compatible storage (optional)
"""

import json
import logging
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# Try to import the data validator from remote_setup
try:
    # Add remote_setup to path
    remote_setup_path = Path(__file__).parent.parent / 'remote_setup'
    if remote_setup_path.exists():
        sys.path.insert(0, str(remote_setup_path))
    from data_validator import DataValidator, ValidationResult
    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False
    DataValidator = None
    ValidationResult = None

logger = logging.getLogger(__name__)


@dataclass
class RemoteDataConfig:
    """Configuration for remote data source."""
    
    # Protocol: 'file', 'http', 'ssh', 's3'
    protocol: str = 'file'
    
    # Location (depends on protocol)
    # - file: /path/to/shared/directory
    # - http: https://example.com/yspy_data
    # - ssh: user@server:/path/to/data
    # - s3: s3://bucket/path
    location: str = ''
    
    # Local cache directory
    cache_dir: Path = field(default_factory=lambda: Path('portfolio/remote_cache'))
    
    # Cache TTL (time-to-live) in hours
    cache_ttl_hours: int = 6
    
    # Overall fetch timeout in seconds (for all protocols)
    fetch_timeout: int = 15
    
    # SSH/SFTP settings (if protocol='ssh')
    ssh_key_path: Optional[str] = None
    ssh_timeout: int = 10  # Connection timeout in seconds
    
    # HTTP settings (if protocol='http')
    http_timeout: int = 30
    http_verify_ssl: bool = True
    
    # Validation settings
    validate_data: bool = True  # Enable/disable data validation
    validation_max_age_hours: int = 48  # Maximum acceptable data age
    validation_strict: bool = False  # Strict mode: warnings become errors
    
    def __post_init__(self):
        """Ensure cache directory exists."""
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


class RemoteShortDataFetcher:
    """Fetches short selling data from remote server."""
    
    def __init__(self, config: RemoteDataConfig):
        """
        Initialize fetcher.
        
        Args:
            config: Configuration for remote data source
        """
        self.config = config
        self.cache_current = config.cache_dir / "short_positions_current.json"
        self.cache_historical = config.cache_dir / "short_positions_historical.json"
        self.cache_meta = config.cache_dir / "short_positions_meta.json"
        self.cache_last_valid = config.cache_dir / "last_valid_data.json"
        
        # Initialize validator if available and enabled
        self.validator = None
        if config.validate_data and HAS_VALIDATOR:
            self.validator = DataValidator(
                max_age_hours=config.validation_max_age_hours,
                strict_mode=config.validation_strict,
                cache_dir=config.cache_dir
            )
            logger.info("Data validation enabled")
        elif config.validate_data and not HAS_VALIDATOR:
            logger.warning("Data validation requested but validator not available")
    
    def fetch_data(self, force_refresh: bool = False) -> Tuple[bool, Optional[Dict]]:
        """
        Fetch short selling data from remote source.
        
        Args:
            force_refresh: Force refresh even if cache is valid
            
        Returns:
            (success, data_dict) where data_dict contains:
            - positions: List of position dicts
            - last_updated: ISO timestamp
            - metadata: Update metadata
        """
        try:
            # Check cache first
            if not force_refresh and self._is_cache_valid():
                logger.debug("Using cached remote data")  # Changed from INFO to DEBUG to reduce log spam
                return True, self._load_cached_data()
            
            # Fetch from remote based on protocol
            logger.info(f"Fetching short data from remote ({self.config.protocol})...")
            
            if self.config.protocol == 'file':
                success = self._fetch_from_file()
            elif self.config.protocol == 'http':
                success = self._fetch_from_http()
            elif self.config.protocol == 'ssh':
                success = self._fetch_from_ssh()
            elif self.config.protocol == 's3':
                success = self._fetch_from_s3()
            else:
                logger.error(f"Unknown protocol: {self.config.protocol}")
                return False, None
            
            if success:
                logger.info("✓ Successfully fetched remote data")
                
                # Validate fetched data before using it
                fetched_data = self._load_cached_data()
                
                if self.validator:
                    validation_result = self._validate_fetched_data(fetched_data)
                    
                    if not validation_result.is_valid:
                        logger.error("✗ Fetched data failed validation")
                        validation_result.log_details(logging.ERROR)
                        
                        # Try to use last valid data instead
                        if self.cache_last_valid.exists():
                            logger.info("Using last valid data as fallback")
                            with open(self.cache_last_valid) as f:
                                return True, json.load(f)
                        
                        # No valid fallback available
                        logger.error("No valid fallback data available")
                        return False, None
                    else:
                        # Validation passed - save as last valid
                        if validation_result.warnings:
                            logger.warning(f"Data validated with {len(validation_result.warnings)} warning(s)")
                        else:
                            logger.info("✓ Data validation passed")
                        
                        # Save validated data as last known good
                        with open(self.cache_last_valid, 'w') as f:
                            json.dump(fetched_data, f, indent=2)
                
                return True, fetched_data
            else:
                logger.warning("Failed to fetch remote data, using cached if available")
                if self.cache_current.exists():
                    return True, self._load_cached_data()
                return False, None
                
        except Exception as e:
            logger.error(f"Error fetching remote data: {e}")
            # Try to use cached data as fallback
            if self.cache_current.exists():
                logger.info("Using cached data as fallback")
                return True, self._load_cached_data()
            return False, None
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if not self.cache_meta.exists():
            return False
        
        try:
            with open(self.cache_meta) as f:
                meta = json.load(f)
            
            last_update = datetime.fromisoformat(meta.get('last_update', ''))
            age = datetime.now() - last_update
            
            return age.total_seconds() < (self.config.cache_ttl_hours * 3600)
        except:
            return False
    
    def _validate_fetched_data(self, data: Dict) -> 'ValidationResult':
        """
        Validate fetched data before accepting it.
        
        Args:
            data: The fetched data to validate
            
        Returns:
            ValidationResult with validation status and details
        """
        if not self.validator:
            # No validator - create a dummy success result
            class DummyResult:
                is_valid = True
                errors = []
                warnings = []
                stats = {}
                def log_details(self, level=None): pass
            return DummyResult()
        
        # Load previous valid data for comparison
        previous_data = None
        if self.cache_last_valid.exists():
            try:
                with open(self.cache_last_valid) as f:
                    previous_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load last valid data for comparison: {e}")
        
        # Validate the fetched data
        return self.validator.validate_positions_data(data, previous_data)
    
    def _load_cached_data(self) -> Dict:
        """Load data from cache."""
        with open(self.cache_current) as f:
            current_data = json.load(f)
        
        with open(self.cache_meta) as f:
            meta_data = json.load(f)
        
        # Load historical if available
        historical_data = {}
        if self.cache_historical.exists():
            with open(self.cache_historical) as f:
                historical_data = json.load(f)
        
        return {
            'positions': current_data.get('positions', []),
            'last_updated': current_data.get('last_updated'),
            'update_source': current_data.get('update_source', 'remote'),
            'metadata': meta_data,
            'historical': historical_data
        }
    
    def _fetch_from_file(self) -> bool:
        """Fetch from local/mounted filesystem."""
        try:
            source_dir = Path(self.config.location)
            
            if not source_dir.exists():
                logger.error(f"Remote directory not found: {source_dir}")
                return False
            
            # Copy all files
            files = [
                'short_positions_current.json',
                'short_positions_historical.json',
                'short_positions_meta.json'
            ]
            
            for filename in files:
                source = source_dir / filename
                dest = self.config.cache_dir / filename
                
                if source.exists():
                    shutil.copy2(source, dest)
                    logger.debug(f"✓ Copied {filename}")
                else:
                    logger.warning(f"File not found: {source}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error fetching from file: {e}")
            return False
    
    def _fetch_from_http(self) -> bool:
        """Fetch from HTTP/HTTPS server."""
        try:
            import requests
            
            base_url = self.config.location.rstrip('/')
            files = [
                'short_positions_current.json',
                'short_positions_historical.json',
                'short_positions_meta.json'
            ]
            
            session = requests.Session()
            
            for filename in files:
                url = f"{base_url}/{filename}"
                
                response = session.get(
                    url,
                    timeout=self.config.http_timeout,
                    verify=self.config.http_verify_ssl
                )
                
                if response.status_code == 200:
                    dest = self.config.cache_dir / filename
                    with open(dest, 'wb') as f:
                        f.write(response.content)
                    logger.debug(f"✓ Downloaded {filename}")
                elif response.status_code == 404:
                    logger.warning(f"File not found: {filename}")
                else:
                    logger.error(f"HTTP {response.status_code} for {filename}")
                    return False
            
            return True
            
        except ImportError:
            logger.error("requests library not available for HTTP fetching")
            return False
        except Exception as e:
            logger.error(f"Error fetching from HTTP: {e}")
            return False
    
    def _fetch_from_ssh(self) -> bool:
        """Fetch from SSH/SFTP server."""
        try:
            import paramiko
            
            # Parse SSH location: user@host:/path
            parts = self.config.location.split(':')
            if len(parts) != 2:
                logger.error(f"Invalid SSH location: {self.config.location}")
                return False
            
            user_host, remote_path = parts
            if '@' in user_host:
                user, host = user_host.split('@')
            else:
                logger.error("SSH location must include user@host")
                return False
            
            # Connect via SFTP
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if self.config.ssh_key_path:
                ssh.connect(host, username=user, key_filename=self.config.ssh_key_path)
            else:
                ssh.connect(host, username=user)
            
            sftp = ssh.open_sftp()
            
            files = [
                'short_positions_current.json',
                'short_positions_historical.json',
                'short_positions_meta.json'
            ]
            
            for filename in files:
                remote_file = f"{remote_path}/{filename}"
                local_file = str(self.config.cache_dir / filename)
                
                try:
                    sftp.get(remote_file, local_file)
                    logger.debug(f"✓ Downloaded {filename}")
                except FileNotFoundError:
                    logger.warning(f"Remote file not found: {remote_file}")
            
            sftp.close()
            ssh.close()
            
            return True
            
        except ImportError:
            logger.error("paramiko library not available for SSH fetching")
            return False
        except Exception as e:
            logger.error(f"Error fetching from SSH: {e}")
            return False
    
    def _fetch_from_s3(self) -> bool:
        """Fetch from S3-compatible storage."""
        try:
            import boto3
            
            # Parse S3 location: s3://bucket/path
            if not self.config.location.startswith('s3://'):
                logger.error(f"Invalid S3 location: {self.config.location}")
                return False
            
            location = self.config.location[5:]  # Remove 's3://'
            parts = location.split('/', 1)
            bucket = parts[0]
            prefix = parts[1] if len(parts) > 1 else ''
            
            s3 = boto3.client('s3')
            
            files = [
                'short_positions_current.json',
                'short_positions_historical.json',
                'short_positions_meta.json'
            ]
            
            for filename in files:
                s3_key = f"{prefix}/{filename}" if prefix else filename
                local_file = str(self.config.cache_dir / filename)
                
                try:
                    s3.download_file(bucket, s3_key, local_file)
                    logger.debug(f"✓ Downloaded {filename} from S3")
                except Exception as e:
                    logger.warning(f"Failed to download {filename}: {e}")
            
            return True
            
        except ImportError:
            logger.error("boto3 library not available for S3 fetching")
            return False
        except Exception as e:
            logger.error(f"Error fetching from S3: {e}")
            return False
    
    def get_data_age(self) -> Optional[timedelta]:
        """Get age of cached data."""
        try:
            if not self.cache_meta.exists():
                return None
            
            with open(self.cache_meta) as f:
                meta = json.load(f)
            
            last_update = datetime.fromisoformat(meta.get('last_update', ''))
            return datetime.now() - last_update
        except:
            return None
    
    def get_status(self) -> Dict:
        """Get status of remote data."""
        age = self.get_data_age()
        
        status = {
            'has_cache': self.cache_current.exists(),
            'cache_valid': self._is_cache_valid(),
            'age_hours': age.total_seconds() / 3600 if age else None,
            'protocol': self.config.protocol,
            'location': self.config.location,
            'validation_enabled': self.validator is not None,
            'has_valid_backup': self.cache_last_valid.exists()
        }
        
        if self.cache_meta.exists():
            with open(self.cache_meta) as f:
                meta = json.load(f)
            status['metadata'] = meta
        
        return status


def load_remote_config(config_file: str = 'remote_config.json') -> RemoteDataConfig:
    """
    Load remote data configuration from file.
    
    Args:
        config_file: Path to config file
        
    Returns:
        RemoteDataConfig object
    """
    config_path = Path(config_file)
    
    if config_path.exists():
        with open(config_path) as f:
            config_dict = json.load(f)
        return RemoteDataConfig(**config_dict)
    else:
        # Return default config (local file)
        return RemoteDataConfig(
            protocol='file',
            location='/shared/yspy_data'  # Example default
        )


def create_example_config():
    """Create example remote_config.json file."""
    examples = {
        "file": {
            "protocol": "file",
            "location": "/mnt/shared/yspy_data",
            "cache_ttl_hours": 6,
            "comment": "For NFS/Samba mounted shares"
        },
        "http": {
            "protocol": "http",
            "location": "https://your-server.com/yspy_data",
            "cache_ttl_hours": 6,
            "http_timeout": 30,
            "http_verify_ssl": True,
            "comment": "For HTTP static file server"
        },
        "ssh": {
            "protocol": "ssh",
            "location": "user@server:/home/user/yspy_data",
            "ssh_key_path": "/home/user/.ssh/id_rsa",
            "cache_ttl_hours": 6,
            "comment": "For SSH/SFTP file transfer"
        }
    }
    
    with open('remote_config_examples.json', 'w') as f:
        json.dump(examples, f, indent=2)
    
    print("Created remote_config_examples.json with configuration examples")
