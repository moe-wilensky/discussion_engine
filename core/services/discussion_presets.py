"""
Discussion preset configurations.

Provides predefined discussion configurations and parameter validation.
"""

from typing import Dict, Tuple
from core.models import PlatformConfig


class DiscussionPreset:
    """Preset discussion configurations for quick setup."""
    
    PRESETS = {
        "quick_exchange": {
            "name": "Quick Exchange",
            "description": "Fast-paced, brief responses",
            "mrm_minutes": 5,
            "rtm": 1.5,
            "mrl_chars": 500,
            "explanation": "Responses in ~7 minutes, up to 500 characters"
        },
        "thoughtful_discussion": {
            "name": "Thoughtful Discussion",
            "description": "Balanced pace and depth",
            "mrm_minutes": 30,
            "rtm": 2.0,
            "mrl_chars": 2000,
            "explanation": "Responses in ~60 minutes, up to 2000 characters"
        },
        "deep_dive": {
            "name": "Deep Dive",
            "description": "Slow-paced, detailed exploration",
            "mrm_minutes": 120,
            "rtm": 2.5,
            "mrl_chars": 5000,
            "explanation": "Responses in ~5 hours, up to 5000 characters"
        }
    }
    
    @staticmethod
    def get_presets() -> Dict:
        """
        Return all presets with live previews.
        
        Returns:
            Dictionary of all available presets
        """
        return {
            preset_id: {
                **preset_data,
                "id": preset_id
            }
            for preset_id, preset_data in DiscussionPreset.PRESETS.items()
        }
    
    @staticmethod
    def preview_parameters(mrm: int, rtm: float, mrl: int) -> Dict:
        """
        Generate plain-language explanation of parameters.
        
        Args:
            mrm: Minimum Response Minutes
            rtm: Response Time Multiplier
            mrl: Maximum Response Length in characters
            
        Returns:
            Dictionary with preview text and estimated MRP
            
        Example:
            "If people respond every 30 minutes on average, 
             each person will have about 60 minutes to respond."
        """
        estimated_mrp = mrm * rtm
        
        # Convert minutes to readable format
        if estimated_mrp < 60:
            time_str = f"{int(estimated_mrp)} minutes"
        elif estimated_mrp < 1440:
            hours = estimated_mrp / 60
            time_str = f"{hours:.1f} hours"
        else:
            days = estimated_mrp / 1440
            time_str = f"{days:.1f} days"
        
        preview = (
            f"If people respond every {mrm} minutes on average, "
            f"each person will have about {time_str} to respond. "
            f"Responses can be up to {mrl} characters."
        )
        
        return {
            "preview": preview,
            "estimated_mrp_minutes": estimated_mrp
        }
    
    @staticmethod
    def validate_parameters(mrm: int, rtm: float, mrl: int, config: PlatformConfig) -> Tuple[bool, str]:
        """
        Validate parameters against platform min/max bounds.
        
        Args:
            mrm: Minimum Response Minutes
            rtm: Response Time Multiplier
            mrl: Maximum Response Length in characters
            config: PlatformConfig instance
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []
        
        # Validate MRM
        if mrm < config.mrm_min_minutes:
            errors.append(f"MRM must be at least {config.mrm_min_minutes} minutes")
        if mrm > config.mrm_max_minutes:
            errors.append(f"MRM cannot exceed {config.mrm_max_minutes} minutes")
        
        # Validate RTM
        if rtm < config.rtm_min:
            errors.append(f"RTM must be at least {config.rtm_min}")
        if rtm > config.rtm_max:
            errors.append(f"RTM cannot exceed {config.rtm_max}")
        
        # Validate MRL
        if mrl < config.mrl_min_chars:
            errors.append(f"MRL must be at least {config.mrl_min_chars} characters")
        if mrl > config.mrl_max_chars:
            errors.append(f"MRL cannot exceed {config.mrl_max_chars} characters")
        
        if errors:
            return False, "; ".join(errors)
        
        return True, ""
    
    @staticmethod
    def get_preset(preset_id: str) -> Dict:
        """
        Get a specific preset by ID.
        
        Args:
            preset_id: ID of the preset to retrieve
            
        Returns:
            Preset dictionary
            
        Raises:
            KeyError: If preset_id doesn't exist
        """
        if preset_id not in DiscussionPreset.PRESETS:
            raise KeyError(f"Preset '{preset_id}' not found")
        
        preset = DiscussionPreset.PRESETS[preset_id].copy()
        preset['id'] = preset_id
        return preset
