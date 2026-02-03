"""
Security and anti-abuse detection service.

Implements rate limiting and behavioral spam detection.
"""

from typing import Dict, List
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Q

from core.models import User, Invite


class AbuseDetectionService:
    """
    Detect and prevent abusive behavior.
    """
    
    # Rate limit configurations
    RATE_LIMITS = {
        'verification_requests': {
            'max_requests': 3,
            'window_seconds': 3600,  # 1 hour
            'key_prefix': 'rate_verification:'
        },
        'invite_sends': {
            'max_requests': 10,
            'window_seconds': 3600,  # 1 hour
            'key_prefix': 'rate_invite:'
        },
        'join_requests': {
            'max_requests': 5,
            'window_seconds': 3600,  # 1 hour
            'key_prefix': 'rate_join:'
        },
        'api_general': {
            'max_requests': 100,
            'window_seconds': 60,  # 1 minute
            'key_prefix': 'rate_api:'
        }
    }
    
    @classmethod
    def check_rate_limit(cls, identifier: str, action: str) -> bool:
        """
        Check if identifier is within rate limit for action.
        
        Args:
            identifier: Unique identifier (phone number, user ID, etc.)
            action: Action type (matches RATE_LIMITS keys)
            
        Returns:
            True if within rate limit, False if exceeded
        """
        if action not in cls.RATE_LIMITS:
            return True  # No limit configured
        
        config = cls.RATE_LIMITS[action]
        key = f"{config['key_prefix']}{identifier}"
        
        current_count = cache.get(key, 0)
        
        if current_count >= config['max_requests']:
            return False
        
        # Increment counter
        if current_count == 0:
            # First request, set with expiry
            cache.set(key, 1, timeout=config['window_seconds'])
        else:
            # Increment existing counter
            cache.incr(key)
        
        return True
    
    @classmethod
    def get_rate_limit_remaining(cls, identifier: str, action: str) -> int:
        """
        Get remaining requests for identifier/action.
        
        Args:
            identifier: Unique identifier
            action: Action type
            
        Returns:
            Number of remaining requests
        """
        if action not in cls.RATE_LIMITS:
            return 999  # Unlimited
        
        config = cls.RATE_LIMITS[action]
        key = f"{config['key_prefix']}{identifier}"
        
        current_count = cache.get(key, 0)
        return max(0, config['max_requests'] - current_count)
    
    @classmethod
    def detect_spam_pattern(cls, user: User) -> Dict:
        """
        Behavioral analysis for spam detection.
        
        Args:
            user: User to analyze
            
        Returns:
            Dictionary with spam analysis results
        """
        flags = []
        confidence = 0.0
        
        # Check 1: Too many rapid invites sent
        recent_cutoff = timezone.now() - timedelta(hours=24)
        recent_invites = Invite.objects.filter(
            inviter=user,
            sent_at__gte=recent_cutoff
        ).count()
        
        if recent_invites > 20:
            flags.append('excessive_invites_24h')
            confidence += 0.3
        
        # Check 2: High decline rate
        total_invites = Invite.objects.filter(inviter=user).count()
        if total_invites > 5:
            declined_invites = Invite.objects.filter(
                inviter=user,
                status='declined'
            ).count()
            
            decline_rate = declined_invites / total_invites
            if decline_rate > 0.5:  # More than 50% declined
                flags.append('high_decline_rate')
                confidence += 0.4
        
        # Check 3: No actual participation
        response_count = user.responses.count()
        if total_invites > 0 and response_count == 0:
            flags.append('no_participation')
            confidence += 0.5
        
        # Check 4: Invite formula violation
        if user.platform_invites_acquired > (user.platform_invites_used + user.platform_invites_banked):
            flags.append('invite_formula_violation_platform')
            confidence += 0.8
        
        if user.discussion_invites_acquired > (user.discussion_invites_used + user.discussion_invites_banked):
            flags.append('invite_formula_violation_discussion')
            confidence += 0.8
        
        # Check 5: Rapid account creation and invite sending
        account_age = timezone.now() - user.created_at
        if account_age < timedelta(hours=1) and recent_invites > 5:
            flags.append('new_account_spam')
            confidence += 0.6
        
        # Check 6: Multiple flagged responses
        # Note: Response flags would be tracked via ModerationAction
        # For now, skip this check or check moderation actions
        flagged_count = 0
        if flagged_count > 3:
            flags.append('multiple_flagged_responses')
            confidence += 0.5
        
        # Cap confidence at 1.0
        confidence = min(1.0, confidence)
        
        is_spam = confidence > 0.7
        
        return {
            'is_spam': is_spam,
            'confidence': round(confidence, 2),
            'flags': flags,
            'metrics': {
                'recent_invites_24h': recent_invites,
                'total_invites': total_invites,
                'response_count': response_count,
                'account_age_hours': account_age.total_seconds() / 3600
            }
        }
    
    @classmethod
    def flag_for_review(cls, user: User, reason: str) -> None:
        """
        Flag user for admin review.
        
        Args:
            user: User to flag
            reason: Reason for flagging
        """
        if not isinstance(user.behavioral_flags, dict):
            user.behavioral_flags = {}
        
        if 'admin_flags' not in user.behavioral_flags:
            user.behavioral_flags['admin_flags'] = []
        
        flag_entry = {
            'reason': reason,
            'flagged_at': timezone.now().isoformat(),
            'resolved': False
        }
        
        user.behavioral_flags['admin_flags'].append(flag_entry)
        user.save()
    
    @classmethod
    def is_flagged(cls, user: User) -> bool:
        """
        Check if user has unresolved flags.
        
        Args:
            user: User to check
            
        Returns:
            True if user has unresolved flags
        """
        if not isinstance(user.behavioral_flags, dict):
            return False
        
        admin_flags = user.behavioral_flags.get('admin_flags', [])
        return any(not flag.get('resolved', False) for flag in admin_flags)
