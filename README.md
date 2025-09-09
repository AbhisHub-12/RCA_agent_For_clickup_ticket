# RCA Report Generator

An automated Root Cause Analysis (RCA) report generation system that integrates ClickUp, Slack, and OpenAI to create comprehensive incident analysis reports with AI-powered insights.

## Features

- 📊 **Automated RCA Generation**: Fetches tickets from ClickUp and generates detailed RCA reports
- 🤖 **AI-Powered Analysis**: Uses OpenAI GPT-4 to analyze conversations and extract insights
- 💬 **Slack Integration**: Retrieves thread conversations, images, and console links from Slack
- 📸 **Media Extraction**: Captures screenshots, error images, and attachments from both ClickUp and Slack
- 📈 **Status Tracking**: Supports complete ClickUp workflow with Active, Done, and Closed statuses
- 🎨 **Interactive HTML Reports**: Beautiful, expandable reports with image galleries and clickable links
- 🔍 **Debug Mode**: Detailed logging for troubleshooting

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                           │
│                    (Command Line + Browser)                      │
└─────────────────┬───────────────────────────┬───────────────────┘
                  │                           │
                  ▼                           ▼
┌─────────────────────────────┐  ┌──────────────────────────────┐
│    1_python_script.py       │  │     HTML Report Output       │
│      (Main Controller)      │  │   (Interactive Dashboard)    │
└─────────┬───────────────────┘  └──────────────────────────────┘
          │
          ├──────────────┬──────────────┬──────────────┐
          ▼              ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   ClickUp    │ │    Slack     │ │   OpenAI     │ │   ClickUp    │
│   Basic API  │ │ Integration  │ │  Processor   │ │   Extended   │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │
       ▼                ▼                ▼                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                            │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   ClickUp    │    Slack     │   OpenAI     │    File System     │
│     API      │     API      │   GPT-4 API  │   (HTML Reports)   │
└──────────────┴──────────────┴──────────────┴────────────────────┘
```

### Data Flow Diagram

```mermaid
graph TD
    Start([User Runs Script]) --> DateRange[Select Date Range]
    DateRange --> FetchTickets[Fetch Tickets from ClickUp]
    
    FetchTickets --> ProcessTicket[Process Each Ticket]
    
    ProcessTicket --> GetClickUpData[Get Extended ClickUp Data]
    GetClickUpData --> GetComments[Extract Comments]
    GetClickUpData --> GetAttachments[Extract Attachments]
    
    ProcessTicket --> GetSlackData[Get Slack Thread Data]
    GetSlackData --> GetMessages[Extract Messages]
    GetSlackData --> GetImages[Extract Images/Screenshots]
    GetSlackData --> GetLinks[Extract Console Links]
    
    GetComments --> AIAnalysis[AI Analysis with GPT-4]
    GetMessages --> AIAnalysis
    GetImages --> AIAnalysis
    GetLinks --> AIAnalysis
    GetAttachments --> AIAnalysis
    
    AIAnalysis --> GenerateRCA[Generate RCA Components]
    GenerateRCA --> Summary[Issue Summary]
    GenerateRCA --> DebugSteps[Debug Steps]
    GenerateRCA --> Resolution[Resolution Steps]
    GenerateRCA --> RootCause[Root Cause]
    
    Summary --> BuildHTML[Build HTML Report]
    DebugSteps --> BuildHTML
    Resolution --> BuildHTML
    RootCause --> BuildHTML
    GetImages --> BuildHTML
    GetLinks --> BuildHTML
    GetAttachments --> BuildHTML
    
    BuildHTML --> SaveReport[Save HTML File]
    SaveReport --> OpenBrowser[Open in Browser]
    OpenBrowser --> End([Report Complete])
