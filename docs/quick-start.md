# APFS recovery investigation — practical guide

**Warning: Use at your own risk.** This is a diagnostic workflow, **not** a one-click recovery procedure or a proven way to fix arbitrary APFS corruption.

## 0. Protect the original

1. Stop writing to the affected device or VM disk.
2. Save an **offline, verified image** of the complete disk.
3. Perform all investigations on **separate test copies**.
4. Do not share your disk images, unredacted logs, host paths, tokens, passwords or user directories with third parties.

If your data is irreplaceable, consider professional data-recovery services before experimenting.

## 1. Prepare a RAW disk image

These tools expect a whole-disk RAW image with a GPT and an APFS partition. An APFS partition dump alone is **not** supported.

For a VMware disk image, a commonly used conversion tool is QEMU:

```bash
qemu-img info "/path/to/virtual-disk.vmdk"
qemu-img convert -p -f vmdk -O raw "/path/to/virtual-disk.vmdk" "/path/to/analysis-copy.raw"
```

Do **not** convert a running, suspended or snapshot-dependent VM without resolving its complete disk chain. The example is not suitable for every VM.

## 2. Inspect APFS without changes

```bash
python3 tools/apfs_analyzer.py \
  --source "/path/to/analysis-copy.raw" \
  --out "./analysis.json"
```

Inspect the GPT-derived APFS start offset, checksum status of checkpoint superblocks and the list of XIDs. **A valid checksum alone does not certify the filesystem tree.**

## 3. Compare a trial with an independent baseline

If you already have two complete offline RAW copies, compare them:

```bash
python3 tools/block_diff.py \
  --source "/path/to/baseline.raw" \
  --compare "/path/to/trial.raw" \
  --out-dir "./diff-report"
```

The results contain one JSONL record per changed 4 KiB block plus changed ranges and a summary. **Do not interpret a small number of changes as proof of safe repair.** The report may include device-specific offsets and filesystem metadata: redact before sharing.

## 4. Verify independently

On a separate test copy, verify the filesystem in a read-only mode using OS tools appropriate for the original filesystem version. For macOS, an offline check often uses `fsck_apfs -n`. Do not allow automatic repair on the original. macOS version differences may affect APFS behavior.

Read-only file checks should confirm the **actual files you need**, not just a successful mount. Boot behavior, login, application launching, filesystem write safety and reboot stability are additional independent criteria.

## 5. Understand the case report

The [anonymized Catalina case](recovery-case.md) explains why fixing an Object Map header or accepting the first passing checkpoint was insufficient. The final experimental trial selected an older existing checkpoint **on a copy**. Its experimental implementation is now published in [experimental checkpoint usage](experimental-checkpoint.md), with explicit risk acknowledgement. It is **not** a safe general-purpose repair command.

We do not recommend copying that experiment onto an unrelated disk. Reliable automated rollback must validate complete checkpoint references, Object Map B-trees, allocation structures and volume metadata together.

## 6. Share a bug safely

When reporting a bug, include the Python version and tool version, the **general** image format, the error text with paths/identifiers redacted, and a synthetic reproducer when possible. Never upload a full disk image or private project contents.

Software is supplied **AS IS** and **without warranty**. See [DISCLAIMER.md](../DISCLAIMER.md).
