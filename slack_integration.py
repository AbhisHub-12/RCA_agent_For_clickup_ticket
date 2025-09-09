# slack_integration.py - Enhanced version with image and link extraction
"""
Enhanced Slack Integration for RCA Report Generation
Extracts messages, images, files, and console links from Slack threads
"""

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from typing import List, Dict, Optional, Tuple
import yaml
import re
from datetime import datetime, timedelta

class SlackIntegration:
    def __init__(self, config_path="config.yaml"):
        """Initialize Slack client"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            if not config.get('slack', {}).get('bot_token'):
                raise ValueError("Slack bot token not found in config")
            
            self.client = WebClient(token=config['slack']['bot_token'])
            self.channels_cache = {}
            
            # Test connection
            self.test_connection()
            print(f"   ✅ Slack integration initialized")
            
        except Exception as e:
            print(f"   ❌ Slack integration failed: {str(e)}")
            raise
    
    def test_connection(self):
        """Test Slack connection"""
        try:
            result = self.client.auth_test()
            self.bot_name = result.get('user', 'Bot')
            self.team_name = result.get('team', 'Unknown')
            return True
        except SlackApiError as e:
            print(f"   ❌ Slack connection test failed: {e}")
            return False
    
    def extract_slack_url_from_ticket(self, clickup_data: Dict) -> Optional[str]:
        """Extract Slack thread URL from ClickUp ticket data"""
        if not clickup_data:
            return None
        
        slack_pattern = r'https://[^/]*slack\.com/archives/[A-Z0-9]+/p[0-9]+'
        
        # Check description
        description = clickup_data.get('description', '')
        if description:
            match = re.search(slack_pattern, description)
            if match:
                return match.group(0)
        
        # Check comments
        comments = clickup_data.get('comments', [])
        for comment in comments:
            if isinstance(comment, dict):
                text = comment.get('comment_text', '')
                if text:
                    match = re.search(slack_pattern, text)
                    if match:
                        return match.group(0)
        
        return None
    
    def get_thread_with_attachments(self, slack_url: str) -> Dict:
        """Get thread messages with images, files, and links"""
        result = {
            'messages': [],
            'images': [],
            'files': [],
            'console_links': [],
            'error_screenshots': [],
            'code_snippets': []
        }
        
        if not slack_url:
            return result
        
        try:
            # Parse Slack URL
            url_parts = slack_url.split('/')
            if len(url_parts) >= 6:
                channel_id = url_parts[-2]
                timestamp_str = url_parts[-1]
                
                # Convert timestamp
                if timestamp_str.startswith('p'):
                    timestamp_str = timestamp_str[1:]
                    timestamp = f"{timestamp_str[:10]}.{timestamp_str[10:]}"
                    
                    # Get thread replies
                    thread_result = self.client.conversations_replies(
                        channel=channel_id,
                        ts=timestamp,
                        limit=200  # Get more messages to capture full conversation
                    )
                    
                    for message in thread_result.get("messages", []):
                        # Extract user and text
                        user_id = message.get("user", "")
                        username = self._get_username(user_id) if user_id else "Unknown"
                        text = message.get("text", "").strip()
                        
                        # Clean and add message text
                        if text:
                            clean_text = self._clean_message_text(text)
                            timestamp = message.get("ts", "")
                            if timestamp:
                                try:
                                    dt = datetime.fromtimestamp(float(timestamp))
                                    time_str = dt.strftime("%m/%d %H:%M")
                                    result['messages'].append(f"[{time_str}] {username}: {clean_text}")
                                except:
                                    result['messages'].append(f"[{username}]: {clean_text}")
                            
                            # Extract console/dashboard links
                            console_links = self._extract_console_links(text)
                            result['console_links'].extend(console_links)
                        
                        # Extract attachments (images and files)
                        attachments = message.get("files", [])
                        for attachment in attachments:
                            self._process_attachment(attachment, result, username)
                        
                        # Extract code blocks
                        blocks = message.get("blocks", [])
                        for block in blocks:
                            if block.get("type") == "rich_text":
                                for element in block.get("elements", []):
                                    for item in element.get("elements", []):
                                        if item.get("type") == "rich_text_preformatted":
                                            code = item.get("elements", [{}])[0].get("text", "")
                                            if code:
                                                result['code_snippets'].append({
                                                    'code': code,
                                                    'user': username,
                                                    'timestamp': time_str if 'time_str' in locals() else ""
                                                })
        
        except SlackApiError as e:
            print(f"      ⚠️ Error getting thread: {str(e)[:50]}")
        except Exception as e:
            print(f"      ❌ Unexpected error: {str(e)[:50]}")
        
        return result
    
    def _process_attachment(self, attachment: Dict, result: Dict, username: str):
        """Process Slack attachment (image or file)"""
        if not isinstance(attachment, dict):
            return
        
        file_type = attachment.get("mimetype", "")
        file_name = attachment.get("name", "")
        file_title = attachment.get("title", file_name)
        
        # Common file info
        file_info = {
            'title': file_title,
            'name': file_name,
            'url': attachment.get("url_private", attachment.get("permalink", "")),
            'thumb_url': attachment.get("thumb_360", attachment.get("thumb_480", "")),
            'user': username,
            'timestamp': attachment.get("timestamp", ""),
            'size': attachment.get("size", 0)
        }
        
        # Categorize by type
        if file_type.startswith("image/") or any(ext in file_name.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif']):
            # It's an image
            file_info['type'] = 'image'
            
            # Check if it's likely an error screenshot
            if any(keyword in file_name.lower() or keyword in file_title.lower() 
                   for keyword in ['error', 'issue', 'bug', 'fail', 'exception', 'console', 'log']):
                result['error_screenshots'].append(file_info)
            else:
                result['images'].append(file_info)
        
        elif file_type in ["text/plain", "application/json", "text/csv", "application/pdf"]:
            # It's a file (log, config, etc.)
            file_info['type'] = file_type
            result['files'].append(file_info)
    
    def _extract_console_links(self, text: str) -> List[Dict]:
        """Extract console/dashboard links from message text"""
        console_links = []
        
        # Patterns for various console/dashboard URLs
        console_patterns = [
            # AWS Console
            (r'https://[^/]*console\.aws\.amazon\.com[^\s<>"{}|\\^`\[\]]+', 'AWS Console'),
            (r'https://[^/]*\.console\.aws\.amazon\.com[^\s<>"{}|\\^`\[\]]+', 'AWS Console'),
            
            # GCP Console
            (r'https://console\.cloud\.google\.com[^\s<>"{}|\\^`\[\]]+', 'GCP Console'),
            
            # Azure Portal
            (r'https://portal\.azure\.com[^\s<>"{}|\\^`\[\]]+', 'Azure Portal'),
            
            # Kubernetes Dashboard
            (r'https://[^/]*kubernetes[^\s<>"{}|\\^`\[\]]*dashboard[^\s<>"{}|\\^`\[\]]+', 'K8s Dashboard'),
            
            # Grafana
            (r'https://[^/]*grafana[^\s<>"{}|\\^`\[\]]+', 'Grafana'),
            
            # DataDog
            (r'https://app\.datadoghq[^\s<>"{}|\\^`\[\]]+', 'DataDog'),
            
            # New Relic
            (r'https://[^/]*newrelic[^\s<>"{}|\\^`\[\]]+', 'New Relic'),
            
            # Generic monitoring/console URLs
            (r'https://[^/]*(console|dashboard|monitor|portal|admin)[^\s<>"{}|\\^`\[\]]+', 'Console/Dashboard')
        ]
        
        for pattern, console_type in console_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Clean up the URL
                clean_url = match.strip()
                if clean_url.endswith('>'):
                    clean_url = clean_url[:-1]
                
                console_links.append({
                    'url': clean_url,
                    'type': console_type,
                    'context': text[:100] if len(text) > 100 else text  # Include some context
                })
        
        return console_links
    
    def get_messages_with_media(self, clickup_url: str, clickup_data: Dict = None) -> Dict:
        """Get messages with all media (images, files, links) from Slack thread"""
        result = {
            'messages': [],
            'images': [],
            'files': [],
            'console_links': [],
            'error_screenshots': [],
            'code_snippets': []
        }
        
        # First, try to extract Slack URL from the ticket
        slack_url = None
        if clickup_data:
            slack_url = self.extract_slack_url_from_ticket(clickup_data)
        
        if slack_url:
            print(f"      📎 Extracting Slack thread with attachments...")
            thread_data = self.get_thread_with_attachments(slack_url)
            
            # Merge results
            result.update(thread_data)
            
            # Report what was found
            if thread_data['images']:
                print(f"      🖼️ Found {len(thread_data['images'])} images")
            if thread_data['error_screenshots']:
                print(f"      📸 Found {len(thread_data['error_screenshots'])} error screenshots")
            if thread_data['console_links']:
                print(f"      🔗 Found {len(thread_data['console_links'])} console links")
            if thread_data['files']:
                print(f"      📄 Found {len(thread_data['files'])} files")
            if thread_data['code_snippets']:
                print(f"      💻 Found {len(thread_data['code_snippets'])} code snippets")
        
        # If no direct Slack URL, try searching for mentions
        elif clickup_url:
            threads = self.find_clickup_threads(clickup_url)
            if threads:
                for thread in threads[:1]:  # Process first matching thread
                    channel = thread.get("channel")
                    timestamp = thread.get("timestamp")
                    if channel and timestamp:
                        slack_url = f"https://slack.com/archives/{channel}/p{timestamp.replace('.', '')}"
                        thread_data = self.get_thread_with_attachments(slack_url)
                        result.update(thread_data)
                        break
        
        # Fallback to just messages if no thread found
        if not result['messages'] and not slack_url:
            result['messages'] = ["No Slack thread found. Link thread in ClickUp for better analysis."]
        
        return result
    
    def find_clickup_threads(self, clickup_url: str) -> List[Dict]:
        """Find Slack threads mentioning the ClickUp ticket"""
        threads = []
        
        if not clickup_url:
            return threads
        
        # Extract task ID from URL
        task_id = clickup_url.split('/')[-1] if clickup_url else None
        
        try:
            # Get list of channels
            result = self.client.conversations_list(
                types="public_channel,private_channel",
                limit=100
            )
            
            channels = result.get('channels', [])
            
            for channel in channels:
                if channel.get('is_archived', False):
                    continue
                
                channel_id = channel['id']
                channel_name = channel.get('name', 'unknown')
                
                try:
                    # Search recent messages in channel
                    history = self.client.conversations_history(
                        channel=channel_id,
                        limit=100
                    )
                    
                    messages = history.get('messages', [])
                    
                    for message in messages:
                        text = message.get('text', '')
                        
                        # Check if message contains ClickUp URL or task ID
                        if clickup_url in text or (task_id and task_id in text):
                            threads.append({
                                "channel": channel_id,
                                "timestamp": message.get('ts'),
                                "text": text[:200],
                                "channel_name": channel_name
                            })
                            break
                            
                except SlackApiError:
                    continue
                    
        except Exception as e:
            print(f"      ❌ Error searching channels: {str(e)[:50]}")
        
        return threads
    
    def _get_username(self, user_id: str) -> str:
        """Get username from user ID with caching"""
        if not user_id:
            return "Unknown"
        
        if not hasattr(self, '_user_cache'):
            self._user_cache = {}
        
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        
        try:
            result = self.client.users_info(user=user_id)
            user = result.get("user", {})
            username = user.get("real_name") or user.get("name") or "Unknown"
            self._user_cache[user_id] = username
            return username
        except:
            return f"User_{user_id[-4:]}"
    
    def _clean_message_text(self, text: str) -> str:
        """Clean and format message text"""
        if not text:
            return ""
        
        # Remove Slack user mentions
        text = re.sub(r'<@U[A-Z0-9]+>', '@user', text)
        
        # Remove Slack channel mentions
        text = re.sub(r'<#C[A-Z0-9]+\|([^>]+)>', r'#\1', text)
        
        # Clean up Slack URLs (keep the URL part)
        text = re.sub(r'<(https?://[^|>]+)(?:\|[^>]+)?>', r'\1', text)
        
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Limit length
        if len(text) > 1000:
            text = text[:997] + "..."
        
        return text