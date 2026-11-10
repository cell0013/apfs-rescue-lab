# Automatic checkpoint nomination (experimental)

**This is not a universal APFS recovery utility.** It is a **heuristic candidate selector** based on the failure mode encountered during one macOS Catalina APFS Data-volume recovery.

The program detects GPT/APFS, enumerates existing container checkpoints and scans APFS volume superblocks. When it finds **one unambiguous case** where the newest volume Object Map header/root looks broken and an earlier volume version has plausible headers and an XID matching an existing container checkpoint, it **nominates that historical checkpoint automatically**.

It does **not** validate complete APFS B-trees, snapshots, allocation data, encryption, signed system volumes, bootability or long-term write safety. **If multiple candidates match, it stops without modifying an image.**

## 1 — Read-only diagnosis (safe default)

```bash
python3 apfs_rescue.py analyze \
  --source "/path/to/offline-disk.raw" \
  --report "/path/to/new-analysis.json"
```

No modification to the RAW.

## 2 — Build an experimental candidate (high risk)

**Before trying this:** preserve your original as a verified independent offline backup; confirm the input is a disposable RAW copy on an APFS filesystem; stop the VM; read [DISCLAIMER](../DISCLAIMER.md).

```bash
python3 apfs_rescue.py recover \
  --source "/path/to/offline-test-source.raw" \
  --output "/path/to/new-candidate.raw" \
  --report "/path/to/new-report.json" \
  --i-understand-this-can-destroy-data
```

If exactly one plausible checkpoint was nominated, the program delegates to the experimental selector. That selector uses macOS `cp -c` to create a **new copy-on-write RAW**, then invalidates the **newer APFS checkpoint headers on the clone**. The input file is opened read-only.

**Caution:** deliberately invalidated checkpoint headers cause checksum errors. This is not a true checkpoint rollback. Other metadata may be inconsistent or overwritten. **Do not trust this candidate for continued writes** even if it mounts or boots.

## 3 — Independent verification

- Inspect the generated report. Verify what was changed on the clone.
- Attach the candidate read-only, not the original.
- Run read-only checks with appropriate tools, such as `fsck_apfs -n` on macOS.
- Read actual recovered files, checking representative content and metadata.
- If valuable data is present, copy it onto a clean filesystem first.
- Boot a throwaway VM copy only as a separate, explicitly risky experiment.
- Do not assume a successful first boot proves safe operation or successful future reboots.

## Compatibility and limitations

| Environment | Support status |
|---|---|
| macOS Catalina-style unencrypted APFS VM images (GPT + whole-disk RAW) | **Experimental: originally observed here** |
| Other Intel macOS / APFS versions | **Unverified** |
| macOS Big Sur and later with signed system volume | **Not validated** |
| FileVault / encrypted APFS | **Not validated** |
| Apple Silicon internal system disks | **Not validated** |
| Fusion Drive / multi-store containers | **Not supported** |
| Live disks or physical devices | **Prohibited by interface** |

The scripts may successfully **read** common APFS metadata across versions, but that does **not** imply they can recover, boot or safely modify every APFS-based OS.

## Technical note

The heuristic is based on a shallow validation: checksum, object type, XID and Object Map B-tree root. It is intentionally **not** advertised as proof of a consistent historical checkpoint. A future release should resolve each volume OID through the container Object Map at the target XID, validate full trees and allocations, and require a full consistency check before the clone may be presented as a viable candidate.

## По-русски

Восстановление **не универсальное**. Команда `analyze` автоматически ищет наиболее вероятный исторический checkpoint по метаданным, ничего не меняя. Команда `recover`, только после явного подтверждения риска, создаёт отдельный APFS-клон и делает новые checkpoint недействительными **только на клоне**. Если выбор неоднозначен — программа останавливается.

Наш успешный случай относится к Catalina; другие macOS, шифрование, Apple Silicon и загрузочные APFS-контейнеры с Signed System Volume **не проверены**. Использование исключительно **на свой страх и риск**, ПО предоставляется **«КАК ЕСТЬ»**.
