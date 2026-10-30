# Projects — OpenAI Codex workspace

Repository: `opskarner90/Projects`

## Codex Cloud environment
1. Open Codex and select this GitHub repository.
2. Create an environment for its `main` branch.
3. Set the setup script to `bash .codex/setup.sh` (or leave automatic setup if preferred).
4. Test the environment with `bash .codex/check.sh`.
5. Save/publish the environment in Codex.

The scripts install dependencies only if root `requirements.txt`, `pyproject.toml` or `package.json` exist. For Windows PowerShell use `.codex/setup.ps1`.

Each new application belongs under `projects/<name>/`.

**Important:** These checked-in files prepare the repository. Creating a cloud environment in the Codex interface is a separate action.
