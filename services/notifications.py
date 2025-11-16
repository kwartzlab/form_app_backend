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

def render_email_template(template_name, **context):
    """Render email template with context"""
    with open(f'templates/{template_name}', 'r') as f:
        template = Template(f.read())
    return template.render(**context)

def send_slack_notification(data, file_links):
    """Send notification to Slack with file links"""
    try:
        if not Config.SLACK_WEBHOOK_URL:
            print("Warning: SLACK_WEBHOOK_URL not set")
            return False
        
        expenses = json.loads(data['expenses'])
        total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)
        
        # Format expenses for Slack
        expense_lines = []
        for exp in expenses:
            expense_lines.append(
                f"• {exp.get('description', 'N/A')} - ${exp.get('amount', '0')} ({exp.get('hst', 'N/A')})"
            )
        
        message = {
            "text": "New Reimbursement Request",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "💰 New Reimbursement Request"
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
        
        response = requests.post(Config.SLACK_WEBHOOK_URL, json=message)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending Slack notification: {e}")
        return False

def build_plain_message(data, file_links):
    # Plain text fallback
    # todo: remove plaintext fallback entirely, or find a way to template-ize it
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

def send_email_notification(data, file_links):          # todo: send second message to submitter
    """Send email notification with file links instead of attachments"""
    try:
        if not all([Config.EMAIL_ADDRESS, Config.EMAIL_PASSWORD, Config.RECIPIENT_EMAIL]):
            print("Warning: Email credentials not fully configured")
            return False
        
        # Email body
        expenses = json.loads(data['expenses'])
        total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)

        # Render HTML email from template
        html_body = render_email_template(
            'email_reimbursement.html',
            first_name=data['firstName'],
            last_name=data['lastName'],
            email=data['email'],
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            expenses=expenses,
            total=total,
            comments=data.get('comments', ''),
            file_links=file_links
        )

        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = Config.EMAIL_ADDRESS
        msg['To'] = Config.RECIPIENT_EMAIL
        msg['Subject'] = f"New Reimbursement Request - {data['firstName']} {data['lastName']}"

        # Attach both plain text and HTML versions
        # plain_body = build_plain_message(data, file_links)
        # msg.attach(MIMEText(plain_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        server.starttls()
        server.login(Config.EMAIL_ADDRESS, Config.EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False