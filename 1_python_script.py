#!/usr/bin/env python3
"""
ClickUp RCA Report Generator - Complete Version with Media Integration and Debug Mode
Generates RCA reports with images, console links, and code snippets from Slack
Analyzes ALL tickets including completed/closed ones
Debug mode support for troubleshooting
"""

import requests
import json
import yaml
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import platform
import sys
import re
import argparse

# AI Integration imports
try:
    from ai_processor import RCAAIProcessor
    from slack_integration import SlackIntegration
    from clickup_extended import ClickUpExtended
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("⚠️ AI components not found. Will generate report without AI analysis.")

CONFIG_FILE = "config.yaml"

def load_config():
    """Load configuration from YAML file"""
    config_path = Path(CONFIG_FILE)
    
    if not config_path.exists():
        print(f"❌ Configuration file '{CONFIG_FILE}' not found!")
        print("\nCreate config.yaml with:")
        print("""
clickup:
  api_key: "pk_YOUR_API_KEY_HERE"
  workspace_id: "3443930"
  customer_folder_id: "109448264"

slack:
  bot_token: "xoxb-YOUR-BOT-TOKEN"

openai:
  api_key: "sk-YOUR-OPENAI-KEY"
  model: "gpt-4o"
        """)
        sys.exit(1)
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if not config.get('clickup', {}).get('api_key'):
            print("❌ ClickUp API key not found!")
            sys.exit(1)
            
        return config
    except Exception as e:
        print(f"❌ Error loading config: {str(e)}")
        sys.exit(1)

def test_api_connection(config):
    """Test API connection"""
    api_key = config['clickup']['api_key']
    headers = {"Authorization": api_key}
    
    print("\n🔧 Testing API connection...")
    
    test_url = "https://api.clickup.com/api/v2/user"
    response = requests.get(test_url, headers=headers)
    
    if response.status_code == 200:
        user_data = response.json()
        user_name = user_data.get('user', {}).get('username', 'Unknown')
        print(f"✅ Connected as: {user_name}")
        return True
    else:
        print("❌ API connection failed!")
        return False

