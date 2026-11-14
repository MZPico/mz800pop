# Releasing

A release is a GitHub release with the game's floppy disk image, built by the workflow
`.github/workflows/release.yml` from a version tag. Users download it from
https://github.com/MZPico/mz800pop/releases (the README points there).

## What a release holds

- `pop800-X.Y.Z.dsk`: the game disk, as `make ci-build` builds `build/pop800.dsk` (the release build: no cheats).
  Every sector's Extended DSK length field is 128 << N (tools/mkgamedisk.py sets them, tools/edsk.py; mzdisk
  writes 0, and a floppy written from such an image by Greaseweazle does not boot); the workflow checks it
  (`python3 tools/edsk.py check`) before it publishes the file.
- `pop800-X.Y.Z.dsk.sha256`: its SHA-256 checksum (`sha256sum -c pop800-X.Y.Z.dsk.sha256`).
- The notes: a short user-facing paragraph (what the file is, what the machine needs, a link to the README at that
  tag, the rights note), followed by GitHub's generated list of the changes since the previous release.

The disk is built from the original DOS game data, which the workflow downloads as the PR checks do
(`tools/ci/fetch_dos_data.py`, md5-checked) and does not attach. The user decided to publish the built disk.

## The version

The version is the `VERSION` file at the repository root (`X.Y.Z`, semantic versioning); the loading screen shows it.
The tag is `v` + that version. The workflow stops when they differ, and a real release stops when `VERSION` is
missing (a dry run only warns).

To bump it, edit `VERSION` (one line) and rebuild (`make`). `tools/version.py` checks the format at build time: it
writes `build/version.inc`, and the loading screen shows the version centred under the credit line as `V0.1.0`.
Anything other than `MAJOR.MINOR.PATCH` fails the build. The build also accepts a `-suffix` of letters, digits, dots
and hyphens (`1.0.0-rc.1`, shown in upper case, since the loader's font has no lower case), for local builds only: the
release workflow takes a plain `X.Y.Z`.

## Cutting a release

1. In a PR, set `VERSION` to the new version (and anything else the release needs); merge it to `main`.
2. Tag the merged commit on `main` and push the tag:

   ```sh
   git fetch origin
   git tag -a v0.1.0 origin/main -m "Prince of Persia MZ-800 0.1.0"
   git push origin v0.1.0
   ```

3. The tag push starts the workflow (Actions tab, "Release"): it checks the tag against `VERSION`, builds the tools
   and the disk, runs the smoke tier (`make check-smoke`), then creates the release with the two files and the notes.

Only a pushed tag `v*.*.*` or a manual run starts the workflow; pushes to branches and PRs never do.

## A dry run

Actions tab, "Release", "Run workflow" (or the CLI), with `dry_run` ticked (the default):

```sh
gh workflow run release.yml --ref main -f dry_run=true                 # the branch's head, no tag needed
gh workflow run release.yml --ref main -f tag=v0.1.0 -f dry_run=true   # an existing tag
gh run watch
```

It builds and checks everything a release does and uploads the files as the run's artifact `pop800-X.Y.Z` (kept 14
days), but creates no release and no tag: the `publish the release` job is skipped. `smoke=false` skips the smoke
tier. A manual run can be started only once the workflow file is on `main`.

## Re-running

- A failed run: "Re-run failed jobs" on the run, or push nothing and start it by hand for the existing tag with
  `dry_run` unticked (`gh workflow run release.yml --ref main -f tag=vX.Y.Z -f dry_run=false`).
- When the release already exists, the workflow replaces its two files (`gh release upload --clobber`) and keeps the
  notes; edit those on the release page.
- To rebuild a release from a different commit, delete the release and the tag on GitHub, fix `main`, then tag again.
  Prefer a new patch version instead.
