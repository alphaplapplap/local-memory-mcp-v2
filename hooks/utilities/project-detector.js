/**
 * Project Context Detection Utility
 * Analyzes the current directory to determine project type, language, and context
 */

const fs = require('fs').promises;
const path = require('path');
const { execSync } = require('child_process');

/**
 * Detect programming language from file extensions
 */
async function detectLanguage(directory) {
    try {
        const files = await fs.readdir(directory, { withFileTypes: true });
        const extensions = new Map();
        
        // Count file extensions
        for (const file of files) {
            if (file.isFile()) {
                const ext = path.extname(file.name).toLowerCase();
                if (ext) {
                    extensions.set(ext, (extensions.get(ext) || 0) + 1);
                }
            }
        }
        
        // Language detection rules with priority weights
        const languageMap = {
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
        };
        
        // Priority weights for language detection (higher = more important)
        const languagePriority = {
            '.py': 10,
            '.js': 8,
            '.ts': 8,
            '.rs': 8,
            '.go': 8,
            '.java': 8,
            '.cpp': 7,
            '.c': 7,
            '.cs': 7,
            '.php': 6,
            '.rb': 6,
            '.swift': 6,
            '.kt': 6,
            '.scala': 6,
            '.sh': 5,
            '.md': 2  // Documentation has low priority
        };
        
        // Find primary language using weighted scoring
        let primaryLanguage = 'Unknown';
        let bestScore = 0;
        
        for (const [ext, count] of extensions.entries()) {
            if (languageMap[ext]) {
                const priority = languagePriority[ext] || 1;
                const score = count * priority; // Weight by both count and priority
                
                if (score > bestScore) {
                    bestScore = score;
                    primaryLanguage = languageMap[ext];
                }
            }
        }
        
        return {
            primary: primaryLanguage,
            extensions: Object.fromEntries(extensions),
            confidence: bestScore > 0 ? Math.min(bestScore / 50, 1) : 0
        };
        
    } catch (error) {
        return { primary: 'Unknown', extensions: {}, confidence: 0 };
    }
}

/**
 * Detect framework and tools from configuration files
 */