def get_date_range():
    """Get date range from user"""
    print("\n" + "="*60)
    print("SELECT DATE RANGE")
    print("="*60)
    
    print("\n1. Last 30 days")
    print("2. Last 7 days")
    print("3. Today only")
    print("4. Custom date range")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    today = datetime.now()
    
    if choice == '1':
        end_date = today
        start_date = today - timedelta(days=30)
        period_name = "Last 30 days"
    elif choice == '2':
        end_date = today
        start_date = today - timedelta(days=7)
        period_name = "Last 7 days"
    elif choice == '3':
        start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = today
        period_name = "Today"
    elif choice == '4':
        start = input("Enter start date (YYYY-MM-DD): ").strip()
        end = input("Enter end date (YYYY-MM-DD): ").strip()
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")
        period_name = "Custom range"
    else:
        end_date = today
        start_date = today - timedelta(days=7)
        period_name = "Last 7 days"
    
    print(f"\n📅 Selected: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    confirm = input("Confirm? (y/n): ").strip().lower()
    if confirm != 'y':
        return None, None, None
    
    return start_date, end_date, period_name

def fetch_tickets_complete(config, start_date, end_date):
    """Fetch ALL tickets from ClickUp including completed/closed status"""
    api_key = config['clickup']['api_key']
    headers = {"Authorization": api_key}
    folder_id = config['clickup']['customer_folder_id']
    
    # Define status mappings based on your ClickUp workflow
    ACTIVE_STATUSES = [
        'OPEN', 'PENDING (ACK)', 'NEEDS CUSTOMER RESPONSE', 
        'PLANNED', 'IN PROGRESS', 'BLOCKED', 
        'PR RAISED', 'PR MERGED', 'IN QA', 
        'TESTED', 'PRODUCT SIGNOFF', 'DESIGN SIGNOFF', 
        'RELEASE PENDING'
    ]
    
    # Both Done and Closed statuses are considered completed
    COMPLETED_STATUSES = [
        # Done statuses
        'DUPLICATE', 'EXTERNAL LIMITATION', 'CUSTOMER SIDE FIX',
        'INVALID', 'NOT REPRODUCIBLE', 'AS DESIGNED', 'CAN\'T FIX',
        # Closed status
        'COMPLETE'
    ]
    
    tickets_by_customer = {}
    
    print(f"\n🔍 Fetching ALL tickets (including completed/closed)...")
    
    # First get the folder structure
    folder_url = f"https://api.clickup.com/api/v2/folder/{folder_id}"
    folder_response = requests.get(folder_url, headers=headers)
    
    if folder_response.status_code != 200:
        print(f"❌ Cannot access folder")
        return tickets_by_customer
    
    folder_data = folder_response.json()
    lists = folder_data.get('lists', [])
    
    print(f"✅ Found {len(lists)} lists")
    
    # Track overall statistics
    total_fetched = 0
    total_completed = 0
    
    for list_item in lists:
        list_name = list_item.get('name', 'Unknown')
        list_id = list_item.get('id')
        
        # Skip internal lists
        if any(skip in list_name.lower() for skip in ['infra', 'internal', 'facets', 'test']):
            continue
        
        print(f"  📋 Processing: {list_name}")
        
        # Fetch tasks with ALL statuses including closed/completed
        task_url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
        
        # Important parameters to get ALL tasks
        params = {
            'archived': 'false',
            'page': 0,
            'order_by': 'created',
            'reverse': 'true',
            'subtasks': 'false',
            'include_closed': 'true'  # CRITICAL: Include closed/completed tasks
        }
        
        # Add date filtering
        start_timestamp = int(start_date.timestamp() * 1000)
        end_timestamp = int((end_date + timedelta(days=1)).timestamp() * 1000)
        
        params['date_created_gt'] = start_timestamp
        params['date_created_lt'] = end_timestamp
        
        # Fetch tasks with pagination support
        all_tasks = []
        page = 0
        
        while True:
            params['page'] = page
            task_response = requests.get(task_url, headers=headers, params=params)
            
            if task_response.status_code == 200:
                response_data = task_response.json()
                tasks = response_data.get("tasks", [])
                
                if not tasks:
                    break
                
                all_tasks.extend(tasks)
                
                if len(tasks) < 100:
                    break
                    
                page += 1
            else:
                print(f"    ⚠️ Error fetching tasks: {task_response.status_code}")
                break
        
        list_total = len(all_tasks)
        list_completed = 0
        
        # Process all tasks
        for task in all_tasks:
            date_created = task.get("date_created")
            if date_created:
                task_date = datetime.fromtimestamp(int(date_created)/1000)
                
                if start_date <= task_date <= end_date + timedelta(days=1):
                    status_info = task.get("status", {})
                    status_name = status_info.get("status", "Unknown") if isinstance(status_info, dict) else str(status_info)
                    status_type = status_info.get("type", "") if isinstance(status_info, dict) else ""
                    
                    # Normalize status name for comparison
                    status_upper = status_name.upper()
                    
                    # Check if ticket is completed (Done or Closed)
                    is_completed = (
                        status_upper in COMPLETED_STATUSES or
                        status_type in ["closed", "done"] or
                        status_name.lower() in ['complete', 'closed', 'done', 'resolved']
                    )
                    
                    if is_completed:
                        list_completed += 1
                    
                    ticket = {
                        "title": task.get("name", "No title"),
                        "clickup_id": task.get("id"),
                        "clickup_url": task.get("url"),
                        "status": status_name,
                        "status_type": status_type,
                        "is_completed": is_completed,
                        "date": task_date.strftime("%Y-%m-%d"),
                        "created_time": task_date.strftime("%H:%M"),
                        "customer": list_name,
                        "description": task.get("description", ""),
                        "priority": task.get("priority", {}),
                        "tags": task.get("tags", []),
                        "date_closed": None,
                        "time_to_resolution": None
                    }
                    
                    # Get assignees
                    assignees = task.get("assignees", [])
                    if assignees:
                        ticket["owner"] = assignees[0].get("username", "Unassigned")
                    else:
                        ticket["owner"] = "Unassigned"
                    
                    # For completed tasks, calculate resolution time
                    if is_completed:
                        date_closed = task.get("date_closed") or task.get("date_done")
                        if date_closed:
                            close_date = datetime.fromtimestamp(int(date_closed)/1000)
                            ticket["date_closed"] = close_date.strftime("%Y-%m-%d %H:%M")
                            time_diff = close_date - task_date
                            hours = int(time_diff.total_seconds() / 3600)
                            if hours < 24:
                                ticket["time_to_resolution"] = f"{hours} hours"
                            else:
                                days = hours // 24
                                ticket["time_to_resolution"] = f"{days} days"
                    
                    if list_name not in tickets_by_customer:
                        tickets_by_customer[list_name] = []
                    tickets_by_customer[list_name].append(ticket)
        
        if list_total > 0:
            print(f"    ✅ Found {list_total} tickets ({list_completed} closed/done, {list_total - list_completed} open)")
            total_fetched += list_total
            total_completed += list_completed
    
    print(f"\n📊 Fetch Summary:")
    print(f"  Total tickets: {total_fetched}")
    print(f"  Closed/Done: {total_completed}")
    print(f"  Open/In Progress: {total_fetched - total_completed}")
    
    return tickets_by_customer

def generate_html_report(tickets_by_customer, start_date, end_date, period_name, 
                        ai_processor=None, slack_client=None, clickup_extended=None, debug_mode=False):
    """Generate HTML report with AI-powered RCA fields including media"""
    sorted_customers = sorted(tickets_by_customer.items(), key=lambda x: (len(x[1]), x[0]))
    total_tickets = sum(len(tickets) for _, tickets in sorted_customers)
    
    # Count completed tickets (includes both Done and Closed statuses)
    total_completed = sum(
        sum(1 for t in tickets if t.get('is_completed', False))
        for _, tickets in sorted_customers
    )
    
    # Track if AI is being used
    using_ai = ai_processor is not None and slack_client is not None and clickup_extended is not None
    
    if using_ai:
        print("\n🤖 AI Analysis enabled - extracting data including images and links")
        if debug_mode:
            print("🔍 Debug mode is ON - detailed logging enabled")
    else:
        print("\n⚠️ AI Analysis disabled - RCA fields will be empty")
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>RCA Report - {period_name}</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
            margin: 0; 
            background: #f8f9fa; 
        }}
        
        .header {{ 
            background: linear-gradient(135deg, #7c3aed 0%, #14b8a6 100%); 
            color: white; 
            padding: 25px 40px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        .header-content {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .header-left {{
            display: flex;
            align-items: center;
            gap: 30px;
        }}
        
        .logo-section {{
            display: flex;
            align-items: center;
            gap: 25px;
        }}
        
        .logo-text {{
            font-size: 2rem;
            font-weight: bold;
            display: flex;
            align-items: baseline;
        }}
        
        .logo-dot {{ color: #14b8a6; font-size: 2.5rem; margin: 0 2px; }}
        .logo-cloud {{ color: #14b8a6; }}
        
        .divider {{
            width: 2px;
            height: 40px;
            background: rgba(255,255,255,0.3);
        }}
        
        .report-title {{
            font-size: 1.5rem;
            font-weight: 300;
        }}
        
        .header-right {{ display: flex; align-items: center; gap: 40px; }}
        .date-info {{ font-size: 0.95rem; opacity: 0.9; }}
        .stats {{ display: flex; gap: 30px; }}
        .stat {{ text-align: center; }}
        .stat-number {{ font-size: 1.8rem; font-weight: bold; color: #14b8a6; }}
        .stat-label {{ font-size: 0.75rem; opacity: 0.85; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}
        
        .ai-badge {{
            background: #10b981;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
            display: inline-block;
            margin-left: 10px;
        }}
        
        .debug-badge {{
            background: #f59e0b;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
            display: inline-block;
            margin-left: 5px;
        }}
        
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        
        .customer-section {{ 
            background: white; 
            margin: 20px 0; 
            border-radius: 12px; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.08); 
            overflow: hidden; 
        }}
        
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ 
            background: #fafafa; 
            padding: 12px 15px; 
            text-align: left; 
            font-size: 0.85rem; 
            color: #6b7280; 
            font-weight: 600; 
            text-transform: uppercase; 
            letter-spacing: 0.5px; 
        }}
        td {{ 
            padding: 14px 15px; 
            border-bottom: 1px solid #f3f4f6; 
            color: #374151; 
        }}
        
        tr.expandable {{ cursor: pointer; }}
        tr.expandable:hover td {{ background: #f9fafb; }}
        
        .expand-indicator {{ 
            display: inline-block; 
            margin-right: 8px; 
            transition: transform 0.3s; 
            color: #7c3aed; 
        }}
        
        .status {{ 
            padding: 5px 10px; 
            border-radius: 6px; 
            font-size: 0.8rem; 
            font-weight: 500; 
        }}
        
        /* Status colors */
        .status-complete {{ background: #d1fae5; color: #065f46; }}
        .status-customer-fix {{ background: #dbeafe; color: #1e40af; }}
        .status-invalid {{ background: #e5e7eb; color: #4b5563; }}
        .status-external {{ background: #fed7aa; color: #9a3412; }}
        .status-blocked {{ background: #fee2e2; color: #991b1b; }}
        .status-progress {{ background: #bfdbfe; color: #1e3a8a; }}
        .status-waiting {{ background: #fef3c7; color: #92400e; }}
        .status-qa {{ background: #e9d5ff; color: #6b21a8; }}
        .status-signoff {{ background: #ccfbf1; color: #134e4a; }}
        .status-open {{ background: #fef3c7; color: #92400e; }}
        .status-default {{ background: #f3f4f6; color: #6b7280; }}
        
        .rca-content {{
            background: #f0fdf4;
            border-left: 4px solid #10b981;
            padding: 12px;
            margin-top: 8px;
            border-radius: 4px;
            font-size: 0.95rem;
            line-height: 1.6;
            white-space: pre-wrap;
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
        }}
        
        .rca-empty {{
            color: #9ca3af;
            font-style: italic;
            padding: 12px;
            background: #f9fafb;
            border-radius: 4px;
        }}
        
        /* Media display styles */
        .media-section {{
            margin-top: 20px;
            padding: 15px;
            background: #f9fafb;
            border-radius: 8px;
            border: 1px solid #e5e7eb;
        }}
        
        .media-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 10px;
        }}
        
        .media-item {{
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            transition: transform 0.2s;
            cursor: pointer;
        }}
        
        .media-item:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        .media-item img {{
            width: 100%;
            height: 150px;
            object-fit: cover;
        }}
        
        .media-item-info {{
            padding: 8px;
            font-size: 0.75rem;
            color: #6b7280;
            text-align: center;
        }}
        
        .reference-link {{
            display: block;
            color: #7c3aed;
            text-decoration: none;
            word-break: break-all;
            margin: 5px 0;
            padding: 2px 0;
        }}
        
        .reference-link:hover {{
            text-decoration: underline;
        }}
        
        .code-snippet {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 15px;
            border-radius: 6px;
            margin: 10px 0;
            overflow-x: auto;
            font-family: 'SF Mono', 'Monaco', monospace;
            font-size: 0.9rem;
            line-height: 1.5;
        }}
        
        .indicator-badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            margin-left: 8px;
        }}
        
        .slack-indicator {{ background: #4a1d96; color: white; }}
        .images-indicator {{ background: #059669; color: white; }}
        .console-indicator {{ background: #dc2626; color: white; }}
        .no-data-indicator {{ background: #ef4444; color: white; }}
        .resolution-time {{ background: #e0e7ff; color: #4338ca; }}
        
        /* Modal for full-size images */
        .image-modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.9);
        }}
        
        .modal-content {{
            margin: auto;
            display: block;
            max-width: 90%;
            max-height: 90%;
            margin-top: 50px;
        }}
        
        .close-modal {{
            position: absolute;
            top: 15px;
            right: 35px;
            color: #f1f1f1;
            font-size: 40px;
            font-weight: bold;
            cursor: pointer;
        }}
        
        .close-modal:hover {{
            color: #bbb;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div class="header-left">
                <div class="logo-section">
                    <div class="logo-text">
                        <span style="color: white;">Facets</span>
                        <span class="logo-dot">.</span>
                        <span class="logo-cloud">cloud</span>
                    </div>
                    <div class="divider"></div>
                    <div class="report-title">
                        RCA Report
                        {f'<span class="ai-badge">✨ AI Analysis</span>' if using_ai else ''}
                        {f'<span class="debug-badge">🔍 Debug Mode</span>' if debug_mode else ''}
                    </div>
                </div>
            </div>
            <div class="header-right">
                <div>
                    <div class="date-info">📅 {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}</div>
                    <div class="date-info" style="margin-top: 5px;">{period_name}</div>
                </div>
                <div class="stats">
                    <div class="stat">
                        <div class="stat-number">{total_tickets}</div>
                        <div class="stat-label">Total Tickets</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">{total_completed}</div>
                        <div class="stat-label">Closed/Done</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">{len(sorted_customers)}</div>
                        <div class="stat-label">Customers</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="container">'''
    
    for customer_name, tickets in sorted_customers:
        customer_completed = sum(1 for t in tickets if t.get('is_completed', False))
        
        html += f'''
        <div class="customer-section">
            <div style="background: linear-gradient(135deg, #f8f9fa 0%, #f3f4f6 100%); 
                        padding: 20px 25px; display: flex; justify-content: space-between; align-items: center;">
                <h2>{customer_name}</h2>
                <div>
                    <span style="background: #14b8a6; color: white; padding: 6px 14px; 
                               border-radius: 20px; font-size: 0.85rem; font-weight: 500; margin-right: 10px;">
                        {len(tickets)} tickets
                    </span>
                    {f'<span style="background: #10b981; color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.85rem; font-weight: 500;">{customer_completed} closed/done</span>' if customer_completed > 0 else ''}
                </div>
            </div>
            <table>
                <tr>
                    <th width="50">#</th>
                    <th>Title</th>
                    <th width="120">ClickUp</th>
                    <th width="100">Date</th>
                    <th width="120">Status</th>
                    <th width="150">Owner</th>
                </tr>'''
        
        for i, ticket in enumerate(tickets, 1):
            status = ticket.get('status', 'Unknown')
            status_upper = status.upper()
            is_completed = ticket.get('is_completed', False)
            
            # Determine status class for styling
            status_class = 'status-default'
            if is_completed:
                if 'COMPLETE' in status_upper:
                    status_class = 'status-complete'
                elif 'CUSTOMER SIDE FIX' in status_upper:
                    status_class = 'status-customer-fix'
                elif 'INVALID' in status_upper or 'DUPLICATE' in status_upper:
                    status_class = 'status-invalid'
                elif 'EXTERNAL LIMITATION' in status_upper or 'CAN\'T FIX' in status_upper:
                    status_class = 'status-external'
                else:
                    status_class = 'status-complete'
            else:
                if 'BLOCKED' in status_upper:
                    status_class = 'status-blocked'
                elif 'IN PROGRESS' in status_upper or 'PR' in status_upper:
                    status_class = 'status-progress'
                elif 'NEEDS CUSTOMER RESPONSE' in status_upper:
                    status_class = 'status-waiting'
                elif 'QA' in status_upper or 'TEST' in status_upper:
                    status_class = 'status-qa'
                elif 'SIGNOFF' in status_upper or 'RELEASE' in status_upper:
                    status_class = 'status-signoff'
                else:
                    status_class = 'status-open'
            
            ticket_id = f"{customer_name.replace(' ', '_')}_{i}"
            clickup_id = ticket.get('clickup_id', '')
            
            # Initialize RCA data
            summary_text = ""
            debug_text = ""
            resolution_text = ""
            root_cause_text = ""
            supporting_media = {}
            indicators = ""
            
            # AI Analysis for this ticket
            if using_ai:
                try:
                    if debug_mode:
                        print(f"\n    === DEBUG: Processing {customer_name} - Ticket {i}/{len(tickets)} ===")
                        print(f"    Ticket ID: {clickup_id}")
                        print(f"    Status: {status}")
                    
                    print(f"    🔍 Analyzing {customer_name} ticket {i}/{len(tickets)} ({status})...")
                    
                    # Get extended data from ClickUp
                    full_task = clickup_extended.get_task_with_comments(clickup_id)
                    
                    if debug_mode:
                        print(f"    DEBUG: ClickUp data retrieved")
                        if full_task:
                            print(f"    DEBUG: Found {len(full_task.get('comments', []))} comments")
                            print(f"    DEBUG: Found {len(full_task.get('attachments', []))} attachments")
                    
                    # Get Slack data with media
                    slack_media = slack_client.get_messages_with_media(
                        ticket.get('clickup_url', ''), 
                        full_task
                    )
                    
                    if debug_mode:
                        print(f"    DEBUG: Slack data retrieved")
                        print(f"    DEBUG: Found {len(slack_media.get('messages', []))} Slack messages")
                    
                    # Get AI analysis with media integration
                    rca_data = ai_processor.analyze_ticket_for_rca(full_task, slack_media)
                    
                    # Extract RCA fields
                    summary_text = rca_data.get("summary", "")
                    debug_text = rca_data.get("debug_steps", "")
                    resolution_text = rca_data.get("resolution_steps", "")
                    root_cause_text = rca_data.get("root_cause", "")
                    supporting_media = rca_data.get("supporting_media", {})
                    
                    # Add ClickUp attachments to supporting media if not already there
                    if full_task and full_task.get('attachments'):
                        if 'attachments' not in supporting_media:
                            supporting_media['attachments'] = []
                        for att in full_task['attachments']:
                            supporting_media['attachments'].append({
                                'url': att.get('url', ''),
                                'title': att.get('title', 'Attachment'),
                                'source': 'clickup'
                            })
                    
                    if debug_mode:
                        print(f"    DEBUG: RCA Analysis complete")
                        print(f"    DEBUG: Summary length: {len(summary_text)} chars")
                        print(f"    DEBUG: Debug steps length: {len(debug_text)} chars")
                        print(f"    DEBUG: Resolution steps length: {len(resolution_text)} chars")
                        print(f"    DEBUG: Attachments: {len(supporting_media.get('attachments', []))}")
                    
                    # Build indicators
                    if slack_media.get('messages') and len(slack_media['messages']) > 1:
                        indicators += '<span class="indicator-badge slack-indicator">Slack</span>'
                    total_images = (len(slack_media.get('images', [])) + 
                                  len(slack_media.get('error_screenshots', [])) + 
                                  len([a for a in supporting_media.get('attachments', []) 
                                       if any(ext in str(a.get('url', '')).lower() 
                                             for ext in ['.png', '.jpg', '.jpeg', '.gif'])]))
                    if total_images > 0:
                        indicators += f'<span class="indicator-badge images-indicator">{total_images} img</span>'
                    if slack_media.get('console_links') or supporting_media.get('console_links'):
                        total_links = len(slack_media.get('console_links', [])) + len(supporting_media.get('console_links', []))
                        indicators += f'<span class="indicator-badge console-indicator">{total_links} links</span>'
                    if ticket.get('time_to_resolution'):
                        indicators += f'<span class="indicator-badge resolution-time">{ticket["time_to_resolution"]}</span>'
                    
                except Exception as e:
                    if debug_mode:
                        print(f"      ❌ DEBUG: Analysis error: {str(e)}")
                        import traceback
                        traceback.print_exc()
                    else:
                        print(f"      ⚠️ Analysis error: {str(e)[:100]}")
                    indicators = '<span class="indicator-badge no-data-indicator">Error</span>'
            
            html += f'''
                <tr class="expandable" onclick="toggleDetails('{ticket_id}')">
                    <td><span class="expand-indicator">▶</span> {i}</td>
                    <td>{ticket.get('title', 'No title')}{indicators}</td>
                    <td><a href="{ticket.get('clickup_url', '#')}" 
                           style="color: #7c3aed; text-decoration: none; padding: 5px 12px; 
                                  border: 1px solid #7c3aed; border-radius: 6px; display: inline-block; font-size: 0.85rem;"
                           target="_blank" onclick="event.stopPropagation()">View</a></td>
                    <td>{ticket.get('date', '-')}</td>
                    <td><span class="status {status_class}">{status}</span></td>
                    <td>{ticket.get('owner', 'Unassigned')}</td>
                </tr>
                <tr id="details_{ticket_id}" style="display: none;">
                    <td colspan="6" style="padding: 0;">
                        <div style="background: #f9fafb; padding: 20px 60px; border-left: 4px solid #7c3aed;">
                            
                            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 25px; 
                                        padding: 15px; background: white; border-radius: 6px;">
                                <div><strong>Customer:</strong><br>{customer_name}</div>
                                <div><strong>Date:</strong><br>{ticket.get('date', 'N/A')}</div>
                                <div><strong>Status:</strong><br>{status}</div>
                                <div><strong>Owner:</strong><br>{ticket.get('owner', 'Unassigned')}</div>
                                <div><strong>ClickUp ID:</strong><br>{clickup_id or 'N/A'}</div>
                                <div><strong>Resolution Time:</strong><br>{ticket.get('time_to_resolution', 'N/A')}</div>
                            </div>
                            
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: #1f2937;">📋 Summary of the Issue</h4>
                                <div style="padding: 12px; background: white; border-radius: 6px;">
                                    {f'<div class="rca-content">{summary_text}</div>' if summary_text else '<div class="rca-empty">No summary data available</div>'}
                                </div>
                            </div>
                            
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: #1f2937;">🔍 Steps to Debug</h4>
                                <div style="padding: 12px; background: white; border-radius: 6px;">
                                    {f'<div class="rca-content">{debug_text}</div>' if debug_text else '<div class="rca-empty">No debug steps found</div>'}
                                </div>
                            </div>
                            
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: #1f2937;">✅ Steps to Resolution</h4>
                                <div style="padding: 12px; background: white; border-radius: 6px;">
                                    {f'<div class="rca-content">{resolution_text}</div>' if resolution_text else '<div class="rca-empty">No resolution data available</div>'}
                                </div>
                            </div>
                            
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: #1f2937;">🎯 Root Cause Analysis</h4>
                                <div style="padding: 12px; background: white; border-radius: 6px;">
                                    {f'<div class="rca-content">{root_cause_text}</div>' if root_cause_text else '<div class="rca-empty">Root cause not identified</div>'}
                                </div>
                            </div>'''
            
            # Add Reference Links section if console links exist
            all_console_links = []
            if supporting_media.get('console_links'):
                all_console_links.extend(supporting_media['console_links'])
            
            if all_console_links:
                html += '''
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: #1f2937;">🔗 Reference Links:</h4>
                                <div style="padding: 12px; background: white; border-radius: 6px;">'''
                
                # Remove duplicates and display links
                seen_urls = set()
                for link in all_console_links[:10]:
                    link_url = link.get('url', '') if isinstance(link, dict) else str(link)
                    if link_url and link_url not in seen_urls:
                        seen_urls.add(link_url)
                        html += f'''
                                    <a href="{link_url}" target="_blank" class="reference-link">
                                        {link_url}
                                    </a>'''
                
                html += '''
                                </div>
                            </div>'''
            
            # Collect ALL images from all sources
            all_images = []
            
            # Add error screenshots from Slack
            if supporting_media.get('error_screenshots'):
                for img in supporting_media['error_screenshots']:
                    all_images.append({
                        'url': img.get('url', ''),
                        'thumb_url': img.get('thumb_url', img.get('url', '')),
                        'title': img.get('title', 'Error Screenshot'),
                        'timestamp': img.get('timestamp', '')
                    })
            
            # Add regular images from Slack
            if supporting_media.get('images'):
                for img in supporting_media['images']:
                    all_images.append({
                        'url': img.get('url', ''),
                        'thumb_url': img.get('thumb_url', img.get('url', '')),
                        'title': img.get('title', 'Image'),
                        'timestamp': img.get('timestamp', '')
                    })
            
            # Add ClickUp attachments that are images
            if supporting_media.get('attachments'):
                for att in supporting_media['attachments']:
                    url = att.get('url', '')
                    if any(ext in url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']):
                        # Extract date from URL if it contains timestamp
                        title = att.get('title', 'Attachment')
                        timestamp = ''
                        # Try to extract timestamp from filename
                        import re
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', title)
                        if date_match:
                            timestamp = date_match.group(1)
                        
                        all_images.append({
                            'url': url,
                            'thumb_url': url,
                            'title': title,
                            'timestamp': timestamp
                        })
            
            # Display all images in a unified "Attached Images" section
            if all_images:
                html += '''
                            <div style="margin-bottom: 20px;">
                                <h4 style="color: #1f2937;">📷 Attached Images</h4>
                                <div style="padding: 15px; background: white; border-radius: 6px;">
                                    <div class="media-grid">'''
                
                for img in all_images[:10]:  # Limit to 10 images
                    img_url = img.get('url', '')
                    img_thumb = img.get('thumb_url', img_url)
                    img_title = img.get('title', 'Image')
                    
                    # Format display title
                    display_title = img_title
                    if 'Screenshot' in img_title and img.get('timestamp'):
                        display_title = f"Screenshot {img['timestamp']}"
                    elif len(img_title) > 30:
                        display_title = img_title[:27] + '...'
                    
                    html += f'''
                                        <div class="media-item" onclick="openImageModal('{img_url}')">
                                            <img src="{img_thumb}" alt="{img_title}" 
                                                 onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'200\\' height=\\'150\\'%3E%3Crect fill=\\'%23f3f4f6\\' width=\\'200\\' height=\\'150\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' text-anchor=\\'middle\\' dy=\\'.3em\\' fill=\\'%236b7280\\'%3EImage Not Available%3C/text%3E%3C/svg%3E'">
                                            <div class="media-item-info">
                                                {display_title}
                                            </div>
                                        </div>'''
                
                html += '''
                                    </div>
                                </div>
                            </div>'''
            
            # Add code snippets if available
            if supporting_media.get('code_snippets'):
                html += '''
                            <div class="media-section">
                                <h4 style="color: #1f2937;">💻 Commands/Code Used</h4>'''
                
                for snippet in supporting_media['code_snippets'][:3]:
                    code = snippet.get('code', '')
                    user = snippet.get('user', 'Unknown')
                    
                    # Escape HTML in code
                    code = code.replace('<', '&lt;').replace('>', '&gt;')
                    
                    html += f'''
                                <div class="code-snippet">
                                    <small style="color: #94a3b8;">Shared by {user}</small>
                                    <pre style="margin: 10px 0 0 0;">{code[:500]}{'...' if len(code) > 500 else ''}</pre>
                                </div>'''
                
                html += '''
                            </div>'''
            
            html += '''
                        </div>
                    </td>
                </tr>'''
        
        html += '</table></div>'
    
    html += '''
    </div>
    
    <!-- Image Modal -->
    <div id="imageModal" class="image-modal" onclick="closeImageModal()">
        <span class="close-modal">&times;</span>
        <img class="modal-content" id="modalImage">
    </div>
    
    <script>
        function toggleDetails(ticketId) {
            const detailsRow = document.getElementById('details_' + ticketId);
            const clickedRow = detailsRow.previousElementSibling;
            const indicator = clickedRow.querySelector('.expand-indicator');
            
            if (detailsRow.style.display === 'table-row') {
                detailsRow.style.display = 'none';
                indicator.innerHTML = '▶';
            } else {
                // Close all other expanded rows
                document.querySelectorAll('[id^="details_"]').forEach(row => {
                    row.style.display = 'none';
                    if (row.previousElementSibling) {
                        row.previousElementSibling.querySelector('.expand-indicator').innerHTML = '▶';
                    }
                });
                
                detailsRow.style.display = 'table-row';
                indicator.innerHTML = '▼';
            }
        }
        
        function openImageModal(imgSrc) {
            event.stopPropagation();
            const modal = document.getElementById('imageModal');
            const modalImg = document.getElementById('modalImage');
            modal.style.display = 'block';
            modalImg.src = imgSrc;
        }
        
        function closeImageModal() {
            document.getElementById('imageModal').style.display = 'none';
        }
        
        // Close modal on Escape key
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                closeImageModal();
            }
        });
    </script>
</body>
</html>'''
    
    return html

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Generate RCA Reports from ClickUp tickets')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode for detailed logging')
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("CLICKUP RCA REPORT GENERATOR - ENHANCED WITH MEDIA")
    if args.debug:
        print("DEBUG MODE ENABLED 🔍")
    print("="*60)
    
    config = load_config()
    
    # Initialize AI components if available
    ai_processor = None
    slack_client = None
    clickup_extended = None
    
    if AI_AVAILABLE:
        try:
            print("\n🤖 Initializing AI components...")
            # Pass debug mode to AI processor
            ai_processor = RCAAIProcessor(debug_mode=args.debug)
            slack_client = SlackIntegration()
            clickup_extended = ClickUpExtended()
            
            if args.debug:
                print("🔍 Debug mode ENABLED for AI processor")
                print("   - Detailed comment extraction logging")
                print("   - Bot filtering visibility")
                print("   - Conversation building details")
                print("   - AI processing steps")
            
            print("✅ AI components ready (with media extraction)")
        except Exception as e:
            print(f"⚠️ AI initialization failed: {str(e)}")
            if args.debug:
                import traceback
                traceback.print_exc()
            print("   Continuing without AI analysis...")
    
    if not test_api_connection(config):
        return
    
    start_date, end_date, period_name = get_date_range()
    if not start_date:
        return
    
    # Use the updated fetch function that gets ALL tickets
    tickets_by_customer = fetch_tickets_complete(config, start_date, end_date)
    
    if not tickets_by_customer:
        print("\n⚠️ No tickets found")
        return
    
    total = sum(len(t) for t in tickets_by_customer.values())
    print(f"\n✅ Processing {total} tickets from {len(tickets_by_customer)} customers")
    
    # Generate report with AI if available (pass debug mode)
    html_content = generate_html_report(
        tickets_by_customer, start_date, end_date, period_name,
        ai_processor, slack_client, clickup_extended,
        debug_mode=args.debug
    )
    
    reports_dir = Path("/Users/abhishtbagewadi/Documents/Scripts/RCA-SCRIPT-2/rca_reports")
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"RCA_Report_{timestamp}.html"
    filepath = reports_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✅ Report saved: {filename}")
    
    if AI_AVAILABLE and ai_processor:
        print("✨ Report includes:")
        print("   - AI-analyzed RCA data")
        print("   - ClickUp attachment images")
        print("   - Error screenshots from Slack")
        print("   - Console/dashboard links")
        print("   - Code snippets and commands")
        if args.debug:
            print("   - Generated with DEBUG mode insights")
    else:
        print("⚠️ Report generated without AI analysis")
    
    if platform.system() == 'Darwin':
        subprocess.run(['open', str(filepath)])
        print("🌐 Opening in browser...")

if __name__ == "__main__":
    try:
        import yaml
        import requests
    except ImportError:
        print("Installing required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "requests"])
        print("Please run again.")
        sys.exit(0)
    
    main()