# APFS Rescue Lab

**Free, open-source APFS diagnostics and recovery research for macOS disk images.** Optional donations; no paywall.

> **EXPERIMENTAL — USE AT YOUR OWN RISK.** Provided **AS IS**, with **NO WARRANTY**, including no guarantee of successful recovery, data integrity, bootability, or fitness for any purpose. Keep the original disk untouched, back it up, and test on independent copies only. Read [DISCLAIMER.md](DISCLAIMER.md) and [LICENSE](LICENSE).

## Why we published this

A macOS Catalina virtual machine stopped booting after its APFS Data volume metadata became inconsistent. We searched for a **ready-to-use, verified solution for this particular failure**, but did not find one. The available guides and fragments of information online were not sufficient. **Several days** went into investigating checkpoints, Object Maps, trial disk images and boot failures, including extensive work with an AI assistant.

The purpose of this repository is to save others from repeating those days of internet searches, trial-and-error and AI prompts. Here is the code and a documented starting point.

**We are not claiming that no other APFS repair or recovery products exist.** The outcome of one incident cannot establish that a technique is safe for other disks.

## Available tools (experimental research release)

- **APFS Analyzer** — inspect GPT partition offsets, container APFS superblock, candidate checkpoint XIDs and checksums.
- **Block Diff** — compare two offline RAW disk images, reporting changed block positions and hashes.
- **Recovery field report** — [anonymized experience and lessons](docs/recovery-case.md).

**Important:** This release does **not** safely or automatically repair APFS. We do, however, publish the **experimental checkpoint-selection tool** which was part of the successful recovery trial. It can create a clone and invalidate newer checkpoint headers on that clone. The unified `apfs_rescue.py` now bundles a limited, automatic candidate-nomination heuristic with the experimental clone-only checkpoint selector. It refuses to nominate encrypted or non-Data volumes and stops on ambiguity. It is explicitly **not** a supported rollback, has not been broadly tested and must not be used on irreplaceable data. See [experimental usage and warnings](docs/experimental-checkpoint.md).

## Automatic candidate nomination (experimental)

The original recovery did **not** require manually choosing an XID. A preceding analysis step nominated an older checkpoint automatically. That heuristic is now available as a single entry point:

```bash
python3 apfs_rescue.py analyze --source "/path/to/disk.raw" --report "./auto-analysis.json"
```

To create a **disposable candidate clone only**, after a verified backup and accepting the high risk:

```bash
python3 apfs_rescue.py recover --source "/path/to/offline-test-source.raw" \
  --output "/path/to/new-test-candidate.raw" \
  --i-understand-this-can-destroy-data
```

This does not guarantee a suitable candidate, safe repair, bootability or write integrity. Only **one unambiguous, plausibly matching checkpoint** is eligible; otherwise it stops. See [compatibility limits and detailed instructions](docs/auto-recovery.md). **Catalina-like unencrypted VM images are the only context in which this technique has been observed to work; it is not validated for all macOS or APFS variants.**

## Quick start

For a more detailed, safety-first walkthrough, read the [step-by-step investigation guide](docs/quick-start.md).

Requires Python 3.9+ (standard library only). Work on **offline copies**, never mounted writable disks.

```bash
python3 tools/apfs_analyzer.py --source "/path/to/disk.raw" --out analysis.json

python3 tools/block_diff.py --source "/path/to/original.raw" \
  --compare "/path/to/trial.raw" --out-dir ./diff-report
```

Input format: whole-disk **RAW** files with a GPT and APFS partition. Read-only operations; no root access required.

For the original step-by-step investigative experience, see [Recovery case](docs/recovery-case.md). It is **not** a universal repair recipe.

## Privacy and safety

Do **not** upload full images, real filesystem content, user home folders, passwords, signing keys, tokens, SSH material or unredacted logs as GitHub issues. Generated reports may include machine-specific paths, offsets or metadata. Review them before sharing. A passing `fsck_apfs` check does not guarantee the OS will start or that writes are safe.

## Roadmap

- Real container and volume Object Map traversal with XID-aware resolution
- Validate B-tree links and compare old checkpoint states
- Safe, independent copy-on-write candidate generation (opt-in)
- Repeatable corruption tests using synthetic disk images
- Clear macOS GUI with diagnostics and warnings

## Help us make recovery possible for more people

**We would love your contributions, comments, and real-world recovery stories.** Data is often irreplaceable: family photos, years of creative work, research, documents, and projects. We want to build a better, freely accessible recovery toolkit **together**, based on reproducible evidence—not promises or trial-and-error on someone's only disk.

Please share:
- **Your recovery story or feedback:** [Open a story / feedback issue](https://github.com/cell0013/apfs-rescue-lab/issues/new?template=recovery-story.yml). Tell us what happened, which OS / APFS version you used, what worked, and what did not.
- **Bugs and reproducible failures:** [Report a bug](https://github.com/cell0013/apfs-rescue-lab/issues/new?template=bug-report.yml).
- **Ideas and compatibility requests:** [Create an issue](https://github.com/cell0013/apfs-rescue-lab/issues/new).
- **Code, tests, translations, and documentation improvements:** [Open a pull request](https://github.com/cell0013/apfs-rescue-lab/pulls), following [CONTRIBUTING.md](CONTRIBUTING.md).

**Your story matters even if recovery failed.** It can help us recognize unsupported layouts and prevent others from losing data.

**Privacy first:** please do not share disk images, real file contents, unredacted paths, user names, device serials, volume UUIDs, credentials, API keys, or full private logs. Prefer sanitized summaries and synthetic test images. Everything posted in this public repository is publicly visible.

## Support

Everything remains free. If APFS Rescue Lab helped you, you can [buy us a coffee](https://buymeacoffee.com/apfs.rescue.lab) to support further development. Donations are completely optional and do not affect access to the tools. See [DONATE.md](DONATE.md).

## License

MIT — see [LICENSE](LICENSE). Contributions and independent testing are welcome ([CONTRIBUTING.md](CONTRIBUTING.md)). [Русская версия](README.ru.md).
