import smtplib
import requests
import logging
import os
import time
from email.mime.text import MIMEText
from config import settings

logger = logging.getLogger("Alerts")

# In-memory deduplication: key -> last_sent_timestamp
_alert_sent = {}
ALERT_COOLDOWN_MINUTES = 30

def send_email_alert(subject: str, body_html: str):
    """Sends an email alert to IT support. Silently fails if not configured."""
    if not settings.smtp_host:
        return
        
    try:
        msg = MIMEText(body_html, 'html')
        msg['Subject'] = f"[PrintHub Alert] {subject}"
        msg['From'] = settings.alert_email_from
        msg['To'] = settings.alert_email_to
        
        # Use a longer timeout for hospital SMTP relays
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            if settings.environment == "production":
                s.starttls()
            s.sendmail(msg['From'], settings.alert_email_to.split(","), msg.as_string())
            
        logger.info(f"[ALERT] Email sent: {subject}")
    except Exception as e:
        logger.error(f"[ALERT ERROR] Email failed: {e}")

def send_webhook_alert(subject: str, body_text: str):
    """Sends a webhook alert (Teams/Slack). Silently fails if not configured."""
    url = settings.alert_webhook_url
    if not url:
        return
        
    try:
        # Teams-style Markdown payload
        # Clean HTML tags and replace br with newline
        clean_body = body_text.replace('<p>', '').replace('</p>', '').replace('<br>', '\n').replace('<b>', '**').replace('</b>', '**')
        payload = {
            "text": f"### {subject}\n{clean_body}"
        }
        requests.post(url, json=payload, timeout=5)
        logger.info(f"[ALERT] Webhook sent: {subject}")
    except Exception as e:
        logger.error(f"[ALERT ERROR] Webhook failed: {e}")

def alert(subject: str, body: str):
    """Send alert via all configured channels."""
    send_email_alert(subject, body)
    send_webhook_alert(subject, body)

def alert_deduplicated(key: str, subject: str, body: str):
    """Prevents alert storms by enforcing a cooldown period per alert type/ID."""
    now = time.time()
    last = _alert_sent.get(key, 0)
    
    if now - last > ALERT_COOLDOWN_MINUTES * 60:
        _alert_sent[key] = now
        alert(subject, body)
    else:
        logger.debug(f"[ALERT SUPPRESSED] {key} is in cooldown.")
