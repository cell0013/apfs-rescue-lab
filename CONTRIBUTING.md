# Contributing to APFS Rescue Lab

Issues and pull requests are welcome. Provide **synthetic, anonymized examples** only. Do not post real disks, personal logs, filesystem paths, user names, tokens, secret keys, or project source files.

Run `python3 -m unittest discover -s tests -v` and compile the scripts before creating a PR.

Write operations to APFS must remain opt-in, must operate on verified independent copies, must have repeatable tests, and must be independently reviewed. No speculative automatic modification of originals or live devices.

## How to take part

We welcome contributions from developers, researchers and people who have experienced APFS data loss. Your feedback matters even if you are not a programmer or recovery was unsuccessful.

- **Share a recovery story:** [use the story issue template](https://github.com/cell0013/apfs-rescue-lab/issues/new?template=recovery-story.yml) with OS version, disk/image type, filesystem symptoms, which steps helped, and whether files or bootability returned.
- **Report a problem:** [use the bug template](https://github.com/cell0013/apfs-rescue-lab/issues/new?template=bug-report.yml).
- **Suggest a feature or add compatibility information:** [open an issue](https://github.com/cell0013/apfs-rescue-lab/issues/new).
- **Contribute code, tests, translations, documentation:** [submit a pull request](https://github.com/cell0013/apfs-rescue-lab/pulls).

Please never upload original disk images, personal data, entire private diagnostic logs, home-directory listings, passwords, serial numbers, UUIDs, or credentials. Use a synthetic reproducer, redact excerpts and check all attachments before posting. All GitHub Issues and Pull Requests in this repository are public.

Data recovery can affect the most irreplaceable parts of people's lives. Write operations must not be advertised as safe without independent evidence, clear limitations and a reversible copy-first workflow.

