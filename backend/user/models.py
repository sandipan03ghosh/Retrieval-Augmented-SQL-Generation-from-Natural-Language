from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import string
import logging

# Set up logger
logger = logging.getLogger(__name__)

# Create your models here.
class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    def __str__(self):
        return f"OTP for {self.user.username}"
    
    def is_valid(self):
        """Check if the OTP is still valid"""
        return not self.is_used and self.expires_at > timezone.now()
    
    @classmethod
    def generate_otp(cls, user, expiry_minutes=10):
        """Generate a new OTP for the given user"""
        try:
            logger.info(f"Invalidating previous OTPs for user {user.username}")
            # Invalidate any existing OTPs
            cls.objects.filter(user=user, is_used=False).update(is_used=True)
            
            # Generate a 6-digit OTP
            otp = ''.join(random.choices(string.digits, k=6))
            logger.info(f"Generated new OTP for user {user.username}")
            
            # Set expiry time
            expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
            
            # Create and return the OTP
            otp_obj = cls.objects.create(user=user, otp=otp, expires_at=expires_at)
            logger.info(f"Created OTP object with ID {otp_obj.id}")
            return otp_obj
        except Exception as e:
            logger.error(f"Error generating OTP: {str(e)}")
            # Create a fallback OTP without trying to invalidate previous ones
            try:
                otp = ''.join(random.choices(string.digits, k=6))
                expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
                otp_obj = cls(user=user, otp=otp, expires_at=expires_at)
                otp_obj.save()
                logger.info(f"Created fallback OTP object with ID {otp_obj.id}")
                return otp_obj
            except Exception as inner_e:
                logger.error(f"Critical error generating fallback OTP: {str(inner_e)}")
                raise

class UserTokenUsage(models.Model):
    """Tracks token usage for LLM API calls per user"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='token_usage')
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    model = models.CharField(max_length=50, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    query_text = models.TextField(blank=True, null=True)  # Store the query for reference
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Token usage for {self.user.username} on {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def record_token_usage(cls, user, prompt_tokens, completion_tokens, model="", query_text=None):
        """Record token usage for a user"""
        try:
            total_tokens = prompt_tokens + completion_tokens
            token_usage = cls(
                user=user,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                model=model,
                query_text=query_text
            )
            token_usage.save()
            logger.info(f"Recorded token usage for user {user.username}: {prompt_tokens} prompt, {completion_tokens} completion")
            return token_usage
        except Exception as e:
            logger.error(f"Error recording token usage: {str(e)}")
            return None
