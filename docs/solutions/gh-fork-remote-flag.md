# Solution: gh fork remote flag rejected

## Linked problem

- [Problem: gh fork remote flag rejected](../problems/2026-06-06-gh-fork-remote-flag.md)

## What failed

`gh repo fork googlecolab/colab-mcp --clone=false --remote --remote-name fork` failed because this GitHub CLI version does not support `--remote` when an explicit repository argument is provided.

## What worked

Running the fork command from inside the cloned source repository without the explicit repository argument worked:

```shell
gh repo fork --remote --remote-name fork
```

## Why it worked

Inside the cloned repository, GitHub CLI can infer the source repository from `origin`, create the authenticated user's fork, and add the requested `fork` remote in one operation.

## Commands run

```shell
gh repo fork googlecolab/colab-mcp --clone=false --remote --remote-name fork
gh repo fork --remote --remote-name fork
git remote -v
```

## Result

The fork remote was added:

```text
fork   https://github.com/iamawanishmaurya/colab-mcp.git (fetch)
fork   https://github.com/iamawanishmaurya/colab-mcp.git (push)
origin https://github.com/googlecolab/colab-mcp.git (fetch)
origin https://github.com/googlecolab/colab-mcp.git (push)
```
