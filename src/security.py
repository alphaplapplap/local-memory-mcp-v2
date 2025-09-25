"""
Security utilities for the memory system
"""

import hashlib
import logging
import re
import secrets
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecurityValidator:
    """Input validation and sanitization utilities"""

    # Security patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|SCRIPT)\b)",
        r"(--|#|/\*|\*/)",
        r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
        r"(\b(OR|AND)\s+'.*'\s*=\s*'.*')",
        r"(\b(OR|AND)\s+\".*\"\s*=\s*\".*\")",
        r"(;|\||&)",
        r"(\b(SCRIPT|JAVASCRIPT|VBSCRIPT|ONLOAD|ONERROR)\b)",
    ]

    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"<iframe[^>]*>.*?</iframe>",
        r"<object[^>]*>.*?</object>",
        r"<embed[^>]*>.*?</embed>",
        r"<link[^>]*>.*?</link>",
        r"<meta[^>]*>.*?</meta>",
        r"javascript:",
        r"vbscript:",
        r"on\w+\s*=",
    ]

    @classmethod
    def sanitize_content(cls, content: str) -> str:
        """Sanitize content to prevent XSS and injection attacks"""
        if not isinstance(content, str):
            raise ValueError("Content must be a string")

        # Remove potential XSS patterns
        for pattern in cls.XSS_PATTERNS:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE | re.DOTALL)

        # Remove null bytes and control characters
        content = content.replace("\x00", "")
        content = "".join(
            char for char in content if ord(char) >= 32 or char in "\t\n\r"
        )

        # Limit length
        if len(content) > 10000:
            content = content[:10000]

        return content.strip()

    @classmethod
    def validate_domain(cls, domain: str) -> str:
        """Validate and sanitize domain name"""
        if not isinstance(domain, str):
            raise ValueError("Domain must be a string")

        # Remove dangerous characters
        domain = re.sub(r"[^a-zA-Z0-9_-]", "", domain)

        if not domain:
            raise ValueError("Domain cannot be empty after sanitization")

        if len(domain) > 50:
            raise ValueError("Domain name too long")

        return domain.lower()

    @classmethod
    def validate_metadata(cls, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize metadata"""
        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a dictionary")

        sanitized = {}
        for key, value in metadata.items():
            # Validate key
            if not isinstance(key, str):
                continue
            if len(key) > 100:
                continue

            # Sanitize key
            key = re.sub(r"[^a-zA-Z0-9_-]", "", key)
            if not key:
                continue

            # Validate value
            if isinstance(value, str):
                value = cls.sanitize_content(value)
                if len(value) > 1000:
                    value = value[:1000]
            elif isinstance(value, (int, float, bool)):
                pass  # These are safe
            elif isinstance(value, list):
                # Sanitize list items
                sanitized_list = []
                for item in value:
                    if isinstance(item, str):
                        sanitized_list.append(cls.sanitize_content(item))
                    elif isinstance(item, (int, float, bool)):
                        sanitized_list.append(item)
                value = sanitized_list
            else:
                continue  # Skip unsupported types

            sanitized[key] = value

        return sanitized

    @classmethod
    def check_sql_injection(cls, query: str) -> bool:
        """Check if query contains potential SQL injection patterns"""
        if not isinstance(query, str):
            return False

        query_upper = query.upper()
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, query_upper, re.IGNORECASE):
                logger.warning(f"Potential SQL injection detected: {query[:100]}")
                return True

        return False

    @classmethod
    def validate_domain_name(cls, domain: str) -> bool:
        """Validate that a domain name is safe to use.

        Args:
            domain: The domain name to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Use existing validate_domain method
            validated = cls.validate_domain(domain)
            return len(validated) > 0
        except (ValueError, TypeError):
            return False

    @classmethod
    def sanitize_input(cls, content: str) -> str:
        """Alias for sanitize_content for compatibility."""
        return cls.sanitize_content(content)


class CredentialManager:
    """Secure credential management"""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using secure method"""
        salt = secrets.token_hex(32)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 100000
        )
        return f"{salt}:{password_hash.hex()}"

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        try:
            salt, stored_hash = hashed_password.split(":")
            password_hash = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), salt.encode(), 100000
            )
            return password_hash.hex() == stored_hash
        except (ValueError, TypeError):
            return False

    @staticmethod
    def generate_api_key() -> str:
        """Generate secure API key"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_session_token() -> str:
        """Generate secure session token"""
        return secrets.token_urlsafe(64)


class RateLimiter:
    """Simple rate limiting implementation"""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # In production, use Redis or similar

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed for client"""
        import time

        current_time = time.time()

        # Clean old entries
        self.requests = {
            k: v
            for k, v in self.requests.items()
            if current_time - v["last_reset"] < self.window_seconds
        }

        # Check current client
        if client_id not in self.requests:
            self.requests[client_id] = {"count": 1, "last_reset": current_time}
            return True

        client_data = self.requests[client_id]

        # Reset if window expired
        if current_time - client_data["last_reset"] >= self.window_seconds:
            client_data["count"] = 1
            client_data["last_reset"] = current_time
            return True

        # Check if under limit
        if client_data["count"] < self.max_requests:
            client_data["count"] += 1
            return True

        return False


class SecurityAuditLogger:
    """Security event logging"""

    def __init__(self):
        self.logger = logging.getLogger("security_audit")
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_suspicious_activity(self, event_type: str, details: Dict[str, Any]):
        """Log suspicious security events"""
        self.logger.warning(f"SUSPICIOUS_ACTIVITY: {event_type} - {details}")

    def log_authentication_failure(self, client_id: str, reason: str):
        """Log authentication failures"""
        self.logger.warning(f"AUTH_FAILURE: {client_id} - {reason}")

    def log_rate_limit_exceeded(self, client_id: str, limit: int):
        """Log rate limit violations"""
        self.logger.warning(f"RATE_LIMIT_EXCEEDED: {client_id} - limit: {limit}")

    def log_sql_injection_attempt(self, query: str, client_id: str):
        """Log SQL injection attempts"""
        self.logger.error(f"SQL_INJECTION_ATTEMPT: {client_id} - query: {query[:100]}")


# Global security instances
security_validator = SecurityValidator()
credential_manager = CredentialManager()
rate_limiter = RateLimiter()
security_audit_logger = SecurityAuditLogger()


def validate_domain_name(domain: str) -> bool:
    """Validate that a domain name is safe to use.

    Args:
        domain: The domain name to validate

    Returns:
        True if valid, False otherwise
    """
    return security_validator.validate_domain_name(domain)


def sanitize_content(content: str) -> str:
    """Sanitize content to remove potentially harmful elements.

    Args:
        content: The content to sanitize

    Returns:
        The sanitized content
    """
    return security_validator.sanitize_input(content)
