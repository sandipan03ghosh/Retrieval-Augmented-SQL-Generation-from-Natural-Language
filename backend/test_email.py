import os
import sys
import time
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'
print(f"Loading .env from: {ENV_PATH.absolute()}")
load_dotenv(ENV_PATH)

# Get email settings from environment variables
email_host = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
email_port = int(os.environ.get('EMAIL_PORT', 587))
email_use_tls = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
email_host_user = os.environ.get('EMAIL_HOST_USER')
email_host_password = os.environ.get('EMAIL_HOST_PASSWORD')
default_from_email = os.environ.get('DEFAULT_FROM_EMAIL', email_host_user)

# Print settings for debugging
print(f"Email Settings:")
print(f"Host: {email_host}")
print(f"Port: {email_port}")
print(f"Use TLS: {email_use_tls}")
print(f"User: {email_host_user}")
print(f"Password: {'Set' if email_host_password else 'Not set'}")
print(f"From Email: {default_from_email}")

def send_test_email():
    try:
        # Create message
        message = MIMEMultipart()
        message['Subject'] = 'Test Email from Django App'
        message['From'] = default_from_email
        message['To'] = email_host_user  # Sending to ourselves for testing
        
        # Create message body
        body = """
        This is a test email to verify that SMTP configuration is working correctly.
        
        If you received this, your email settings are correct!
        """
        message.attach(MIMEText(body, 'plain'))
        
        # Create SMTP connection with timeout
        print("Connecting to SMTP server...")
        server = smtplib.SMTP(email_host, email_port, timeout=20)
        
        try:
            if email_use_tls:
                print("Starting TLS...")
                server.starttls()
            
            print("Logging in...")
            server.login(email_host_user, email_host_password)
            
            print("Sending email...")
            server.send_message(message)
            print("Email sent successfully!")
            
        except Exception as e:
            print(f"SMTP operation failed: {str(e)}")
            print(traceback.format_exc())
            return False
        finally:
            print("Closing SMTP connection...")
            server.quit()
            
        return True
    except Exception as e:
        print(f"Error setting up email: {str(e)}")
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    print("Starting email test...")
    result = send_test_email()
    print(f"Email test {'succeeded' if result else 'failed'}")
    
    # Wait for a moment to see all output
    time.sleep(1)