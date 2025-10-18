# GitHub Copilot Setup for U-Report

This guide helps you set up GitHub Copilot for optimal development experience with the U-Report Django project.

## Prerequisites

- GitHub account with Copilot access
- Visual Studio Code (recommended) or compatible IDE
- Git installed and configured

## 1. Install GitHub Copilot

### Option A: VS Code Extension (Recommended)
1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X / Cmd+Shift+X)
3. Search for "GitHub Copilot"
4. Install the "GitHub Copilot" extension by GitHub
5. Install the "GitHub Copilot Chat" extension (optional but recommended)

### Option B: Command Line
```bash
code --install-extension GitHub.copilot
code --install-extension GitHub.copilot-chat
```

## 2. Authentication

1. Open VS Code Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
2. Type "GitHub Copilot: Sign In to GitHub"
3. Follow the authentication flow in your browser
4. Return to VS Code when prompted

## 3. Project-Specific Configuration

### VS Code Settings
Create or update your `.vscode/settings.json` in the project root:

```json
{
    "github.copilot.enable": {
        "*": true,
        "yaml": true,
        "plaintext": true,
        "markdown": true,
        "python": true,
        "javascript": true,
        "html": true,
        "css": true,
        "django-html": true
    },
    "github.copilot.advanced": {
        "length": 300,
        "inlineSuggestCount": 3
    },
    "python.defaultInterpreterPath": "./.venv/bin/python",
    "python.terminal.activateEnvironment": true,
    "files.associations": {
        "*.html": "django-html"
    },
    "emmet.includeLanguages": {
        "django-html": "html"
    }
}
```

### Extensions for Enhanced Experience
Install these VS Code extensions for better Django + Copilot experience:

```bash
# Core Python and Django extensions
code --install-extension ms-python.python
code --install-extension ms-python.black-formatter
code --install-extension ms-python.isort
code --install-extension batisteo.vscode-django

# Frontend development
code --install-extension bradlc.vscode-tailwindcss
code --install-extension formulahendry.auto-rename-tag

# Code quality
code --install-extension ms-python.flake8
code --install-extension charliermarsh.ruff
```

## 4. Development Environment Setup

Before using Copilot effectively, ensure your development environment is properly configured:

### Python Environment
```bash
# Install Poetry if not already installed
pip install --upgrade pip poetry

# Install project dependencies
poetry install --no-root

# Activate the virtual environment
poetry shell
```

### Database Setup
```bash
# Link settings file (adjust for your setup)
ln -s settings.py.postgres ureport/settings.py

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic
```

### Frontend Dependencies
```bash
# Install Node.js dependencies
npm install

# Build CSS
npm run build
```

## 5. Copilot Best Practices for This Project

### Code Context
- Keep related files open in tabs to provide Copilot with better context
- Open relevant model files when working on views or serializers
- Have template files open when working on view logic

### Useful File Patterns
- `ureport/polls/models.py` - Main data models
- `ureport/polls/views.py` - View logic
- `ureport/api/` - REST API endpoints
- `templates/` - Django templates
- `static/` - CSS, JS, and other static assets

### Django-Specific Tips

#### 1. Model Development
```python
# Example: Copilot can help with Django model fields and methods
class Poll(models.Model):
    # Type comments like this to get better suggestions:
    # "Create a title field with max length 255"
    # "Add a created_at timestamp field"
    # "Add a method to get active polls"
```

#### 2. View Development
```python
# Copilot understands Django patterns:
# "Create a ListView for polls with pagination"
# "Add a method to filter polls by category"
# "Create an API endpoint that returns poll results as JSON"
```

#### 3. Template Development
```html
<!-- Copilot can help with Django template syntax: -->
<!-- "Create a loop to display poll questions" -->
<!-- "Add conditional logic to show results only for completed polls" -->
```

### API Development
The project uses Django REST Framework. Copilot can help with:
- Serializer creation and validation
- ViewSet implementations
- Permission classes
- Custom API endpoints

## 6. Testing with Copilot

Copilot can assist with test creation:

```python
# In test files, describe what you want to test:
# "Test that poll creation requires authentication"
# "Test API endpoint returns correct JSON structure"
# "Test that poll results are calculated correctly"
```

## 7. Troubleshooting

### Copilot Not Working
1. Check authentication: Command Palette → "GitHub Copilot: Check Status"
2. Restart VS Code
3. Check internet connection
4. Verify your GitHub Copilot subscription is active

### Poor Suggestions
1. Ensure relevant files are open for context
2. Add descriptive comments about what you're trying to achieve
3. Use meaningful variable and function names
4. Keep your code style consistent with the project

### Django-Specific Issues
1. Make sure Django extension is installed and configured
2. Verify Python interpreter points to the Poetry virtual environment
3. Ensure `settings.py` is properly linked for your environment

## 8. Advanced Configuration

### Custom Prompts
Create common comment patterns for better suggestions:

```python
# Common patterns that work well with Copilot:
# "Create a Django model for [entity] with fields [field1, field2]"
# "Add a method to [model] that calculates [calculation]"
# "Create a view that handles [HTTP method] requests for [endpoint]"
# "Add validation to ensure [condition]"
```

### Keyboard Shortcuts
- `Tab` - Accept suggestion
- `Alt/Option + ]` - Next suggestion
- `Alt/Option + [` - Previous suggestion
- `Ctrl/Cmd + Enter` - Open Copilot completions panel

## 9. Project-Specific Context

### Key Technologies
- **Backend**: Django 5.2+, Django REST Framework
- **Database**: PostgreSQL
- **Cache**: Valkey/Redis
- **Frontend**: HTML, CSS (Tailwind), JavaScript
- **Build Tools**: Poetry (Python), npm (Node.js)
- **Testing**: Django's built-in testing framework

### Common Development Tasks
1. Adding new poll types and questions
2. Creating API endpoints for mobile apps
3. Building dashboard views and analytics
4. Managing user authentication and permissions
5. Implementing data visualization features

### Code Style
The project uses:
- Black for Python formatting (line length: 119)
- isort for import sorting
- Ruff for linting
- djlint for template formatting

Run code checks with:
```bash
./code_check.py --debug
```

### Quick Development Workflow
1. Start development server: `python manage.py runserver`
2. In another terminal, watch for CSS changes: `npm run watch`
3. Use Copilot to generate code based on existing patterns
4. Run tests: `python manage.py test`
5. Check code style: `./code_check.py --debug`

## Getting Help

- GitHub Copilot Chat: Use the chat panel to ask questions about the code
- Project documentation: Check the main README.md for development setup
- Django documentation: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/

## Validation

You can test your setup by running our validation script:

```bash
python test_copilot_setup.py
```

This will check that all required tools are installed and configured correctly.

Happy coding with Copilot! 🚀