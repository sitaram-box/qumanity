# Git Workflow

## Branch Strategy

| Branch | Purpose |
| :--- | :--- |
| `main` | Production-ready code |
| `develop` | Integration branch |
| `feature/*` | New features |
| `bugfix/*` | Bug fixes |
| `hotfix/*` | Urgent production fixes |

## Commit Messages

Format: `<type>(<scope>): <description>`

| Type | Description |
| :--- | :--- |
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `style` | Code style (formatting, etc.) |
| `refactor` | Code refactoring |
| `test` | Adding tests |
| `chore` | Maintenance tasks |

## Examples

```bash
git commit -m "feat(elections): add nomination approval button for admin"
git commit -m "fix(marquee): correct poem cycling after last poem"
git commit -m "docs(knowledge): add setup guide"
```

## Regular Workflow

```bash
git checkout develop
git pull origin develop
git checkout -b feature/your-feature-name
# make changes
git add .
git commit -m "feat(scope): description"
git push origin feature/your-feature-name
# create pull request on GitHub
```

## Reverting

```bash
# Revert to previous stable version
git checkout backup-before-languages
# Or
git tag backup-before-changes
```