```

### Component Interaction Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTION FLOW                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. INITIALIZATION                                          │
│     ├── Load config.yaml                                   │
│     ├── Initialize AI Processor                            │
│     ├── Initialize Slack Client                            │
│     └── Initialize ClickUp Extended                        │
│                                                             │
│  2. DATA COLLECTION                                         │
│     ├── Fetch tickets from ClickUp API                     │
│     │   ├── Filter by date range                          │
│     │   ├── Include closed/done statuses                  │
│     │   └── Paginate through results                      │
│     │                                                      │
│     └── For each ticket:                                   │
│         ├── Get full task details                          │
│         ├── Extract comments                               │
│         ├── Get attachments/images                         │
│         └── Find Slack thread URL                          │
│                                                             │
│  3. SLACK INTEGRATION                                       │
│     ├── Parse Slack thread URL                             │
│     ├── Fetch thread messages                              │
│     ├── Extract images/screenshots                         │
│     ├── Extract console/dashboard links                    │
│     └── Extract code snippets                              │
│                                                             │
│  4. AI PROCESSING                                           │
│     ├── Filter bot messages                                │
│     ├── Build conversation context                         │
│     ├── Extract technical content                          │
│     │   ├── Commands                                      │
│     │   ├── Error messages                                │
│     │   └── Configuration blocks                          │
│     │                                                      │
│     └── Generate RCA using GPT-4                           │
│         ├── Analyze conversation                           │
│         ├── Structure findings                             │
│         └── Format output                                  │
│                                                             │
│  5. REPORT GENERATION                                       │
│     ├── Create HTML structure                              │
│     ├── Add RCA content                                    │
│     ├── Embed images with thumbnails                       │
│     ├── Add clickable reference links                      │
│     ├── Apply status-based styling                         │
│     └── Include interactive JavaScript                     │
│                                                             │
│  6. OUTPUT                                                  │
│     ├── Save to rca_reports directory                      │
│     └── Open in default browser                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Module Dependencies

```
1_python_script.py (Main)
    │
    ├──► ai_processor.py
    │    └──► OpenAI API
    │
    ├──► slack_integration.py
    │    └──► Slack SDK
    │         └──► Slack API
    │
    ├──► clickup_extended.py
    │    └──► Requests Library
    │         └──► ClickUp API
    │
    └──► config.yaml
         ├── ClickUp credentials
         ├── Slack credentials
         └── OpenAI credentials
```

## Prerequisites

- Python 3.7+
- ClickUp API access
- Slack Bot with appropriate permissions
- OpenAI API key (GPT-4 access recommended)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd RCA-SCRIPT-2
```

2. Install required packages:
```bash
pip install pyyaml requests slack-sdk openai
```

3. Create configuration file:
```bash
cp config.yaml.example config.yaml
```

4. Edit `config.yaml` with your API credentials:
```yaml
clickup:
  api_key: "pk_YOUR_CLICKUP_API_KEY"
  workspace_id: "3443930"
  customer_folder_id: "109448264"

slack:
  bot_token: "xoxb-YOUR-SLACK-BOT-TOKEN"

openai:
  api_key: "sk-YOUR-OPENAI-API-KEY"
  model: "gpt-4o"  # or "gpt-4-turbo-preview"
```

## Project Structure

```
RCA-SCRIPT-2/
├── 1_python_script.py        # Main script - generates RCA reports
├── ai_processor.py           # AI processing module for RCA analysis
├── slack_integration.py      # Slack API integration
├── clickup_extended.py       # Extended ClickUp API functionality
├── test_ai_integration.py    # Test suite for components
├── config.yaml              # Configuration file (create from example)
└── rca_reports/            # Output directory for generated reports
```

## Usage

### Basic Usage

Run the main script to generate an RCA report:
```bash
python 1_python_script.py
```

You'll be prompted to select a date range:
1. Last 30 days
2. Last 7 days
3. Today only
4. Custom date range

### Debug Mode

For detailed logging and troubleshooting:
```bash
python 1_python_script.py --debug
```

### Testing Components

Verify all components are working:
```bash
python test_ai_integration.py
```

## ClickUp Status Workflow

The system recognizes the following status categories:

### Active Statuses
- OPEN
- PENDING (ACK)
- NEEDS CUSTOMER RESPONSE
- PLANNED
- IN PROGRESS
- BLOCKED
- PR RAISED
- PR MERGED
- IN QA
- TESTED
- PRODUCT SIGNOFF
- DESIGN SIGNOFF
- RELEASE PENDING

