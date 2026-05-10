---
name: obsidian
description: Read, search, and create notes in the Obsidian vault.
---

# Obsidian Vault

**Location:** Set via `OBSIDIAN_VAULT_PATH` environment variable (e.g. in `~/.hermes/.env`).

If unset, defaults to `~/Documents/Obsidian Vault`.

Note: Vault paths may contain spaces - always quote them.

## Read a note

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
cat "$VAULT/Note Name.md"
```

## List notes

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# All notes
find "$VAULT" -name "*.md" -type f

# In a specific folder
ls "$VAULT/Subfolder/"
```

## Search

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# By filename
find "$VAULT" -name "*.md" -iname "*keyword*"

# By content
grep -rli "keyword" "$VAULT" --include="*.md"
```

## Create a note

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
cat > "$VAULT/New Note.md" << 'ENDNOTE'
# Title

Content here.
ENDNOTE
```

## Append to a note

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
echo "
New content here." >> "$VAULT/Existing Note.md"
```

## Wikilinks

Obsidian links notes with `[[Note Name]]` syntax. When creating notes, use these to link related content.

## Railway deployment — GitHub PAT for vault sync

The vault lives in a private GitHub repo. On Railway, the agent needs a Personal Access Token to clone/pull/push.

**1. Add the token as a Railway env var:**

- Variable name: `GITHUB_PAT` (or `GH_TOKEN`)
- Value: `github_pat_...` (the full token)

**2. Configure git credentials at container startup.** Either copy the token into `~/.hermes/.env`, or set up a git credential helper directly. Example entrypoint snippet:

```bash
if [ -n "$GITHUB_PAT" ]; then
  git config --global credential.helper '!f() { echo "username=x-access-token"; echo "password=$GITHUB_PAT"; }; f'
  export GITHUB_TOKEN=$GITHUB_PAT
fi
```

This way every fresh Railway deployment has git access to the vault without manual intervention.
