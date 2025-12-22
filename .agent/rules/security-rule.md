---
trigger: always_on
---

# AI Coding Assistant Security Rules

You MUST strictly follow these security rules when performing any coding tasks in this project:

## 1. Command Execution Security
- **Strictly Limited Scope**: All shell commands MUST be executed within the project core workspace (/Users/bytedance/ai/agent-example).
- **No Destructive Commands**: Never execute 'rm -rf /', 'chmod -R 777', or any commands that could compromise system stability or security.
- **Verification of External Dependencies**: Before introducing new npm or pip packages, verify they are reputable and do not have known vulnerabilities.

## 2. Secrets and Credential Management
- **Zero Tolerance for Hardcoding**: NEVER hardcode API keys, passwords, or tokens in source code.
- **Environment Variables**: Always use '.env' files and 'os.getenv()' or equivalent for configuration.
- **Git Ignore**: Ensure that '.env' and other sensitive files are never committed to control. Check '.gitignore' before creating new config files.

## 3. Data Privacy and PII
- **Protect Sensitive Data**: Do not include personally identifiable information (PII) in logs, reports, or comments.
- **Anonymize Logs**: Ensure that debug logs do not leak user data or internal system details.

## 4. Code Quality and Vulnerability Prevention
- **Input Validation**: Always validate and sanitize user inputs to prevent SQL Injection, XSS, and command injection.
- **Secure Defaults**: Use secure-by-default configurations for web servers (e.g., CORS settings, CSP headers).
- **Dependency Scanning**: Regularly check for vulnerable dependencies using tools like 'npm audit' or 'pip-audit' if available.

## 5. File Access Control
- **No Unauthorized Reading**: Do not attempt to read sensitive system files (e.g., '/etc/passwd', ssh keys, bash history) unless explicitly requested for a valid reason.
- **Internal Directories**: Do not bypass established project directory structures.

## 6. Execution Safety
- **Turbo Rules**: Follow '// turbo' and '// turbo-all' annotations in workflows strictly. Always set 'SafeToAutoRun' to 'false' for any command that has side effects or reaches external networks unless explicitly permitted by the workflow.

---
*Failure to comply with these rules will be considered a severe security breach.*