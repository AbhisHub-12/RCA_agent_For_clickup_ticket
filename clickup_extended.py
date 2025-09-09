# clickup_extended.py
"""
Extended ClickUp API Integration for RCA Report Generation
Fetches detailed task information including comments, activity, Slack integration, and attachments/images
"""

import requests
from typing import Dict, List, Optional
import yaml
from datetime import datetime
import re
import json

class ClickUpExtended:
    def __init__(self, config_path="config.yaml"):
        """Initialize ClickUp client with extended features"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            if not config.get('clickup', {}).get('api_key'):
                raise ValueError("ClickUp API key not found in config")
            
            self.api_key = config['clickup']['api_key']
            self.headers = {
                "Authorization": self.api_key,
                "Content-Type": "application/json"
            }
            self.base_url = "https://api.clickup.com/api/v2"
            
            print(f"   ✅ ClickUp Extended initialized")
            
        except Exception as e:
            print(f"   ❌ ClickUp Extended initialization failed: {str(e)}")
            raise
    
    def get_task_with_comments(self, task_id: str) -> Dict:
        """Get task details including comments, Slack integration, and attachments"""
        if not task_id:
            return {}
        
        task_data = {}
        
        try:
            # Get complete task details with custom fields
            task_url = f"{self.base_url}/task/{task_id}"
            params = {
                "include_subtasks": "true",
                "include_markdown_description": "true"
            }
            response = requests.get(task_url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                task_data = response.json()
                
                # Get comments for the task
                comments = self.get_task_comments(task_id)
                task_data['comments'] = comments
                
                # Extract Slack thread URL from various sources
                slack_url = self.extract_slack_thread_url(task_data, comments)
                if slack_url:
                    task_data['slack_thread_url'] = slack_url
                    print(f"      📎 Found Slack thread in ticket: {slack_url[:60]}...")
                
                # Get attachments and images
                attachments = self.get_task_attachments_with_images(task_data)
                task_data['attachments'] = attachments
                
                # Extract images from comments
                comment_images = self.extract_images_from_comments(comments)
                task_data['comment_images'] = comment_images
                
                # Get custom fields if any
                custom_fields = self.extract_custom_fields(task_data)
                task_data['custom_fields_formatted'] = custom_fields
                
                # Try to get task activity/history
                activity = self.get_task_activity_timeline(task_id)
                if activity:
                    task_data['activity'] = activity
                
            elif response.status_code == 404:
                print(f"      ⚠️ Task {task_id} not found")
            else:
                print(f"      ⚠️ Failed to fetch task {task_id}: Status {response.status_code}")
        
        except requests.exceptions.Timeout:
            print(f"      ⚠️ Timeout fetching task {task_id}")
        except Exception as e:
            print(f"      ❌ Error fetching task {task_id}: {str(e)[:100]}")
        
        return task_data
    
    def get_task_attachments_with_images(self, task_data: Dict) -> List[Dict]:
        """Get all attachments including images from task data"""
        attachments = []
        
        try:
            # Process attachments from task data
            for attachment in task_data.get('attachments', []):
                att_info = {
                    'id': attachment.get('id', ''),
                    'title': attachment.get('title', 'Attachment'),
                    'url': attachment.get('url', ''),
                    'type': attachment.get('type', ''),
                    'size': attachment.get('size', 0),
                    'date': self._format_timestamp(attachment.get('date')),
                    'is_image': self._is_image_file(attachment.get('url', '') or attachment.get('title', ''))
                }
                
                # If it's an image, mark it
                if att_info['is_image']:
                    att_info['thumbnail_url'] = attachment.get('thumbnail_small', attachment.get('url', ''))
                
                attachments.append(att_info)
        
        except Exception as e:
            print(f"      ⚠️ Error processing attachments: {str(e)[:100]}")
        
        return attachments
    
    def extract_images_from_comments(self, comments: List[Dict]) -> List[Dict]:
        """Extract image URLs and references from comments"""
        images = []
        
        # Pattern to find image URLs
        image_url_pattern = r'(https?://[^\s<>"{}|\\^`\[\]]+\.(?:png|jpg|jpeg|gif|webp|svg))'
        # Pattern to find markdown images
        markdown_img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        
        for comment in comments:
            if isinstance(comment, dict):
                text = comment.get('comment_text', '')
                if text:
                    # Find direct image URLs
                    url_matches = re.findall(image_url_pattern, text, re.IGNORECASE)
                    for url in url_matches:
                        images.append({
                            'url': url,
                            'title': 'Image from comment',
                            'source': 'comment',
                            'is_image': True
                        })
                    
                    # Find markdown images
                    md_matches = re.findall(markdown_img_pattern, text)
                    for alt_text, url in md_matches:
                        images.append({
                            'url': url,
                            'title': alt_text or 'Image from comment',
                            'source': 'comment',
                            'is_image': True
                        })
        
        return images
    
    def _is_image_file(self, text: str) -> bool:
        """Check if text contains image file extension"""
        if not text:
            return False
        image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp']
        text_lower = text.lower()
        return any(ext in text_lower for ext in image_extensions)
    
    def get_task_comments(self, task_id: str) -> List[Dict]:
        """Get all comments for a task including nested replies"""
        comments = []
        
        if not task_id:
            return comments
        
        try:
            comments_url = f"{self.base_url}/task/{task_id}/comment"
            response = requests.get(comments_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                raw_comments = data.get('comments', [])
                
                # Process and clean comments
                for comment in raw_comments:
                    processed_comment = {
                        'id': comment.get('id'),
                        'comment_text': self._clean_comment_text(comment.get('comment', [])),
                        'user': comment.get('user', {}),
                        'date': self._format_timestamp(comment.get('date')),
                        'resolved': comment.get('resolved', False),
                        'assignee': comment.get('assignee', {})
                    }
                    
                    # Check for Slack URLs in comments
                    comment_text = processed_comment['comment_text']
                    if comment_text and 'slack.com' in comment_text:
                        slack_match = re.search(r'https://[^/]*slack\.com/archives/[A-Z0-9]+/p[0-9]+', comment_text)
                        if slack_match:
                            processed_comment['slack_url'] = slack_match.group(0)
                    
                    # Only add if there's actual text
                    if processed_comment['comment_text']:
                        comments.append(processed_comment)
                
                # Sort by date (newest first)
                comments.sort(key=lambda x: x.get('date', ''), reverse=True)
            
        except Exception as e:
            print(f"      ❌ Error fetching comments for task {task_id}: {str(e)[:100]}")
        
        return comments
    
    def extract_slack_thread_url(self, task_data: Dict, comments: List[Dict]) -> Optional[str]:
        """Extract Slack thread URL from task data or comments"""
        slack_pattern = r'https://[^/\s]*slack\.com/archives/[A-Z0-9]+/p[0-9]+'
        
        # 1. Check task description
        description = task_data.get('description', '') or ''
        if description:
            match = re.search(slack_pattern, description)
            if match:
                return match.group(0)
        
        # 2. Check markdown description
        markdown_desc = task_data.get('markdown_description', '') or ''
        if markdown_desc:
            match = re.search(slack_pattern, markdown_desc)
            if match:
                return match.group(0)
        
        # 3. Check comments
        for comment in comments:
            if isinstance(comment, dict):
                # Check if we already found a Slack URL in this comment
                if 'slack_url' in comment:
                    return comment['slack_url']
                
                # Otherwise check the comment text
                text = comment.get('comment_text', '')
                if text:
                    match = re.search(slack_pattern, text)
                    if match:
                        return match.group(0)
        
        # 4. Check custom fields for Slack integration
        custom_fields = task_data.get('custom_fields', [])
        for field in custom_fields:
            if isinstance(field, dict):
                field_name = field.get('name', '').lower()
                field_value = field.get('value', '')
                
                # Check if this is a Slack-related field
                if 'slack' in field_name or 'thread' in field_name:
                    if field_value and 'slack.com' in str(field_value):
                        match = re.search(slack_pattern, str(field_value))
                        if match:
                            return match.group(0)
        
        # 5. Check attachments or linked items
        attachments = task_data.get('attachments', [])
        for attachment in attachments:
            if isinstance(attachment, dict):
                title = attachment.get('title', '').lower()
                url = attachment.get('url', '')
                if 'slack' in title and url:
                    match = re.search(slack_pattern, url)
                    if match:
                        return match.group(0)
        
        return None
    
    def get_task_activity_timeline(self, task_id: str) -> List[Dict]:
        """Get task activity timeline including status changes"""
        activities = []
        
        if not task_id:
            return activities
        
        try:
            # Try to get task history/activity
            history_url = f"{self.base_url}/task/{task_id}/history"
            response = requests.get(history_url, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                history_data = response.json()
                for item in history_data.get('history', []):
                    activity = {
                        'date': self._format_timestamp(item.get('date')),
                        'user': item.get('user', {}).get('username', 'System'),
                        'field': item.get('field', ''),
                        'before': item.get('before', ''),
                        'after': item.get('after', '')
                    }
                    activities.append(activity)
        except:
            # If history endpoint fails, at least add basic info
            pass
        
        return activities
    
    def extract_custom_fields(self, task_data: Dict) -> Dict:
        """Extract and format custom fields from task data"""
        custom_fields = {}
        
        try:
            fields = task_data.get('custom_fields', [])
            
            for field in fields:
                field_name = field.get('name', 'Unknown Field')
                field_value = self._extract_field_value(field)
                
                if field_value:
                    custom_fields[field_name] = field_value
                    
                    # Special handling for Slack-related fields
                    if 'slack' in field_name.lower():
                        custom_fields['slack_field_found'] = True
        
        except Exception as e:
            print(f"      ⚠️ Error extracting custom fields: {str(e)[:100]}")
        
        return custom_fields
    
    def _clean_comment_text(self, comment_data) -> str:
        """Clean and extract text from comment data"""
        if isinstance(comment_data, str):
            return comment_data.strip()
        
        if isinstance(comment_data, list):
            # ClickUp comments can be structured as blocks
            text_parts = []
            for block in comment_data:
                if isinstance(block, dict):
                    # Handle different block types
                    if 'text' in block:
                        text_parts.append(block['text'])
                    elif 'string' in block:
                        text_parts.append(block['string'])
                    elif 'content' in block:
                        # Nested content blocks
                        content = block['content']
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and 'text' in item:
                                    text_parts.append(item['text'])
                                elif isinstance(item, str):
                                    text_parts.append(item)
                        elif isinstance(content, str):
                            text_parts.append(content)
                elif isinstance(block, str):
                    text_parts.append(block)
            
            return ' '.join(text_parts).strip()
        
        if isinstance(comment_data, dict):
            # Try to extract text from dict format
            if 'text' in comment_data:
                return comment_data['text']
            elif 'content' in comment_data:
                return str(comment_data['content'])
        
        return ""
    
    def _extract_field_value(self, field: Dict) -> str:
        """Extract value from a custom field"""
        field_type = field.get('type', '')
        
        if field_type == 'drop_down':
            # Handle dropdown fields
            type_config = field.get('type_config', {})
            if type_config:
                options = type_config.get('options', [])
                value = field.get('value')
                if value is not None and options:
                    for option in options:
                        if str(option.get('orderindex')) == str(value) or option.get('id') == value:
                            return option.get('name', '')
        
        elif field_type in ['text', 'short_text', 'long_text']:
            return field.get('value', '')
        
        elif field_type == 'number':
            value = field.get('value')
            return str(value) if value is not None else ''
        
        elif field_type == 'currency':
            value = field.get('value')
            return f"${value}" if value is not None else ''
        
        elif field_type == 'date':
            value = field.get('value')
            if value:
                return self._format_timestamp(value)
        
        elif field_type == 'url':
            return field.get('value', '')
        
        elif field_type == 'email':
            return field.get('value', '')
        
        elif field_type == 'phone':
            return field.get('value', '')
        
        elif field_type == 'checkbox':
            value = field.get('value')
            return 'Yes' if value else 'No'
        
        else:
            # Default: try to get value as string
            value = field.get('value')
            return str(value) if value else ''
        
        return ''
    
    def _format_timestamp(self, timestamp) -> str:
        """Format timestamp to readable date"""
        if not timestamp:
            return ''
        
        try:
            if isinstance(timestamp, str):
                # If it's already a formatted date string, return it
                if '-' in timestamp or '/' in timestamp:
                    return timestamp
                # Try to parse as timestamp
                timestamp = float(timestamp)
            
            # Convert milliseconds to seconds if needed
            if timestamp > 10000000000:
                timestamp = timestamp / 1000
            
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M')
        
        except Exception:
            return str(timestamp)