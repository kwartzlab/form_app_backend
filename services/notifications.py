import json
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from config import Config


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

def send_email_notification(data, file_links):          # todo: separate html body template into a separate file for readability
    """Send email notification with file links instead of attachments"""
    try:
        if not all([Config.EMAIL_ADDRESS, Config.EMAIL_PASSWORD, Config.RECIPIENT_EMAIL]):
            print("Warning: Email credentials not fully configured")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = Config.EMAIL_ADDRESS
        msg['To'] = Config.RECIPIENT_EMAIL
        msg['Subject'] = f"New Reimbursement Request - {data['firstName']} {data['lastName']}"
        
        # Email body
        expenses = json.loads(data['expenses'])
        total = sum(float(exp.get('amount', 0) or 0) for exp in expenses)
        
        # Create HTML table for expenses
        expense_rows = ""
        for exp in expenses:
            expense_rows += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px;">{exp.get('approval', 'N/A')}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{exp.get('vendor', 'N/A')}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{exp.get('description', 'N/A')}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">${exp.get('amount', '0')}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{exp.get('hst', 'N/A')}</td>
            </tr>"""
        
        # Create file links HTML
        file_links_html = ""
        if file_links:
            file_links_html = "<h3>Attached Files:</h3><ul>"
            for link in file_links:
                file_links_html += f'<li><a href="{link}">View File</a></li>'
            file_links_html += "</ul>"
        else:
            file_links_html = "<p><em>No files attached.</em></p>"
        
        # Comments section
        comments_html = ""
        if data.get('comments'):
            comments_html = f"""
            <h3>Additional Comments:</h3>
            <p>{data['comments']}</p>"""
        
        # HTML body
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th {{ background-color: #4CAF50; color: white; padding: 12px; text-align: left; border: 1px solid #ddd; }}
                td {{ border: 1px solid #ddd; padding: 8px; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                .header {{ background-color: #f4f4f4; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .total {{ font-size: 18px; font-weight: bold; margin: 20px 0; padding: 10px; background-color: #e8f5e9; border-left: 4px solid #4CAF50; }}
                h2 {{ color: #2c3e50; }}
                h3 {{ color: #34495e; margin-top: 20px; }}
                a {{ color: #1976d2; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <h2>New Reimbursement Request</h2>
            
            <div class="header">
                <p><strong>Submitted by:</strong> {data['firstName']} {data['lastName']}</p>
                <p><strong>Email:</strong> {data['email']}</p>
                <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <h3>Expense Details:</h3>
            <table>
                <thead>
                    <tr>
                        <th>Approval/Project</th>
                        <th>Vendor</th>
                        <th>Description</th>
                        <th>Amount</th>
                        <th>HST</th>
                    </tr>
                </thead>
                <tbody>
                    {expense_rows}
                </tbody>
            </table>
            
            <div class="total">
                TOTAL: ${total:.2f}
            </div>
            
            {comments_html}
            
            {file_links_html}
        </body>
        </html>
        """
        
        # Plain text fallback
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
        
        # Attach both plain text and HTML versions
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