async function detectFramework(directory) {
    const frameworks = [];
    const tools = [];
    
    try {
        const files = await fs.readdir(directory);
        
        // Check for common configuration files
        const configFiles = {
            'package.json': async () => {
                const pkg = JSON.parse(await fs.readFile(path.join(directory, 'package.json'), 'utf8'));
                
                // Check dependencies for frameworks
                const deps = { ...pkg.dependencies, ...pkg.devDependencies };
                
                if (deps.react || deps['@types/react']) frameworks.push('React');
                if (deps.vue || deps['@vue/cli']) frameworks.push('Vue.js');
                if (deps.angular || deps['@angular/core']) frameworks.push('Angular');
                if (deps.next || deps['next']) frameworks.push('Next.js');
                if (deps.express || deps['express']) frameworks.push('Express.js');
                if (deps.fastify) frameworks.push('Fastify');
                if (deps.svelte || deps['svelte']) frameworks.push('Svelte');
                
                tools.push('npm');
                return pkg.name || 'node-project';
            },
            'pyproject.toml': async () => {
                tools.push('Python');
                const content = await fs.readFile(path.join(directory, 'pyproject.toml'), 'utf8');
                
                // Extract project name from pyproject.toml
                const nameMatch = content.match(/^name\s*=\s*["']([^"']+)["']/m);
                
                if (content.includes('django')) frameworks.push('Django');
                if (content.includes('flask')) frameworks.push('Flask');
                if (content.includes('fastapi')) frameworks.push('FastAPI');
                if (content.includes('pytest')) tools.push('pytest');
                if (content.includes('poetry')) tools.push('Poetry');
                if (content.includes('mcp')) frameworks.push('MCP');
                if (content.includes('postgresql') || content.includes('asyncpg')) tools.push('PostgreSQL');
                if (content.includes('ollama')) tools.push('Ollama');
                
                return nameMatch ? nameMatch[1] : 'python-project';
            },
            'requirements.txt': async () => {
                tools.push('Python');
                const content = await fs.readFile(path.join(directory, 'requirements.txt'), 'utf8');
                
                if (content.includes('fastapi')) frameworks.push('FastAPI');
                if (content.includes('flask')) frameworks.push('Flask');
                if (content.includes('django')) frameworks.push('Django');
                if (content.includes('asyncpg')) tools.push('PostgreSQL');
                if (content.includes('ollama')) tools.push('Ollama');
                if (content.includes('mcp')) frameworks.push('MCP');
                
                return 'python-project';
            },
            'Cargo.toml': async () => {
                tools.push('Cargo');
                const content = await fs.readFile(path.join(directory, 'Cargo.toml'), 'utf8');
                
                const nameMatch = content.match(/^name\s*=\s*["']([^"']+)["']/m);
                
                if (content.includes('actix-web')) frameworks.push('Actix Web');
                if (content.includes('rocket')) frameworks.push('Rocket');
                if (content.includes('warp')) frameworks.push('Warp');
                if (content.includes('tokio')) frameworks.push('Tokio');
                if (content.includes('tauri')) frameworks.push('Tauri');
                
                return nameMatch ? nameMatch[1] : 'rust-project';
            },
            'tauri.conf.json': async () => {
                frameworks.push('Tauri');
                tools.push('Tauri CLI');
                
                try {
                    const config = JSON.parse(await fs.readFile(path.join(directory, 'tauri.conf.json'), 'utf8'));
                    const appName = config.package?.productName || 'tauri-app';
                    return appName;
                } catch (error) {
                    return 'tauri-app';
                }
            },
            'go.mod': async () => {
                tools.push('Go Modules');
                const content = await fs.readFile(path.join(directory, 'go.mod'), 'utf8');
                
                const moduleMatch = content.match(/^module\s+(.+)$/m);
                
                if (content.includes('gin-gonic/gin')) frameworks.push('Gin');
                if (content.includes('gorilla/mux')) frameworks.push('Gorilla Mux');
                if (content.includes('fiber')) frameworks.push('Fiber');
                
                return moduleMatch ? path.basename(moduleMatch[1]) : 'go-project';
            },
            'pom.xml': () => {
                tools.push('Maven');
                frameworks.push('Java/Maven');
                return 'java-maven-project';
            },
            'build.gradle': () => {
                tools.push('Gradle');
                frameworks.push('Java/Gradle');
                return 'java-gradle-project';
            },
            'docker-compose.yml': () => {
                tools.push('Docker Compose');
                return null;
            },
            'Dockerfile': () => {
                tools.push('Docker');
                return null;
            },
            '.env': () => {
                tools.push('Environment Config');
                return null;
            }
        };
        
        let projectName = null;
        
        for (const file of files) {
            if (configFiles[file]) {
                const result = await configFiles[file]();
                if (result && !projectName) {
                    projectName = result;
                }
            }
        }
        
        // Check subdirectories for Tauri projects (common pattern: frontend/src-tauri/)
        const tauriPaths = [
            'frontend/src-tauri',
            'src-tauri', 
            'tauri',
            'app/src-tauri'
        ];
        
        for (const tauriPath of tauriPaths) {
            const tauriDir = path.join(directory, tauriPath);
            try {
                const tauriFiles = await fs.readdir(tauriDir);
                
                // Check for tauri.conf.json in subdirectory
                if (tauriFiles.includes('tauri.conf.json')) {
                    const tauriConfig = path.join(tauriDir, 'tauri.conf.json');
                    const config = JSON.parse(await fs.readFile(tauriConfig, 'utf8'));
                    frameworks.push('Tauri');
                    tools.push('Tauri CLI');
                    if (!projectName) {
                        projectName = config.package?.productName || 'tauri-app';
                    }
                }
                
                // Check for Cargo.toml in subdirectory
                if (tauriFiles.includes('Cargo.toml')) {
                    const cargoToml = path.join(tauriDir, 'Cargo.toml');
                    const content = await fs.readFile(cargoToml, 'utf8');
                    tools.push('Cargo');
                    
                    if (content.includes('tokio')) frameworks.push('Tokio');
                    if (content.includes('tauri')) frameworks.push('Tauri');
                    
                    if (!projectName) {
                        const nameMatch = content.match(/^name\s*=\s*["']([^"']+)["']/m);
                        projectName = nameMatch ? nameMatch[1] : 'rust-project';
                    }
                }
            } catch (error) {
                // Directory doesn't exist or can't be read, continue
            }
        }
        
        return {
            frameworks,
            tools,
            projectName
        };
        
    } catch (error) {
        return { frameworks: [], tools: [], projectName: null };
    }
}

/**
 * Get Git repository information
 */
function getGitInfo(directory) {
    try {
        const gitDir = path.join(directory, '.git');
        
        // Check if this is a git repository
        const isGitRepo = require('fs').existsSync(gitDir);
        if (!isGitRepo) {
            return { isRepo: false };
        }
        
        // Get repository information
        const remoteBranch = execSync('git branch --show-current', { cwd: path.resolve(directory), encoding: 'utf8' }).trim();
        const remoteUrl = execSync('git config --get remote.origin.url', { cwd: path.resolve(directory), encoding: 'utf8' }).trim();
        const lastCommit = execSync('git log -1 --pretty=format:"%h %s"', { cwd: path.resolve(directory), encoding: 'utf8' }).trim();
        
        // Extract repository name from URL
        let repoName = 'unknown-repo';
        if (remoteUrl) {
            const match = remoteUrl.match(/([^\/]+)(?:\.git)?$/);
            if (match) {
                repoName = match[1].replace('.git', '');
            }
        }
        
        return {
            isRepo: true,
            branch: remoteBranch,
            remoteUrl,
            repoName,
            lastCommit
        };
        
    } catch (error) {
        return { isRepo: false, error: error.message };
    }
}