### Done Statuses (Resolution without fix)
- DUPLICATE
- EXTERNAL LIMITATION
- CUSTOMER SIDE FIX
- INVALID
- NOT REPRODUCIBLE
- AS DESIGNED
- CAN'T FIX

### Closed Status
- COMPLETE

## Report Features

Generated reports include:

### Per Ticket Analysis
- **Summary of the Issue**: AI-extracted problem description
- **Steps to Debug**: Documented debugging actions with commands
- **Steps to Resolution**: Actions taken to resolve the issue
- **Root Cause Analysis**: Identified root cause of the problem

### Media Integration
- **Reference Links**: Console/dashboard URLs from conversations
- **Attached Images**: Screenshots from ClickUp and Slack
- **Error Screenshots**: Automatically categorized error images
- **Code Snippets**: Extracted commands and code blocks

### Visual Indicators
- 🔗 Slack thread integration
- 📸 Image count badges
- ⏱️ Resolution time tracking
- 🎨 Color-coded status indicators

## Slack Bot Setup

### Required Permissions
Your Slack bot needs these OAuth scopes:
- `channels:history` - Read public channel messages
- `groups:history` - Read private channel messages
- `im:history` - Read direct messages
- `mpim:history` - Read group direct messages
- `files:read` - Access file information
- `users:read` - Get user information

### Bot Configuration
1. Create a Slack App at https://api.slack.com/apps
2. Add OAuth scopes under "OAuth & Permissions"
3. Install the app to your workspace
4. Copy the Bot User OAuth Token to `config.yaml`

## ClickUp API Setup

1. Get your API token from ClickUp:
   - Go to Settings → Apps → API Token
   - Generate and copy your personal token

2. Find your workspace and folder IDs:
   - Use the ClickUp API explorer or inspect network requests
   - Update IDs in `config.yaml`

## OpenAI Configuration

1. Get an API key from https://platform.openai.com
2. Ensure you have access to GPT-4 models
3. Add the key to `config.yaml`

## Output

Reports are saved to `/Users/abhishtbagewadi/Documents/Scripts/RCA-SCRIPT-2/rca_reports/` with timestamp:
- Format: `RCA_Report_YYYYMMDD_HHMMSS.html`
- Automatically opens in browser on macOS

## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **API Rate Limits**
   - Implement pagination for large datasets
   - Add delays between API calls if needed

3. **No Slack Messages Found**
   - Ensure Slack URL is included in ClickUp ticket
   - Verify bot has channel access permissions

4. **AI Analysis Fails**
   - Check OpenAI API key and model access
   - Verify conversation data is being extracted

### Debug Mode Features
- Detailed comment extraction logging
- Bot message filtering visibility
- Conversation building details
- AI processing step tracking
- Media extraction debugging

## Customization

### Modify Status Mappings
Edit status lists in `fetch_tickets_complete()` function:
```python
ACTIVE_STATUSES = [...]
COMPLETED_STATUSES = [...]
```

### Adjust Report Styling
Modify CSS in `generate_html_report()` function for custom styling.

### Change AI Prompts
Edit system and user prompts in `ai_processor.py` to customize analysis.

## Performance Considerations

- **Large Datasets**: Uses pagination for tickets exceeding 100 items
- **Long Conversations**: Intelligently chunks conversations over 30,000 characters
- **Image Limits**: Displays up to 10 images per ticket
- **Console Links**: Shows up to 10 reference links per ticket

## Security Notes

- Never commit `config.yaml` with real API keys
- Use environment variables for production deployments
- Rotate API keys regularly
- Limit bot permissions to necessary channels only

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with `test_ai_integration.py`
5. Submit a pull request

## License

[Specify your license here]

## Support

For issues or questions:
- Check debug mode output first
- Review test suite results
- Ensure all API credentials are valid
- Verify network connectivity to APIs

## Version History

- **v2.0**: Added AI analysis with GPT-4 integration
- **v1.5**: Enhanced media extraction from Slack
- **v1.0**: Basic RCA report generation

---

**Note**: Update file paths and workspace IDs according to your environment before running.
