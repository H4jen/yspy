#!/usr/bin/env python3
"""
Data validation module for remote short selling data.

Provides comprehensive validation to ensure data integrity:
- Freshness checks (reject stale data)
- Structure validation (required fields, types)
- Value validation (reasonable ranges, valid dates)
- Corruption detection (suspicious changes from previous data)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of data validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    stats: Dict[str, Any]
    
    def __str__(self) -> str:
        if self.is_valid:
            msg = "✓ Data validation passed"
            if self.warnings:
                msg += f" with {len(self.warnings)} warning(s)"
        else:
            msg = f"✗ Data validation failed with {len(self.errors)} error(s)"
        return msg
    
    def log_details(self, log_level: int = logging.INFO):
        """Log validation details."""
        logger.log(log_level, str(self))
        for error in self.errors:
            logger.error(f"  ERROR: {error}")
        for warning in self.warnings:
            logger.warning(f"  WARNING: {warning}")


class DataValidator:
    """
    Validates short selling data for correctness and freshness.
    
    Validation checks:
    1. Freshness: Data should not be too old
    2. Structure: Required fields must exist with correct types
    3. Values: Percentages, dates, etc. must be in valid ranges
    4. Consistency: Large changes from previous data are flagged
    """
    
    # Maximum age of data in hours before it's considered stale
    DEFAULT_MAX_AGE_HOURS = 48
    
    # Maximum percentage value (above this is likely an error)
    MAX_REASONABLE_PERCENTAGE = 50.0
    
    # Maximum change in percentage between updates (for corruption detection)
    MAX_PERCENTAGE_CHANGE = 20.0
    
    # Minimum expected positions (if below, might indicate fetch failure)
    MIN_EXPECTED_POSITIONS = 10
    
    # Maximum percentage of positions that can disappear (corruption detection)
    MAX_POSITION_LOSS_PERCENT = 50.0
    
    def __init__(
        self,
        max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
        strict_mode: bool = False,
        cache_dir: Optional[Path] = None
    ):
        """
        Initialize validator.
        
        Args:
            max_age_hours: Maximum age of data in hours
            strict_mode: If True, warnings become errors
            cache_dir: Directory for storing validation state
        """
        self.max_age_hours = max_age_hours
        self.strict_mode = strict_mode
        self.cache_dir = Path(cache_dir) if cache_dir else None
        
    def validate_positions_data(
        self,
        data: Dict,
        previous_data: Optional[Dict] = None
    ) -> ValidationResult:
        """
        Validate short positions data.
        
        Args:
            data: Current data to validate
            previous_data: Previous valid data for comparison (optional)
            
        Returns:
            ValidationResult with status and details
        """
        errors = []
        warnings = []
        stats = {}
        
        # 1. Check basic structure
        struct_errors, struct_warnings = self._validate_structure(data)
        errors.extend(struct_errors)
        warnings.extend(struct_warnings)
        
        if struct_errors:
            # Can't proceed with other checks if structure is invalid
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                stats={'validation_stopped_at': 'structure'}
            )
        
        # 2. Check freshness
        fresh_errors, fresh_warnings, age_hours = self._validate_freshness(data)
        errors.extend(fresh_errors)
        warnings.extend(fresh_warnings)
        stats['data_age_hours'] = age_hours
        
        # 3. Check position values
        positions = data.get('positions', [])
        value_errors, value_warnings, value_stats = self._validate_values(positions)
        errors.extend(value_errors)
        warnings.extend(value_warnings)
        stats.update(value_stats)
        
        # 4. Check for data corruption (comparison with previous)
        if previous_data:
            corrupt_errors, corrupt_warnings, corrupt_stats = self._detect_corruption(
                data, previous_data
            )
            errors.extend(corrupt_errors)
            warnings.extend(corrupt_warnings)
            stats.update(corrupt_stats)
        
        # In strict mode, warnings become errors
        if self.strict_mode:
            errors.extend(warnings)
            warnings = []
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            stats=stats
        )
    
    def _validate_structure(self, data: Dict) -> Tuple[List[str], List[str]]:
        """Validate data structure and types."""
        errors = []
        warnings = []
        
        # Required top-level fields
        required_fields = ['positions', 'last_updated']
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: '{field}'")
        
        if errors:
            return errors, warnings
        
        # Validate 'positions' is a list
        if not isinstance(data['positions'], list):
            errors.append(f"'positions' must be a list, got {type(data['positions']).__name__}")
            return errors, warnings
        
        # Validate 'last_updated' is a valid ISO timestamp
        try:
            datetime.fromisoformat(data['last_updated'].replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            errors.append(f"'last_updated' is not a valid ISO timestamp: {data.get('last_updated')}")
        
        # Validate each position
        required_position_fields = [
            ('ticker', str),
            ('company_name', str),
            ('position_percentage', (int, float)),
            ('position_date', str),
            ('market', str),
        ]
        
        for i, pos in enumerate(data['positions']):
            if not isinstance(pos, dict):
                errors.append(f"Position {i} is not a dictionary")
                continue
                
            for field, expected_type in required_position_fields:
                if field not in pos:
                    errors.append(f"Position {i} missing required field: '{field}'")
                elif not isinstance(pos[field], expected_type):
                    errors.append(
                        f"Position {i} field '{field}' has wrong type: "
                        f"expected {expected_type}, got {type(pos[field]).__name__}"
                    )
            
            # Validate individual_holders if present
            if 'individual_holders' in pos:
                if pos['individual_holders'] is not None:
                    if not isinstance(pos['individual_holders'], list):
                        errors.append(f"Position {i} 'individual_holders' must be a list")
                    else:
                        for j, holder in enumerate(pos['individual_holders']):
                            if not isinstance(holder, dict):
                                errors.append(f"Position {i} holder {j} is not a dictionary")
                            elif 'holder_name' not in holder:
                                errors.append(f"Position {i} holder {j} missing 'holder_name'")
                            elif 'position_percentage' not in holder:
                                errors.append(f"Position {i} holder {j} missing 'position_percentage'")
        
        return errors, warnings
    
    def _validate_freshness(self, data: Dict) -> Tuple[List[str], List[str], Optional[float]]:
        """Validate data is not too old."""
        errors = []
        warnings = []
        age_hours = None
        
        try:
            last_updated = datetime.fromisoformat(
                data['last_updated'].replace('Z', '+00:00')
            )
            # Remove timezone info for comparison if present
            if last_updated.tzinfo is not None:
                last_updated = last_updated.replace(tzinfo=None)
            
            age = datetime.now() - last_updated
            age_hours = age.total_seconds() / 3600
            
            if age_hours > self.max_age_hours:
                errors.append(
                    f"Data is too old: {age_hours:.1f} hours "
                    f"(max allowed: {self.max_age_hours} hours)"
                )
            elif age_hours > self.max_age_hours / 2:
                warnings.append(
                    f"Data is getting stale: {age_hours:.1f} hours old"
                )
            
            # Also check for future timestamps (clock skew)
            if last_updated > datetime.now() + timedelta(hours=1):
                errors.append(
                    f"Data timestamp is in the future: {data['last_updated']}"
                )
                
        except Exception as e:
            errors.append(f"Could not parse timestamp: {e}")
        
        return errors, warnings, age_hours
    
    def _validate_values(self, positions: List[Dict]) -> Tuple[List[str], List[str], Dict]:
        """Validate position values are reasonable."""
        errors = []
        warnings = []
        stats = {
            'total_positions': len(positions),
            'positions_checked': 0,
            'positions_with_issues': 0
        }
        
        # CRITICAL: Reject empty or near-empty data as this indicates a fetch failure
        if len(positions) == 0:
            errors.append(
                "No positions found - this indicates a data fetch failure. "
                "Rejecting to prevent data corruption."
            )
        elif len(positions) < self.MIN_EXPECTED_POSITIONS:
            warnings.append(
                f"Only {len(positions)} positions found "
                f"(expected at least {self.MIN_EXPECTED_POSITIONS})"
            )
        
        for i, pos in enumerate(positions):
            stats['positions_checked'] += 1
            has_issue = False
            
            # Check percentage is reasonable
            pct = pos.get('position_percentage', 0)
            if not isinstance(pct, (int, float)):
                errors.append(f"Position {i} ({pos.get('ticker', 'unknown')}): "
                             f"percentage is not a number: {pct}")
                has_issue = True
            elif pct < 0:
                errors.append(f"Position {i} ({pos.get('ticker', 'unknown')}): "
                             f"negative percentage: {pct}")
                has_issue = True
            elif pct > self.MAX_REASONABLE_PERCENTAGE:
                warnings.append(f"Position {i} ({pos.get('ticker', 'unknown')}): "
                               f"unusually high percentage: {pct}%")
                has_issue = True
            elif pct == 0:
                warnings.append(f"Position {i} ({pos.get('ticker', 'unknown')}): "
                               f"zero percentage")
                has_issue = True
            
            # Check date is reasonable
            date_str = pos.get('position_date', '')
            if date_str:
                try:
                    # Try common date formats
                    pos_date = None
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d']:
                        try:
                            pos_date = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if pos_date:
                        # Check date is not too old (> 1 year)
                        if pos_date < datetime.now() - timedelta(days=365):
                            warnings.append(
                                f"Position {i} ({pos.get('ticker', 'unknown')}): "
                                f"position date is very old: {date_str}"
                            )
                            has_issue = True
                        # Check date is not in the future
                        elif pos_date > datetime.now() + timedelta(days=1):
                            errors.append(
                                f"Position {i} ({pos.get('ticker', 'unknown')}): "
                                f"position date is in the future: {date_str}"
                            )
                            has_issue = True
                except Exception:
                    pass  # Date parsing issues handled elsewhere
            
            # Validate individual holders sum
            if pos.get('individual_holders'):
                holders = pos['individual_holders']
                if holders:
                    holder_sum = sum(
                        h.get('position_percentage', 0) 
                        for h in holders 
                        if isinstance(h.get('position_percentage'), (int, float))
                    )
                    total_pct = pos.get('position_percentage', 0)
                    
                    # Allow some tolerance for rounding
                    if abs(holder_sum - total_pct) > 1.0:
                        warnings.append(
                            f"Position {i} ({pos.get('ticker', 'unknown')}): "
                            f"holder sum ({holder_sum:.2f}%) doesn't match "
                            f"total ({total_pct:.2f}%)"
                        )
                        has_issue = True
            
            if has_issue:
                stats['positions_with_issues'] += 1
        
        return errors, warnings, stats
    
    def _detect_corruption(
        self,
        current_data: Dict,
        previous_data: Dict
    ) -> Tuple[List[str], List[str], Dict]:
        """
        Detect potential data corruption by comparing with previous data.
        
        Checks for:
        - Sudden large drops in number of positions
        - Sudden large changes in individual position percentages
        - Companies disappearing that should still be present
        """
        errors = []
        warnings = []
        stats = {}
        
        current_positions = current_data.get('positions', [])
        previous_positions = previous_data.get('positions', [])
        
        # Build lookup by company name
        current_by_company = {
            pos.get('company_name', '').lower(): pos 
            for pos in current_positions
        }
        previous_by_company = {
            pos.get('company_name', '').lower(): pos 
            for pos in previous_positions
        }
        
        # Check for large drop in position count
        if previous_positions:
            prev_count = len(previous_positions)
            curr_count = len(current_positions)
            
            if prev_count > 0:
                drop_percent = ((prev_count - curr_count) / prev_count) * 100
                stats['position_count_change'] = curr_count - prev_count
                stats['position_count_change_percent'] = -drop_percent
                
                if drop_percent > self.MAX_POSITION_LOSS_PERCENT:
                    errors.append(
                        f"Suspicious drop in position count: "
                        f"{prev_count} -> {curr_count} ({drop_percent:.1f}% loss)"
                    )
                elif drop_percent > self.MAX_POSITION_LOSS_PERCENT / 2:
                    warnings.append(
                        f"Significant drop in position count: "
                        f"{prev_count} -> {curr_count} ({drop_percent:.1f}% loss)"
                    )
        
        # Check for large changes in individual positions
        large_changes = []
        for company, prev_pos in previous_by_company.items():
            if company in current_by_company:
                curr_pos = current_by_company[company]
                prev_pct = prev_pos.get('position_percentage', 0)
                curr_pct = curr_pos.get('position_percentage', 0)
                
                change = abs(curr_pct - prev_pct)
                if change > self.MAX_PERCENTAGE_CHANGE:
                    large_changes.append({
                        'company': prev_pos.get('company_name', company),
                        'previous': prev_pct,
                        'current': curr_pct,
                        'change': change
                    })
        
        stats['large_percentage_changes'] = len(large_changes)
        
        if large_changes:
            if len(large_changes) > len(previous_positions) * 0.3:
                # More than 30% of positions have large changes - suspicious
                errors.append(
                    f"Too many positions with large percentage changes: "
                    f"{len(large_changes)} positions changed by more than "
                    f"{self.MAX_PERCENTAGE_CHANGE}%"
                )
            else:
                for change in large_changes[:5]:  # Log first 5
                    warnings.append(
                        f"Large change for {change['company']}: "
                        f"{change['previous']:.2f}% -> {change['current']:.2f}% "
                        f"(Δ{change['change']:.2f}%)"
                    )
        
        # Check for companies that disappeared but had significant positions
        disappeared = []
        for company, prev_pos in previous_by_company.items():
            if company not in current_by_company:
                prev_pct = prev_pos.get('position_percentage', 0)
                if prev_pct >= 5.0:  # Only flag significant positions
                    disappeared.append({
                        'company': prev_pos.get('company_name', company),
                        'percentage': prev_pct
                    })
        
        stats['disappeared_positions'] = len(disappeared)
        
        for d in disappeared[:5]:  # Log first 5
            warnings.append(
                f"Position disappeared: {d['company']} "
                f"(had {d['percentage']:.2f}% short interest)"
            )
        
        return errors, warnings, stats
    
    def validate_and_save(
        self,
        data: Dict,
        output_path: Path,
        previous_data_path: Optional[Path] = None
    ) -> Tuple[bool, ValidationResult]:
        """
        Validate data and save only if valid.
        
        Args:
            data: Data to validate
            output_path: Path to save validated data
            previous_data_path: Path to previous data file for comparison
            
        Returns:
            (success, ValidationResult)
        """
        # Load previous data if available
        previous_data = None
        if previous_data_path and previous_data_path.exists():
            try:
                with open(previous_data_path) as f:
                    previous_data = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load previous data for comparison: {e}")
        
        # Validate
        result = self.validate_positions_data(data, previous_data)
        result.log_details()
        
        if result.is_valid:
            # Save validated data
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"✓ Saved validated data to {output_path}")
            
            # Also save a backup of this good data for future comparison
            if self.cache_dir:
                backup_path = self.cache_dir / "last_valid_data.json"
                with open(backup_path, 'w') as f:
                    json.dump(data, f, indent=2)
            
            return True, result
        else:
            logger.error(f"✗ Data validation failed, not saving corrupted data")
            return False, result


def validate_position_dict(position: Dict) -> Tuple[bool, List[str]]:
    """
    Quick validation for a single position dictionary.
    
    Args:
        position: Position dictionary to validate
        
    Returns:
        (is_valid, error_messages)
    """
    errors = []
    
    required_fields = ['ticker', 'company_name', 'position_percentage', 'market']
    for field in required_fields:
        if field not in position:
            errors.append(f"Missing required field: {field}")
    
    if 'position_percentage' in position:
        pct = position['position_percentage']
        if not isinstance(pct, (int, float)):
            errors.append(f"position_percentage must be a number, got {type(pct).__name__}")
        elif pct < 0 or pct > 100:
            errors.append(f"position_percentage out of range: {pct}")
    
    return len(errors) == 0, errors


# Convenience functions for common validation scenarios

def validate_before_save(
    data: Dict,
    output_path: Path,
    max_age_hours: int = 48
) -> bool:
    """
    Simple validation before saving data.
    
    Args:
        data: Data to validate
        output_path: Where data will be saved
        max_age_hours: Maximum acceptable age
        
    Returns:
        True if data is valid and should be saved
    """
    validator = DataValidator(max_age_hours=max_age_hours)
    
    # Load previous data from output path for comparison
    previous_data = None
    if output_path.exists():
        try:
            with open(output_path) as f:
                previous_data = json.load(f)
        except:
            pass
    
    result = validator.validate_positions_data(data, previous_data)
    result.log_details()
    
    return result.is_valid


def validate_fetched_data(
    data: Dict,
    cache_dir: Path,
    strict: bool = False
) -> Tuple[bool, str]:
    """
    Validate data fetched from remote source.
    
    Args:
        data: Fetched data
        cache_dir: Cache directory (for loading previous valid data)
        strict: Use strict validation mode
        
    Returns:
        (is_valid, message)
    """
    validator = DataValidator(
        strict_mode=strict,
        cache_dir=cache_dir
    )
    
    # Try to load previous valid data
    previous_data = None
    last_valid_path = cache_dir / "last_valid_data.json"
    if last_valid_path.exists():
        try:
            with open(last_valid_path) as f:
                previous_data = json.load(f)
        except:
            pass
    
    result = validator.validate_positions_data(data, previous_data)
    
    if result.is_valid:
        # Save as last valid data
        with open(last_valid_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        msg = f"Data validated: {result.stats.get('total_positions', 0)} positions"
        if result.warnings:
            msg += f" ({len(result.warnings)} warnings)"
        return True, msg
    else:
        msg = f"Validation failed: {'; '.join(result.errors[:3])}"
        if len(result.errors) > 3:
            msg += f" (+{len(result.errors) - 3} more errors)"
        return False, msg


if __name__ == "__main__":
    # Test the validator
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("Data Validator Test")
    print("=" * 60)
    
    # Test with sample data
    sample_data = {
        'last_updated': datetime.now().isoformat(),
        'positions': [
            {
                'ticker': 'ERIC-B.ST',
                'company_name': 'Ericsson B',
                'position_holder': 'Multiple',
                'position_percentage': 12.5,
                'position_date': '2026-02-01',
                'market': 'SE',
                'threshold_crossed': '0.5%',
                'individual_holders': [
                    {'holder_name': 'Hedge Fund A', 'position_percentage': 6.0, 'position_date': '2026-02-01'},
                    {'holder_name': 'Hedge Fund B', 'position_percentage': 6.5, 'position_date': '2026-02-01'},
                ]
            },
            {
                'ticker': 'SBB-B.ST',
                'company_name': 'SBB B',
                'position_holder': 'Multiple',
                'position_percentage': 25.0,
                'position_date': '2026-02-01',
                'market': 'SE',
                'threshold_crossed': '0.5%',
                'individual_holders': []
            }
        ]
    }
    
    validator = DataValidator(max_age_hours=48)
    result = validator.validate_positions_data(sample_data)
    
    print(f"\nResult: {result}")
    print(f"Stats: {result.stats}")
    
    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings:
            print(f"  - {w}")
    
    if result.errors:
        print("\nErrors:")
        for e in result.errors:
            print(f"  - {e}")
    
    # Test with invalid data
    print("\n" + "=" * 60)
    print("Testing with invalid data...")
    print("=" * 60)
    
    invalid_data = {
        'last_updated': (datetime.now() - timedelta(hours=72)).isoformat(),  # Too old
        'positions': [
            {
                'ticker': 'TEST.ST',
                'company_name': 'Test Company',
                'position_percentage': 150.0,  # Invalid percentage
                'position_date': '2099-01-01',  # Future date
                'market': 'SE',
            }
        ]
    }
    
    result = validator.validate_positions_data(invalid_data)
    print(f"\nResult: {result}")
    result.log_details()
