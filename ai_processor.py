# ai_processor.py - Final Production Version
"""
AI Processor for RCA Report Generation - Production Ready
- Universal technical content extraction (not limited to specific tools)
- Returns appropriate empty RCA when no conversation exists
- Filters bot messages while preserving engineer content
- Analyzes actual conversation without assumptions
- Proper formatting with line breaks between steps
"""

import openai
from typing import Dict, List, Optional, Union, Tuple
import yaml
from pathlib import Path
import json
import re
from datetime import datetime

class RCAAIProcessor:
    def __init__(self, config_path="config.yaml", debug_mode=False):
        """Initialize AI processor with config"""
        self.debug_mode = debug_mode
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            if not config.get('openai', {}).get('api_key'):
                raise ValueError("OpenAI API key not found in config")
            
            self.model = config['openai'].get('model', 'gpt-4o')
            openai.api_key = config['openai']['api_key']
            
            print(f"   ✅ AI Processor initialized with model: {self.model}")
            if self.debug_mode:
                print("   🔍 Debug mode enabled")
        except Exception as e:
            print(f"   ❌ AI Processor initialization failed: {str(e)}")
            raise
    
    def analyze_ticket_for_rca(self, clickup_data: Dict, slack_data: Union[List[str], Dict]) -> Dict:
        """
        Main entry point - Analyze ticket and generate comprehensive RCA
        """
        try:
            if self.debug_mode:
                print("\n=== DEBUG: Starting RCA Analysis ===")
            
            # 1. Normalize data formats
            slack_media = self._normalize_slack_data(slack_data)
            
            # 2. Filter out bot messages and automation content
            clickup_data_filtered = self._filter_bot_content(clickup_data)
            slack_media_filtered = self._filter_slack_bot_content(slack_media)
            
            # 3. Build complete conversation
            full_conversation = self._build_complete_conversation(clickup_data_filtered, slack_media_filtered)
            
            # Check if conversation is actually empty
            if not full_conversation.strip() or len(full_conversation.strip()) < 50:
                if self.debug_mode:
                    print("DEBUG: No meaningful conversation found")
                return self._create_empty_rca(clickup_data)
            
            # 4. Extract technical content (any type)
            extracted_content = self._extract_all_technical_content(clickup_data_filtered, slack_media_filtered)
            
            if self.debug_mode:
                print(f"DEBUG: Conversation length: {len(full_conversation)} chars")
                print(f"DEBUG: Extracted {len(extracted_content['commands'])} commands")
                print(f"DEBUG: Extracted {len(extracted_content['code_blocks'])} code blocks")
            
            # 5. Extract all media with original URLs
            media_content = self._extract_all_media_content(clickup_data_filtered, slack_media_filtered)
            
            # 6. Get metadata and engineers
            metadata = self._extract_metadata(clickup_data)
            engineers = self._extract_engineers(clickup_data, slack_media)
            
            # 7. Use AI to analyze and structure RCA
            rca_result = self._ai_analyze_and_structure(
                conversation=full_conversation,
                extracted_content=extracted_content,
                media_content=media_content,
                metadata=metadata,
                engineers=engineers
            )
            
            # 8. Final validation and media attachment
            final_result = self._finalize_rca(rca_result, media_content)
            
            return final_result
            
        except Exception as e:
            print(f"      ❌ Analysis failed: {str(e)}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()
            return self._create_empty_rca(clickup_data)
    
    def _filter_bot_content(self, clickup_data: Dict) -> Dict:
        """Filter out bot messages and automation content from ClickUp data"""
        if not clickup_data:
            return clickup_data
        
        # Bot identifiers - only filter clear automation
        bot_patterns = [
            'clickbot', 'automation #', 'webhook', 'form submission'
        ]
        
        if 'comments' in clickup_data:
            filtered_comments = []
            for comment in clickup_data['comments']:
                if isinstance(comment, dict):
                    user = comment.get('user', {})
                    username = ''
                    if isinstance(user, dict):
                        username = (user.get('username', '') or user.get('name', '')).lower()
                    
                    comment_text = self._get_comment_full_text(comment).lower()
                    
                    # Only filter if clearly a bot
                    is_bot = False
                    for pattern in bot_patterns:
                        if pattern in username:
                            is_bot = True
                            break
                    
                    # Check for pure automation messages
                    if not is_bot and comment_text:
                        automation_phrases = [
                            'clickbot (automations) set',
                            'clickbot (form submission)',
                            'clickbot (automations) added tag',
                            'clickbot (automations) also added'
                        ]
                        for phrase in automation_phrases:
                            if comment_text.startswith(phrase):
                                is_bot = True
                                break
                    
                    if not is_bot:
                        filtered_comments.append(comment)
            
            clickup_data['comments'] = filtered_comments
        
        return clickup_data
    
    def _filter_slack_bot_content(self, slack_media: Dict) -> Dict:
        """Filter out bot messages from Slack data"""
        if not slack_media or not slack_media.get('messages'):
            return slack_media
        
        bot_patterns = [
            '[bot]:', '[automation]:', '[system]:', '[webhook]:'
        ]
        
        filtered_messages = []
        for msg in slack_media['messages']:
            if msg and not msg.startswith('No '):
                msg_lower = msg.lower()
                is_bot = any(pattern in msg_lower[:50] for pattern in bot_patterns)
                if not is_bot:
                    filtered_messages.append(msg)
        
        slack_media['messages'] = filtered_messages
        return slack_media
    
    def _normalize_slack_data(self, slack_data: Union[List[str], Dict]) -> Dict:
        """Normalize Slack data to consistent dictionary format"""
        if isinstance(slack_data, dict):
            return slack_data
        elif isinstance(slack_data, list):
            return {
                'messages': slack_data,
                'images': [],
                'console_links': [],
                'error_screenshots': [],
                'code_snippets': [],
                'files': []
            }
        return {
            'messages': [],
            'images': [],
            'console_links': [],
            'error_screenshots': [],
            'code_snippets': [],
            'files': []
        }
    
    def _extract_all_technical_content(self, clickup_data: Dict, slack_media: Dict) -> Dict:
        """
        Extract ALL types of technical content - generic approach
        """
        extracted = {
            'code_blocks': [],
            'commands': [],
            'error_messages': [],
            'configurations': [],
            'console_links': slack_media.get('console_links', [])
        }
        
        # Extract from ClickUp
        if clickup_data:
            if clickup_data.get('description'):
                self._extract_from_text(clickup_data['description'], extracted, 'description')
            
            for i, comment in enumerate(clickup_data.get('comments', [])):
                if isinstance(comment, dict):
                    comment_text = self._get_comment_full_text(comment)
                    if comment_text:
                        user = self._get_comment_user(comment)
                        self._extract_from_text(comment_text, extracted, user)
        
        # Extract from Slack messages
        for i, msg in enumerate(slack_media.get('messages', [])):
            if msg and not msg.startswith('No '):
                self._extract_from_text(str(msg), extracted, f'slack_{i}')
        
        # Add Slack code snippets
        for snippet in slack_media.get('code_snippets', []):
            extracted['code_blocks'].append({
                'code': snippet.get('code', ''),
                'language': snippet.get('language', 'text'),
                'source': 'slack_snippet',
                'user': snippet.get('user', 'Unknown')
            })
        
        return extracted
    
    def _extract_from_text(self, text: str, extracted: Dict, source: str):
        """
        Extract technical content from text - generic approach for any technology
        """
        if not text:
            return
        
        # 1. Look for terminal/command output patterns (generic)
        if self._looks_like_command_output(text):
            lines = text.split('\n')
            current_block = []
            in_output = False
            
            for line in lines:
                # Check if line looks like a command or output
                if self._is_command_line(line):
                    if current_block and len(current_block) > 1:
                        # Save previous block
                        extracted['code_blocks'].append({
                            'code': '\n'.join(current_block),
                            'language': 'bash',
                            'source': source
                        })
                    current_block = [line]
                    in_output = True
                elif in_output and self._is_output_line(line):
                    current_block.append(line)
                elif in_output and not line.strip():
                    # Empty line might end output
                    if len(current_block) > 2:
                        extracted['code_blocks'].append({
                            'code': '\n'.join(current_block),
                            'language': 'bash',
                            'source': source
                        })
                    current_block = []
                    in_output = False
            
            # Save any remaining block
            if current_block and len(current_block) > 1:
                extracted['code_blocks'].append({
                    'code': '\n'.join(current_block),
                    'language': 'bash',
                    'source': source
                })
        
        # 2. Code blocks with ```
        code_pattern = r'```([a-zA-Z]*)\n?([\s\S]*?)```'
        for match in re.finditer(code_pattern, text):
            language = match.group(1) or 'text'
            code = match.group(2).strip()
            if code:
                extracted['code_blocks'].append({
                    'code': code,
                    'language': language,
                    'source': source
                })
        
        # 3. Generic command extraction (any command-like pattern)
        command_patterns = [
            # Common CLI tools
            r'((?:sudo\s+)?[a-z]+[\w\-]*\s+[\w\-]+[^\n]*)',  # Generic command pattern
            r'(npm\s+[^\n]+)',
            r'(yarn\s+[^\n]+)',
            r'(pip\s+[^\n]+)',
            r'(python\s+[^\n]+)',
            r'(java\s+[^\n]+)',
            r'(mvn\s+[^\n]+)',
            r'(gradle\s+[^\n]+)',
            r'(curl\s+[^\n]+)',
            r'(wget\s+[^\n]+)',
            r'(apt-get\s+[^\n]+)',
            r'(yum\s+[^\n]+)',
            r'(brew\s+[^\n]+)',
            # Add any other technology-specific patterns as needed
        ]
        
        for pattern in command_patterns:
            for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
                command = match.group(1).strip()
                # Filter out false positives
                if len(command) > 10 and not command.startswith('//') and not command.startswith('#'):
                    # Avoid duplicates
                    if not any(cmd['command'] == command for cmd in extracted['commands']):
                        extracted['commands'].append({
                            'command': command,
                            'source': source
                        })
        
        # 4. Error messages (generic)
        error_patterns = [
            r'([Ee]rror:\s*[^\n]+)',
            r'([Ee]xception:\s*[^\n]+)',
            r'([Ff]ailed:\s*[^\n]+)',
            r'([Ww]arning:\s*[^\n]+)',
            r'(FATAL:\s*[^\n]+)',
            r'(ERROR\s+\[\d+\]:[^\n]+)',
            r'(\[ERROR\][^\n]+)',
            r'(Traceback[^\n]+)',
            r'(panic:[^\n]+)',
            r'(fatal:[^\n]+)',
        ]
        
        for pattern in error_patterns:
            for match in re.finditer(pattern, text):
                error = match.group(1).strip()
                if error and not any(err['error'] == error for err in extracted['error_messages']):
                    extracted['error_messages'].append({
                        'error': error,
                        'source': source
                    })
        
        # 5. Inline code with backticks
        inline_pattern = r'`([^`]+)`'
        for match in re.finditer(inline_pattern, text):
            code = match.group(1).strip()
            if len(code) > 5:  # Skip very short snippets
                # Check if it looks like a command or code
                if any(char in code for char in [' ', '/', '-', '.', '(', ')', '=']):
                    if not any(cmd['command'] == code for cmd in extracted['commands']):
                        extracted['commands'].append({
                            'command': code,
                            'source': source
                        })
        
        # 6. Configuration blocks (JSON, YAML, XML)
        # JSON
        json_pattern = r'(\{(?:[^{}]|(?:\{[^{}]*\}))*\})'
        for match in re.finditer(json_pattern, text):
            json_str = match.group(1)
            try:
                if len(json_str) > 30:
                    json_obj = json.loads(json_str)
                    formatted = json.dumps(json_obj, indent=2)
                    extracted['configurations'].append({
                        'config': formatted,
                        'type': 'json',
                        'source': source
                    })
            except:
                pass
        
        # 7. URLs (any console/dashboard/monitoring links)
        url_pattern = r'(https?://[^\s<>"{}|\\^`\[\]]+)'
        for match in re.finditer(url_pattern, text):
            url = match.group(1)
            # Check if it's a technical/dashboard link
            tech_keywords = [
                'console', 'dashboard', 'portal', 'admin', 'monitor',
                'grafana', 'datadog', 'newrelic', 'kibana', 'splunk',
                'jenkins', 'gitlab', 'github', 'bitbucket', 'jira',
                'confluence', 'aws', 'azure', 'gcp', 'cloud'
            ]
            if any(keyword in url.lower() for keyword in tech_keywords):
                if not any(link['url'] == url for link in extracted['console_links']):
                    extracted['console_links'].append({
                        'url': url,
                        'type': 'Technical Link',
                        'source': source,
                        'context': text[max(0, match.start()-50):min(len(text), match.end()+50)]
                    })
    
    def _looks_like_command_output(self, text: str) -> bool:
        """Check if text looks like command output"""
        # Generic indicators of command output
        indicators = [
            # Table headers
            'NAME', 'STATUS', 'VERSION', 'TYPE', 'ID', 'CREATED',
            # Separators
            '----', '====', '****',
            # Common output patterns
            re.compile(r'^\d+\s+\w+', re.MULTILINE),  # Numbered lists
            re.compile(r'^\w+\s+\d+\s+\w+', re.MULTILINE),  # Table rows
            re.compile(r'^\[\w+\]', re.MULTILINE),  # Log format
            re.compile(r'^\s*\*\s+\w+', re.MULTILINE),  # Bullet points
        ]
        
        matches = 0
        for indicator in indicators:
            if isinstance(indicator, str):
                if indicator in text:
                    matches += 1
            else:
                if indicator.search(text):
                    matches += 1
        
        return matches >= 2  # At least 2 indicators
    
    def _is_command_line(self, line: str) -> bool:
        """Check if line looks like a command"""
        line = line.strip()
        if not line:
            return False
        
        # Common command indicators
        command_starts = [
            '$', '#', '>', '~',
            'root@', 'user@', 'admin@',
            'C:\\', 'PS ',  # Windows
        ]
        
        for start in command_starts:
            if line.startswith(start):
                return True
        
        # Check for common command structures
        # Word followed by arguments
        if re.match(r'^[a-z]+[\w\-]*\s+[\-\w]+', line, re.IGNORECASE):
            return True
        
        return False
    
    def _is_output_line(self, line: str) -> bool:
        """Check if line looks like command output"""
        if not line:
            return False
        
        # Table-like output (has multiple spaces or tabs)
        if '  ' in line or '\t' in line:
            return True
        
        # Structured data patterns
        patterns = [
            r'^\s*\d+[\.\)]\s+',  # Numbered list
            r'^\s*[\*\-\+]\s+',  # Bullet list
            r'^\w+[\-\w]*\s*[:=]\s*',  # Key-value pairs
            r'^\s*\[\w+\]',  # Log format
            r'^\d{4}-\d{2}-\d{2}',  # Date stamps
        ]
        
        for pattern in patterns:
            if re.match(pattern, line):
                return True
        
        return False
    
    def _build_complete_conversation(self, clickup_data: Dict, slack_media: Dict) -> str:
        """
        Build complete conversation for AI analysis
        """
        parts = []
        
        # ClickUp content
        if clickup_data:
            if clickup_data.get('name'):
                parts.append(f"TICKET TITLE: {clickup_data['name']}\n")
            
            if clickup_data.get('description'):
                desc = self._clean_text(clickup_data['description'])
                if desc:
                    parts.append("INITIAL DESCRIPTION:")
                    parts.append(desc)
                    parts.append("")
            
            comments = clickup_data.get('comments', [])
            if comments:
                parts.append("CONVERSATION:")
                for comment in comments:
                    if isinstance(comment, dict):
                        text = self._get_comment_full_text(comment)
                        if text:
                            user = self._get_comment_user(comment)
                            parts.append(f"\n[{user}]:")
                            parts.append(text)
                            parts.append("")
        
        # Slack conversation
        if slack_media.get('messages'):
            if not parts:
                parts.append("SLACK CONVERSATION:")
            else:
                parts.append("\nADDITIONAL SLACK MESSAGES:")
            
            for msg in slack_media['messages']:
                if msg and not msg.startswith('No '):
                    parts.append(self._clean_text(str(msg)))
                    parts.append("")
        
        return "\n".join(parts)
    
    def _extract_all_media_content(self, clickup_data: Dict, slack_media: Dict) -> Dict:
        """Extract all media with original URLs"""
        media = {
            'images': [],
            'error_screenshots': [],
            'console_links': slack_media.get('console_links', []),
            'attachments': [],
            'files': slack_media.get('files', [])
        }
        
        # Process Slack images
        for img in slack_media.get('images', []):
            media['images'].append({
                'url': img.get('url', ''),
                'thumb_url': img.get('thumb_url', img.get('url', '')),
                'title': img.get('title', 'Image'),
                'source': 'slack'
            })
        
        for img in slack_media.get('error_screenshots', []):
            media['error_screenshots'].append({
                'url': img.get('url', ''),
                'thumb_url': img.get('thumb_url', img.get('url', '')),
                'title': img.get('title', 'Error Screenshot'),
                'source': 'slack'
            })
        
        # Process ClickUp attachments
        if clickup_data:
            for att in clickup_data.get('attachments', []):
                if isinstance(att, dict):
                    media['attachments'].append({
                        'url': att.get('url', ''),
                        'title': att.get('title', 'Attachment'),
                        'source': 'clickup'
                    })
        
        return media
    
    def _ai_analyze_and_structure(self, conversation: str, extracted_content: Dict, 
                                  media_content: Dict, metadata: Dict, 
                                  engineers: List[str]) -> Dict:
        """
        Use AI to analyze conversation and structure RCA
        """
        # Prepare content summary
        content_summary = self._prepare_content_summary(extracted_content, media_content)
        
        # Handle very long conversations
        if len(conversation) > 30000:
            conversation = self._intelligent_chunking(conversation, extracted_content)
        
        system_prompt = """You are creating RCA (Root Cause Analysis) reports from support tickets.
Analyze the conversation and create a structured report based on what actually happened.
Only include information that is present in the conversation.
If no debugging steps are mentioned, say so.
If no resolution is mentioned, say so.
Do not make assumptions or add information not in the conversation."""

        user_prompt = f"""Analyze this support ticket conversation and create an RCA report.

TICKET: {metadata.get('title', 'N/A')}
STATUS: {metadata.get('status', 'N/A')}
ENGINEERS: {', '.join(engineers) if engineers else 'Support Team'}

TECHNICAL CONTENT FOUND:
{content_summary}

CONVERSATION:
{conversation}

Based on the conversation above, create an RCA report with these sections:

1. **Summary of the Issue**: 
   - What problem was reported? 
   - Include any error messages or symptoms mentioned
   - Be specific about what wasn't working

2. **Steps to Debug**: 
   - List the actual debugging actions taken (numbered list)
   - Include any commands run or checks performed
   - Format commands in code blocks
   - If no debugging steps are mentioned, state: "No debugging steps were documented in the conversation."

3. **Steps to Resolution**: 
   - What was done to fix the issue?
   - Include specific actions taken
   - Format commands in code blocks
   - If no resolution is mentioned, state: "No resolution steps were documented in the conversation."

4. **Root Cause Analysis**: 
   - What caused the issue based on the investigation?
   - Be specific if the cause was identified
   - If not identified, state: "Root cause was not identified in the conversation."

IMPORTANT: 
- Only include information actually present in the conversation
- Use proper formatting with line breaks between numbered steps
- Put actual commands/code in ``` blocks
- Do not make up or assume steps that aren't mentioned

Return as JSON:
{{"summary": "...", "debug_steps": "...", "resolution_steps": "...", "root_cause": "..."}}"""

        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=4000
            )
            
            ai_response = response.choices[0].message.content.strip()
            result = self._parse_ai_response(ai_response)
            
            # Ensure proper formatting
            result = self._ensure_proper_formatting(result)
            
            return result
            
        except Exception as e:
            print(f"      ❌ AI error: {str(e)}")
            return self._create_structured_fallback(extracted_content, metadata, engineers)
    
    def _ensure_proper_formatting(self, result: Dict) -> Dict:
        """Ensure proper line breaks and formatting in RCA steps"""
        for field in ['debug_steps', 'resolution_steps']:
            if field in result and result[field]:
                text = result[field]
                
                # Fix formatting for numbered steps
                # Add double line break before numbered items (except first)
                text = re.sub(r'(?<!^)(\d+)\.\s*([A-Z])', r'\n\n\1. \2', text)
                
                # Ensure code blocks are properly separated
                text = re.sub(r'(```[^`]*```)\s*(\d+\.)', r'\1\n\n\2', text, flags=re.DOTALL)
                
                # Clean up excessive newlines
                text = re.sub(r'\n{3,}', '\n\n', text)
                
                # Remove leading/trailing whitespace
                text = text.strip()
                
                result[field] = text
        
        return result
    
    def _prepare_content_summary(self, extracted_content: Dict, media_content: Dict) -> str:
        """Prepare a summary of extracted content for AI context"""
        parts = []
        
        if extracted_content['error_messages']:
            parts.append("Errors found:")
            for err in extracted_content['error_messages'][:5]:
                parts.append(f"- {err['error']}")
        
        if extracted_content['commands']:
            parts.append("\nCommands found:")
            for cmd in extracted_content['commands'][:10]:
                parts.append(f"- {cmd['command']}")
        
        if extracted_content['code_blocks']:
            parts.append(f"\n{len(extracted_content['code_blocks'])} code blocks found")
        
        if media_content['console_links']:
            parts.append(f"{len(media_content['console_links'])} console/dashboard links found")
        
        return "\n".join(parts) if parts else "No technical content extracted"
    
    def _intelligent_chunking(self, conversation: str, extracted_content: Dict) -> str:
        """Chunk very long conversations while preserving important parts"""
        chunks = []
        
        # Keep beginning
        chunks.append(conversation[:10000])
        
        # Include error contexts
        for err in extracted_content.get('error_messages', [])[:3]:
            err_text = err['error']
            if err_text in conversation:
                idx = conversation.find(err_text)
                start = max(0, idx - 500)
                end = min(len(conversation), idx + len(err_text) + 500)
                chunks.append(f"\n[Error context]:\n{conversation[start:end]}")
        
        # Keep end
        chunks.append(f"\n[Final part]:\n{conversation[-10000:]}")
        
        return "\n".join(chunks)
    
    def _parse_ai_response(self, response: str) -> Dict:
        """Parse AI response safely"""
        # Clean response
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        
        # Extract JSON
        if '{' in response and '}' in response:
            response = response[response.index('{'):response.rindex('}')+1]
        
        # Remove control characters
        response = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', response)
        
        try:
            result = json.loads(response)
            # Ensure all fields exist
            for field in ['summary', 'debug_steps', 'resolution_steps', 'root_cause']:
                if field not in result:
                    result[field] = ""
            return result
        except json.JSONDecodeError:
            return self._extract_fields_manually(response)
    
    def _extract_fields_manually(self, text: str) -> Dict:
        """Extract fields when JSON parsing fails"""
        result = {
            "summary": "",
            "debug_steps": "",
            "resolution_steps": "",
            "root_cause": ""
        }
        
        patterns = {
            'summary': r'"summary"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',
            'debug_steps': r'"debug_steps"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',
            'resolution_steps': r'"resolution_steps"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',
            'root_cause': r'"root_cause"\s*:\s*"([^"]*(?:\\.[^"]*)*)"'
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.DOTALL)
            if match:
                content = match.group(1)
                # Unescape
                content = content.replace('\\n', '\n')
                content = content.replace('\\"', '"')
                content = content.replace('\\\\', '\\')
                content = content.replace('\\t', '\t')
                result[field] = content
        
        return result
    
    def _finalize_rca(self, rca_result: Dict, media_content: Dict) -> Dict:
        """Finalize RCA with media attachments"""
        rca_result['supporting_media'] = {
            'images': media_content.get('images', []),
            'error_screenshots': media_content.get('error_screenshots', []),
            'console_links': media_content.get('console_links', []),
            'attachments': media_content.get('attachments', []),
            'files': media_content.get('files', [])
        }
        
        return rca_result
    
    def _create_structured_fallback(self, extracted_content: Dict, metadata: Dict, 
                                   engineers: List[str]) -> Dict:
        """Create structured fallback when AI fails"""
        # Only create content if we actually have extracted content
        if not extracted_content['commands'] and not extracted_content['code_blocks']:
            return self._create_empty_rca({'name': metadata.get('title', '')})
        
        engineer = engineers[0] if engineers else "Engineer"
        
        debug_steps = []
        for i, cmd in enumerate(extracted_content.get('commands', [])[:5], 1):
            debug_steps.append(f"{i}. {cmd.get('source', engineer)} ran:\n```bash\n{cmd['command']}\n```")
        
        for i, block in enumerate(extracted_content.get('code_blocks', [])[:3], len(debug_steps)+1):
            debug_steps.append(f"{i}. Output:\n```{block['language']}\n{block['code'][:500]}\n```")
        
        return {
            "summary": metadata.get('title', 'Issue reported'),
            "debug_steps": "\n\n".join(debug_steps) if debug_steps else "No debugging steps documented",
            "resolution_steps": "No resolution steps documented",
            "root_cause": "Root cause not identified",
            "supporting_media": {}
        }
    
    def _create_empty_rca(self, clickup_data: Dict) -> Dict:
        """Create empty RCA when no conversation exists"""
        title = ""
        if isinstance(clickup_data, dict):
            title = clickup_data.get('name', 'Support Issue')
        
        return {
            "summary": title if title else "No issue description available",
            "debug_steps": "No debugging steps documented in the conversation",
            "resolution_steps": "No resolution steps documented in the conversation",
            "root_cause": "Root cause not identified in the conversation",
            "supporting_media": {
                'images': [],
                'error_screenshots': [],
                'console_links': [],
                'attachments': [],
                'files': []
            }
        }
    
    # Helper methods
    def _get_comment_full_text(self, comment: Dict) -> str:
        """Get full text from comment including code blocks"""
        if not isinstance(comment, dict):
            return ""
        
        # Try various field names that ClickUp might use
        text_fields = [
            'comment_text', 'text', 'message', 'content', 'comment', 
            'body', 'comment_body', 'description', 'value'
        ]
        
        for field in text_fields:
            if field in comment:
                data = comment[field]
                
                if isinstance(data, str):
                    return data
                
                elif isinstance(data, list):
                    parts = []
                    for item in data:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict):
                            # Check various nested fields
                            for subfield in ['text', 'value', 'content', 'string']:
                                if subfield in item:
                                    parts.append(str(item[subfield]))
                                    break
                            # Check for code blocks
                            if 'code' in item:
                                parts.append(f"```\n{item['code']}\n```")
                    
                    return '\n'.join(parts)
                
                elif isinstance(data, dict):
                    # Try to extract from nested structure
                    for subfield in ['text', 'value', 'content']:
                        if subfield in data:
                            return str(data[subfield])
        
        return ""
    
    def _get_comment_user(self, comment: Dict) -> str:
        """Get user from comment"""
        if isinstance(comment, dict):
            user = comment.get('user', {})
            if isinstance(user, dict):
                username = user.get('username') or user.get('name') or user.get('email', '').split('@')[0]
                return username or "Unknown"
            elif isinstance(user, str):
                return user
        return "Unknown"
    
    def _clean_text(self, text: str) -> str:
        """Clean text while preserving structure"""
        if not text:
            return ""
        text = str(text)
        # Remove control characters except newlines and tabs
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', ' ', text)
        return text.strip()
    
    def _extract_metadata(self, clickup_data: Dict) -> Dict:
        """Extract ticket metadata"""
        metadata = {'title': '', 'status': ''}
        if clickup_data:
            metadata['title'] = clickup_data.get('name', '')
            status = clickup_data.get('status', '')
            if isinstance(status, dict):
                metadata['status'] = status.get('status', '')
            else:
                metadata['status'] = str(status)
        return metadata
    
    def _extract_engineers(self, clickup_data: Dict, slack_media: Dict) -> List[str]:
        """Extract all engineer names, excluding bots"""
        engineers = set()
        
        if clickup_data:
            # From assignees
            for assignee in clickup_data.get('assignees', []):
                if isinstance(assignee, dict):
                    name = assignee.get('username') or assignee.get('name')
                    if name and name != "Unknown" and 'bot' not in name.lower():
                        engineers.add(name)
            
            # From comments
            for comment in clickup_data.get('comments', []):
                if isinstance(comment, dict):
                    user = comment.get('user', {})
                    if isinstance(user, dict):
                        name = user.get('username') or user.get('name')
                        if name and name != "Unknown" and 'bot' not in name.lower():
                            engineers.add(name)
        
        return list(engineers)