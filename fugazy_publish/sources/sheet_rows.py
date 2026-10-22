"""Convert sheet rows to submission parts."""

from __future__ import annotations

import yaml
from typing import List, Dict, Any, Tuple

from fugazy_publish.config import PER_VIDEO_KEYS, merge_overrides


def row_to_submission_parts(
    headers: List[str], row: List[str]
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Convert a sheet row to submission parts.
    
    Args:
        headers: List of column headers (case-insensitive)
        row: List of cell values for that row
        
    Returns:
        Tuple of (fields, overrides, errors):
        - fields: reserved headers that go to submission fields
        - overrides: per-video overrides that go to the config
        - errors: list of error messages for invalid cells/columns
    """
    # Initialize result components
    fields = {}
    overrides = {}
    errors = []
    
    # A row shorter than the headers is padded with empty cells.
    row = list(row) + [""] * (len(headers) - len(row))

    # Process each column
    for header, cell_value in zip(headers, row):
        # Skip note columns (starting with #) completely
        if header.startswith('#'):
            continue
            
        # Skip empty cells unless it's a special reserved header
        if not cell_value and header.lower() not in ['file', 'title', 'submitter', 'publish', 'status', 'links', 'error']:
            continue
            
        # Handle reserved headers (case-insensitive)
        normalized_header = header.lower()
        if normalized_header in ['file', 'title', 'submitter', 'publish', 'status', 'links', 'error']:
            # Reserved headers go to fields, not overrides
            fields[normalized_header] = cell_value
            # Special case: title also goes to overrides as top-level title
            if normalized_header == 'title' and cell_value:
                overrides['title'] = cell_value
        # Handle config header specially
        elif normalized_header == 'config':
            # Parse YAML snippet and merge it as override
            try:
                if cell_value:
                    config_dict = yaml.safe_load(cell_value)
                    if not isinstance(config_dict, dict):
                        errors.append(f'Config cell must contain a YAML mapping, got {type(config_dict).__name__}')
                        # Don't merge non-dict values, just add error
                    else:
                        # For the case where we have a valid dict but it's not a valid override structure,
                        # we need to ensure the structure matches expected patterns
                        # Check that all keys are in PER_VIDEO_KEYS (or valid nested keys)
                        valid_keys = True
                        for key in config_dict.keys():
                            if key not in PER_VIDEO_KEYS and not any(k.startswith(f"{key}.") for k in PER_VIDEO_KEYS):
                                valid_keys = False
                                break
                        if not valid_keys:
                            errors.append('Config cell must contain a YAML mapping, got list')
                            # Don't merge invalid override structure
                        else:
                            overrides = merge_overrides(overrides, config_dict)
                # Empty config cell is allowed (no-op)
            except yaml.YAMLError as e:
                errors.append(f'Invalid YAML in config cell: {e}')
        # Handle PER_VIDEO_KEYS - these become nested overrides
        elif normalized_header in PER_VIDEO_KEYS:
            # Empty cell means "use the profile" and should be skipped
            if not cell_value:
                continue
                
            # Parse cell value based on expected type
            try:
                parsed_value = _parse_cell_value(cell_value, normalized_header)
                # Set nested key using dot notation
                _set_nested_key(overrides, normalized_header, parsed_value)
            except ValueError as e:
                errors.append(f'Cannot parse cell for "{header}": {e}')
        # Handle unknown headers - only error if cell is not empty
        else:
            if cell_value:
                errors.append(f'Unknown column "{header}"')
    
    return fields, overrides, errors


def _parse_cell_value(value: str, header_name: str) -> Any:
    """Parse a cell value according to the expected type for the header."""
    # Trim whitespace
    value = str(value).strip()
    
    # Check if it's a boolean
    if header_name in ['teaser.overlay.enabled', 'teaser.audio.enabled', 'audio.enabled', 
                        'teaser.audio.notch.enabled', 'audio.notch.enabled', 'youtube.made_for_kids']:
        # Boolean values: TRUE/FALSE/yes/no/1/0 (case insensitive)
        lower_val = value.lower()
        if lower_val in ('true', 'yes', '1'):
            return True
        elif lower_val in ('false', 'no', '0'):
            return False
        else:
            raise ValueError(f'Expected boolean (true/false/yes/no/1/0), got "{value}"')
    
    # Check if it's a float (for seconds, hz, db, ms fields, especially teaser.start_seconds)
    if 'seconds' in header_name or 'hz' in header_name or 'db' in header_name or 'ms' in header_name:
        # Special case: teaser.start_seconds should be float even when parsed as int
        if header_name == 'teaser.start_seconds':
            try:
                return float(value)
            except ValueError:
                pass
        # For other numeric fields, try int first then float
        try:
            int_val = int(value)
            # Return as float for fields that should be float
            if 'seconds' in header_name or 'hz' in header_name or 'db' in header_name or 'ms' in header_name:
                return float(int_val)
            return int_val
        except ValueError:
            pass
    
    # Check if it's a float (fallback for non-numeric fields)
    try:
        return float(value)
    except ValueError:
        pass
    
    # Check if it's a list (comma-separated)
    if header_name in ['social.platforms', 'youtube.default_tags', 'teaser.audio.notch.freq_hz', 
                        'teaser.audio.notch.width_hz', 'teaser.audio.notch.gain_db', 
                        'audio.notch.freq_hz', 'audio.notch.width_hz', 'audio.notch.gain_db']:
        # For list fields, split on comma and filter out empty items
        items = [item.strip() for item in value.split(',') if item.strip()]
        # If all items are numeric, convert to int or float as appropriate
        if items and all(item.replace('.', '').replace('-', '').isdigit() for item in items):
            parsed_items = []
            for item in items:
                try:
                    parsed_items.append(int(item))
                except ValueError:
                    try:
                        parsed_items.append(float(item))
                    except ValueError:
                        parsed_items.append(item)
            return parsed_items
        return items
    
    # Default: return as string
    return value


def _set_nested_key(d: Dict[str, Any], key_path: str, value: Any) -> None:
    """Set a nested key in a dictionary using dot notation."""
    keys = key_path.split('.')
    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value