import json
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from email.mime.base import MIMEBase
from email import encoders

from config import Config
from .utils import log_execution_time
from services.logger import logger

def render_email_template(template_name, **context):
    """Render email template with context"""
    with open(f'templates/{template_name}', 'r') as f:
        template = Template(f.read())
    return template.render(**context)

@log_execution_time
def send_slack_notification(data, file_links):
    """Send notification to Slack with file links"""
    # TODO generalize the slack notification function later. Right now, only the PA uses it
    try:
        if not Config.SLACK_WEBHOOK_URL:
            logger.warning("SLACK_WEBHOOK_URL not set")
            # print("Warning: SLACK_WEBHOOK_URL not set")
            return False
        
        expenses = data['expenses']
        total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)
        
        # Format expenses for Slack
        expense_lines = []
        for exp in expenses:
            expense_lines.append(
                f"• {exp.get('description', 'N/A')} - ${exp.get('amount', '0')} ({exp.get('hst', 'N/A')})"
            )
        
        message = {
            "text": "New Purchase Approval",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "💰 New Purchase Approval"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Name:*\n{data['firstName']} {data['lastName']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Email:*\n{data['email']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Amount:*\n${total:.2f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Date:*\n{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Expenses:*\n" + "\n".join(expense_lines)
                    }
                }
            ]
        }
        
        if data.get('comments'):
            message["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Comments:*\n{data['comments']}"
                }
            })
        
        # Add file links
        if file_links:
            file_links_formatted = '\n'.join([f"• <{link}|View File>" for link in file_links])
            message["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Attached Files:*\n{file_links_formatted}"
                }
            })
        
        response = requests.post(Config.SLACK_WEBHOOK_URL, json=message, timeout=10)
        return response.status_code == 200
    except Exception as e:
        # print(f"Error sending Slack notification: {e}")
        logger.error("Error Occurred", extra={'error sending slack notification':str(e)}, exc_info=True)
        return False

def build_plain_message(data, file_links):
    # Plain text fallback
    # TODO remove plaintext fallback entirely, or find a way to template-ize it
    # TODO implement PA version of plaintext, if keeping it
    expenses = json.loads(data['expenses'])
    total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)
    plain_body = f"""
New Reimbursement Request

Submitted by: {data['firstName']} {data['lastName']}
Email: {data['email']}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

EXPENSES:
"""
    for i, exp in enumerate(expenses, 1):
        plain_body += f"""
{i}. Approval/Project: {exp.get('approval', 'N/A')}
Vendor: {exp.get('vendor', 'N/A')}
Description: {exp.get('description', 'N/A')}
Amount: ${exp.get('amount', '0')}
HST: {exp.get('hst', 'N/A')}
"""
    
    plain_body += f"\nTOTAL: ${total:.2f}\n"
    
    if data.get('comments'):
        plain_body += f"\nAdditional Comments:\n{data['comments']}\n"
    
    if file_links:
        plain_body += "\n\nATTACHED FILES:\n"
        for i, link in enumerate(file_links, 1):
            plain_body += f"{i}. {link}\n"
    else:
        plain_body += "\n\nNo files attached.\n"

    return plain_body

def email_builder(endpoint, data, file_links, email_type):
    """Build email HTML from unified template"""
    form_specific = {
        "Reimbursement Request": {
            "message": "Thank you for submitting your request! Our Treasurer will be in touch if there are any issues."
        },
        "Purchase Approval": {
            "message": "Thank you for submitting your purchase approval request! Remember to keep an eye on the member's list for questions and +1s from the Board."
        }
    }

    # Calculate total
    expenses = data['expenses']  # Already parsed as list of dicts
    total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)
    
    # Render unified template
    html_body = render_email_template(
        'email_template.html',
        email_type=email_type,
        form_type=endpoint,
        message=form_specific[endpoint]["message"],
        first_name=data['firstName'],
        last_name=data['lastName'],
        email=data['email'],
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        expenses=expenses,
        total=total,
        comments=data.get('comments', ''),
        file_links=file_links
    )

    return html_body

@log_execution_time
def send_email_notification(endpoint, data, file_links):
    """Send email notification with file links instead of attachments"""
    try:
        sender_email = Config.DEV_OUTBOUND_EMAIL_ADDRESS if Config.FLASK_ENV == "development" else Config.OUTBOUND_EMAIL_ADDRESS
        if not all([sender_email, Config.EMAIL_PASSWORD]):
            # print("Warning: Email credentials not fully configured")
            logger.warning("Email credentials not fully configured")
            return False
        
        recipient_email = Config.DEV_RECIPIENT_EMAIL if Config.FLASK_ENV == "development" else Config.RECIPIENT_EMAIL[endpoint]
        if not recipient_email:
            # print(f"Warning: No recipient email configured for {endpoint}")
            logger.warning(f"Warning: No recipient email configured for {endpoint}")
            return False

        # Render both emails from unified template
        list_notify_html_body = email_builder(endpoint, data, file_links, "list")
        thanks_html_body = email_builder(endpoint, data, file_links, "acknowledgment")

        # Create both messages
        list_msg = MIMEMultipart('alternative')
        list_msg['From'] = sender_email
        list_msg['To'] = recipient_email
        list_msg['Subject'] = f"New {endpoint} - {data['firstName']} {data['lastName']}"
        list_msg.attach(MIMEText(list_notify_html_body, 'html'))

        ack_msg = MIMEMultipart('alternative')
        ack_msg['From'] = sender_email
        ack_msg['To'] = data["email"]
        ack_msg['Subject'] = f"New {endpoint} - {data['firstName']} {data['lastName']}"
        ack_msg.attach(MIMEText(thanks_html_body, 'html'))
        
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        server.starttls()
        server.login(sender_email, Config.EMAIL_PASSWORD)
        
        list_sent = False
        ack_sent = False
        
        try:
            server.send_message(list_msg)
            list_sent = True
        except Exception as e:
            # print(f"Failed to send list notification: {e}")
            logger.exception("Exception Occurred", extra={'failed to send list notification':str(e)}, exc_info=True)
        try:
            server.send_message(ack_msg)
            ack_sent = True
        except Exception as e:
            # print(f"Failed to send acknowledgement: {e}")
            logger.exception("Exception Occurred", extra={'failed to send acknowledgement':str(e)}, exc_info=True)
            
        server.quit()
        return list_sent or ack_sent
    except Exception as e:
        print(f"Error sending email: {e}")
        logger.error("Error Occurred", extra={'error sending email':str(e)}, exc_info=True)
        return False