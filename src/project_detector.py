"""
Project Context Detection Utility
Analyzes the current directory to determine project type, language, and context
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

# ANSI Colors for console output
COLORS = {
    'RESET': '\x1b[0m',
    'BRIGHT': '\x1b[1m',
    'DIM': '\x1b[2m',
    'CYAN': '\x1b[36m',
    'GREEN': '\x1b[32m',
    'BLUE': '\x1b[34m',
    'YELLOW': '\x1b[33m',
    'GRAY': '\x1b[90m',
    'RED': '\x1b[31m'
}

def detect_language(directory: str) -> Dict[str, Any]:
    """
    Detect programming language from file extensions
    """
    try:
        extensions = {}

        # Count file extensions
        for item in os.listdir(directory):
            if os.path.isfile(os.path.join(directory, item)):
                ext = os.path.splitext(item)[1].lower()
                if ext:
                    extensions[ext] = extensions.get(ext, 0) + 1

        # Language detection rules
        language_map = {
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.jsx': 'React/JavaScript',
            '.tsx': 'React/TypeScript',
            '.py': 'Python',
            '.rs': 'Rust',
            '.go': 'Go',
            '.java': 'Java',
            '.cpp': 'C++',
            '.c': 'C',
            '.cs': 'C#',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.scala': 'Scala',
            '.sh': 'Shell',
            '.md': 'Documentation'
        }

        # Find most common language extension
        primary_language = 'Unknown'
        max_count = 0

        for ext, count in extensions.items():
            if ext in language_map and count > max_count:
                max_count = count
                primary_language = language_map[ext]

        confidence = min(max_count / 10, 1.0) if max_count > 0 else 0

        return {
            'primary': primary_language,
            'extensions': extensions,
            'confidence': confidence
        }

    except Exception:
        return {'primary': 'Unknown', 'extensions': {}, 'confidence': 0}

def detect_framework(directory: str) -> Dict[str, Any]:
    """
    Detect framework and tools from configuration files
    """
    frameworks = []
    tools = []
    project_name = None

    try:
        # Check for common configuration files
        config_checks = {
            'package.json': lambda path: _check_package_json(path, frameworks, tools),
            'pyproject.toml': lambda path: _check_pyproject_toml(path, frameworks, tools),
            'Cargo.toml': lambda path: _check_cargo_toml(path, frameworks, tools),
            'go.mod': lambda path: _check_go_mod(path, frameworks, tools),
            'pom.xml': lambda path: _check_maven(path, frameworks, tools),
            'build.gradle': lambda path: _check_gradle(path, frameworks, tools),
            'docker-compose.yml': lambda path: (tools.append('Docker Compose'), None),
            'Dockerfile': lambda path: (tools.append('Docker'), None),
            '.env': lambda path: (tools.append('Environment Config'), None)
        }

        for filename, check_func in config_checks.items():
            filepath = os.path.join(directory, filename)
            if os.path.exists(filepath):
                result = check_func(filepath)
                if result and not project_name:
                    project_name = result

        return {
            'frameworks': frameworks,
            'tools': tools,
            'projectName': project_name
        }

    except Exception:
        return {'frameworks': [], 'tools': [], 'projectName': None}

def _check_package_json(filepath: str, frameworks: List[str], tools: List[str]) -> Optional[str]:
    """Check package.json for Node.js frameworks"""
    try:
        with open(filepath, 'r') as f:
            pkg = json.load(f)

        # Check dependencies for frameworks
        deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}

        if 'react' in deps or '@types/react' in deps:
            frameworks.append('React')
        if 'vue' in deps or '@vue/cli' in deps:
            frameworks.append('Vue.js')
        if 'angular' in deps or '@angular/core' in deps:
            frameworks.append('Angular')
        if 'next' in deps:
            frameworks.append('Next.js')
        if 'express' in deps:
            frameworks.append('Express.js')
        if 'fastify' in deps:
            frameworks.append('Fastify')
        if 'svelte' in deps:
            frameworks.append('Svelte')

        tools.append('npm')
        return pkg.get('name', 'node-project')

    except Exception:
        return None

def _check_pyproject_toml(filepath: str, frameworks: List[str], tools: List[str]) -> Optional[str]:
    """Check pyproject.toml for Python frameworks"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        tools.append('Python')

        # Extract project name
        import re
        name_match = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)

        if 'django' in content:
            frameworks.append('Django')
        if 'flask' in content:
            frameworks.append('Flask')
        if 'fastapi' in content:
            frameworks.append('FastAPI')
        if 'pytest' in content:
            tools.append('pytest')
        if 'poetry' in content:
            tools.append('Poetry')

        return name_match.group(1) if name_match else 'python-project'

    except Exception:
        return None