// ANSI Colors for console output
const COLORS = {
    RESET: '\x1b[0m',
    BRIGHT: '\x1b[1m',
    DIM: '\x1b[2m',
    CYAN: '\x1b[36m',
    GREEN: '\x1b[32m',
    BLUE: '\x1b[34m',
    YELLOW: '\x1b[33m',
    GRAY: '\x1b[90m',
    RED: '\x1b[31m'
};

/**
 * Main project context detection function with enhanced visual output
 */
async function detectProjectContext(directory = process.cwd()) {
    try {
        const directoryName = path.basename(directory);
        console.log(`${COLORS.BLUE}📂 Project Detector${COLORS.RESET} ${COLORS.DIM}→${COLORS.RESET} Analyzing ${COLORS.BRIGHT}${directoryName}${COLORS.RESET}`);
        
        // Get basic directory information
        
        // Detect language
        const language = await detectLanguage(directory);
        
        // Detect framework and tools
        const framework = await detectFramework(directory);
        
        // Get Git information
        const git = getGitInfo(directory);
        
        // Determine project name (priority: git repo > directory name > config file)
        const projectName = git.repoName || directoryName || framework.projectName;
        
        // Calculate confidence score
        let confidence = 0.5; // Base confidence
        if (git.isRepo) confidence += 0.3;
        if (framework.frameworks.length > 0) confidence += 0.2;
        if (language.confidence > 0.5) confidence += language.confidence * 0.3;
        
        const context = {
            name: projectName,
            directory,
            language: language.primary,
            languageDetails: language,
            frameworks: framework.frameworks,
            tools: framework.tools,
            git: git,
            confidence: Math.min(confidence, 1.0),
            metadata: {
                detectedAt: new Date().toISOString(),
                analyzer: 'claude-hooks-project-detector',
                version: '1.1.0'
            }
        };
        
        // Enhanced output with confidence indication
        const confidencePercent = (context.confidence * 100).toFixed(0);
        const confidenceColor = context.confidence > 0.8 ? COLORS.GREEN : 
                               context.confidence > 0.6 ? COLORS.YELLOW : COLORS.GRAY;
        
        // Build technology stack display
        const techStack = [];
        
        // Add primary language
        if (context.language !== 'Unknown') {
            techStack.push(context.language);
        }
        
        // Add frameworks
        if (context.frameworks.length > 0) {
            techStack.push(...context.frameworks);
        }
        
        // Add additional languages if different from primary
        if (context.languageDetails && context.languageDetails.extensions) {
            const additionalLangs = [];
            for (const [ext, count] of Object.entries(context.languageDetails.extensions)) {
                const langMap = {
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
                };
                
                const lang = langMap[ext];
                if (lang && lang !== context.language && !context.frameworks.includes(lang)) {
                    additionalLangs.push(lang);
                }
            }
            techStack.push(...additionalLangs);
        }
        
        // Remove duplicates while preserving order
        const uniqueTechStack = [...new Set(techStack)];
        
        // Format technology stack
        const techDisplay = uniqueTechStack.length > 1 
            ? `${COLORS.GRAY}(${uniqueTechStack.join(' + ')})${COLORS.RESET}`
            : `${COLORS.GRAY}(${context.language})${COLORS.RESET}`;

        console.log(`${COLORS.BLUE}📊 Detection Result${COLORS.RESET} ${COLORS.DIM}→${COLORS.RESET} ${COLORS.BRIGHT}${context.name}${COLORS.RESET} ${techDisplay} ${COLORS.DIM}•${COLORS.RESET} ${confidenceColor}${confidencePercent}%${COLORS.RESET}`);
        
        return context;
        
    } catch (error) {
        console.error(`${COLORS.RED}❌ Project Detector Error${COLORS.RESET} ${COLORS.DIM}→${COLORS.RESET} ${error.message}`);
        
        // Return minimal context on error
        return {
            name: path.basename(directory),
            directory,
            language: 'Unknown',
            frameworks: [],
            tools: [],
            confidence: 0.1,
            error: error.message
        };
    }
}

module.exports = {
    detectProjectContext,
    detectLanguage,
    detectFramework,
    getGitInfo
};

// Direct execution support for testing
if (require.main === module) {
    detectProjectContext(process.cwd())
        .then(context => {
            console.log('\n=== PROJECT CONTEXT ===');
            console.log(JSON.stringify(context, null, 2));
            console.log('=== END CONTEXT ===\n');
        })
        .catch(error => console.error('Detection failed:', error));
}