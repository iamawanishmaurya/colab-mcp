# Problem: gh fork remote flag rejected

## Exact error

```text
the `--remote` flag is unsupported when a repository argument is provided

Usage:  gh repo fork [<repository>] [-- <gitflags>...] [flags]

Flags:
  --clone                 Clone the fork
  --default-branch-only   Only include the default branch in the fork
  --fork-name string      Rename the forked repository
  --org string            Create the fork in an organization
  --remote                Add a git remote for the fork
  --remote-name string    Specify the name for the new remote (default "origin")
```

## Reproduction steps

1. Work in `/home/astra/codex/Google-Colab/colab-mcp`.
2. Run `gh repo fork googlecolab/colab-mcp --clone=false --remote --remote-name fork`.

## Environment

- Repository: `/home/astra/codex/Google-Colab/colab-mcp`
- Current branch: `main`
- Authenticated GitHub account: `iamawanishmaurya`
- GitHub CLI is installed and authenticated.

## First hypothesis

The installed GitHub CLI version requires either running `gh repo fork --remote --remote-name fork` from inside the source repository without an explicit repository argument, or creating the fork first and adding the remote with `git remote add` separately.
