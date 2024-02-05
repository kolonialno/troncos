<!--pytest-codeblocks:skipfile-->
# CONTRIBUTING

## Set-up

```console
pre-commit install
poetry install
```

## Release

We use [release-please](https://github.com/googleapis/release-please) to automate release including semver version based on [conventional-commits](https://www.conventionalcommits.org/en/v1.0.0/).

Manually create a release PR from main branch

```bash
npx release-please release-pr \
--token=$(gh auth token) \
--repo-url=kolonialno/troncos
--dry-run
```
