from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
import secrets
import string

class FirebaseAuthView(APIView):
    """
    Authentication view for handling both form-based Firebase login and Google sign-ins.
    This centralizes all Firebase authentication into a single endpoint.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Extract user info from the request
        email = request.data.get('email')
        uid = request.data.get('uid')
        username = request.data.get('username')
        display_name = request.data.get('display_name', '')
        is_google_login = request.data.get('is_google_login', False)
        is_registration = request.data.get('is_registration', False)
        # Get the password if provided (for form registration)
        form_password = request.data.get('password')
        
        if not email or not uid:
            return Response(
                {"detail": "Email and uid are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate a username for Google users if not provided
        if is_google_login and not username:
            username = display_name or email.split('@')[0]
            # Make username unique by removing non-alphanumeric chars and adding part of uid
            username = ''.join(c for c in username if c.isalnum())
            username = f"{username}_{uid[-6:]}"
        
        # Generate a strong random password for the Django user if no form password provided
        # (Firebase handles actual auth, this is just for Django's model)
        password = form_password if form_password else ''.join(
            secrets.choice(string.ascii_letters + string.digits + string.punctuation) 
            for _ in range(20)
        )
        
        # Try to find existing user or create a new one
        try:
            # First check if user exists with this email
            user = User.objects.get(email=email)
            
            # If this is a registration attempt for an existing email, return an error
            if is_registration and not is_google_login:
                return Response(
                    {"detail": "This email is already registered. Please login instead."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # For existing users, we don't change their username
            # This keeps form login and Google login working for the same user
            
        except User.DoesNotExist:
            # User doesn't exist, create a new one
            if not username:
                return Response(
                    {"detail": "Username is required for registration"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # Check if username is already taken
            if User.objects.filter(username=username).exists():
                return Response(
                    {"detail": "This username is already taken. Please choose a different one."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # Create new user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password  # Use the actual password or the generated one
            )
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # Add username to token payload
        refresh['username'] = user.username
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'username': user.username,
            'email': user.email
        })