def _check_cargo_toml(filepath: str, frameworks: List[str], tools: List[str]) -> Optional[str]:
    """Check Cargo.toml for Rust frameworks"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        tools.append('Cargo')

        import re
        name_match = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)

        if 'actix-web' in content:
            frameworks.append('Actix Web')
        if 'rocket' in content:
            frameworks.append('Rocket')
        if 'warp' in content:
            frameworks.append('Warp')
        if 'tokio' in content:
            frameworks.append('Tokio')

        return name_match.group(1) if name_match else 'rust-project'

    except Exception:
        return None

def _check_go_mod(filepath: str, frameworks: List[str], tools: List[str]) -> Optional[str]:
    """Check go.mod for Go frameworks"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        tools.append('Go Modules')

        import re
        module_match = re.search(r'^module\s+(.+)$', content, re.MULTILINE)

        if 'gin-gonic/gin' in content:
            frameworks.append('Gin')
        if 'gorilla/mux' in content:
            frameworks.append('Gorilla Mux')
        if 'fiber' in content:
            frameworks.append('Fiber')

        if module_match:
            return os.path.basename(module_match.group(1))
        return 'go-project'

    except Exception:
        return None

def _check_maven(filepath: str, frameworks: List[str], tools: List[str]) -> Optional[str]:
    """Check pom.xml for Maven/Java projects"""
    tools.append('Maven')
    frameworks.append('Java/Maven')
    return 'java-maven-project'

def _check_gradle(filepath: str, frameworks: List[str], tools: List[str]) -> Optional[str]:
    """Check build.gradle for Gradle/Java projects"""
    tools.append('Gradle')
    frameworks.append('Java/Gradle')
    return 'java-gradle-project'

def get_git_info(directory: str) -> Dict[str, Any]:
    """
    Get Git repository information
    """
    try:
        git_dir = os.path.join(directory, '.git')

        # Check if this is a git repository
        if not os.path.exists(git_dir):
            return {'isRepo': False}

        # Get repository information
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=2
        )
        branch = result.stdout.strip() if result.returncode == 0 else ''

        result = subprocess.run(
            ['git', 'config', '--get', 'remote.origin.url'],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=2
        )
        remote_url = result.stdout.strip() if result.returncode == 0 else ''

        result = subprocess.run(
            ['git', 'log', '-1', '--pretty=format:%h %s'],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=2
        )
        last_commit = result.stdout.strip() if result.returncode == 0 else ''

        # Extract repository name from URL
        repo_name = 'unknown-repo'
        if remote_url:
            import re
            match = re.search(r'([^/]+)(?:\.git)?$', remote_url)
            if match:
                repo_name = match.group(1).replace('.git', '')

        return {
            'isRepo': True,
            'branch': branch,
            'remoteUrl': remote_url,
            'repoName': repo_name,
            'lastCommit': last_commit
        }

    except Exception as e:
        return {'isRepo': False, 'error': str(e)}

def detect_project_context(directory: str = None) -> Dict[str, Any]:
    """
    Main project context detection function with enhanced visual output
    """
    if directory is None:
        directory = os.getcwd()

    try:
        directory_name = os.path.basename(directory)
        print(f"{COLORS['BLUE']}📂 Project Detector{COLORS['RESET']} {COLORS['DIM']}→{COLORS['RESET']} Analyzing {COLORS['BRIGHT']}{directory_name}{COLORS['RESET']}")

        # Detect language
        language = detect_language(directory)

        # Detect framework and tools
        framework = detect_framework(directory)

        # Get Git information
        git = get_git_info(directory)

        # Determine project name (priority: git repo > config file > directory name)
        project_name = framework['projectName'] or git.get('repoName') or directory_name

        # Calculate confidence score
        confidence = 0.5  # Base confidence
        if git.get('isRepo'):
            confidence += 0.3
        if framework['frameworks']:
            confidence += 0.2
        if language['confidence'] > 0.5:
            confidence += language['confidence'] * 0.3

        confidence = min(confidence, 1.0)

        context = {
            'name': project_name,
            'directory': directory,
            'language': language['primary'],
            'languageDetails': language,
            'frameworks': framework['frameworks'],
            'tools': framework['tools'],
            'git': git,
            'confidence': confidence,
            'metadata': {
                'detectedAt': datetime.now().isoformat(),
                'analyzer': 'claude-hooks-project-detector',
                'version': '1.1.0'
            }
        }

        # Enhanced output with confidence indication
        confidence_percent = int(context['confidence'] * 100)
        confidence_color = (COLORS['GREEN'] if context['confidence'] > 0.8 else
                          COLORS['YELLOW'] if context['confidence'] > 0.6 else
                          COLORS['GRAY'])

        print(f"{COLORS['BLUE']}📊 Detection Result{COLORS['RESET']} {COLORS['DIM']}→{COLORS['RESET']} {COLORS['BRIGHT']}{context['name']}{COLORS['RESET']} {COLORS['GRAY']}({context['language']}){COLORS['RESET']} {COLORS['DIM']}•{COLORS['RESET']} {confidence_color}{confidence_percent}%{COLORS['RESET']}")

        return context

    except Exception as error:
        print(f"{COLORS['RED']}❌ Project Detector Error{COLORS['RESET']} {COLORS['DIM']}→{COLORS['RESET']} {error}")

        # Return minimal context on error
        return {
            'name': os.path.basename(directory),
            'directory': directory,
            'language': 'Unknown',
            'frameworks': [],
            'tools': [],
            'confidence': 0.1,
            'error': str(error)
        }

# Direct execution support for testing
if __name__ == '__main__':
    context = detect_project_context()
    print('\n=== PROJECT CONTEXT ===')
    print(json.dumps(context, indent=2, default=str))
    print('=== END CONTEXT ===\n')